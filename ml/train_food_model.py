"""Trains the CalorAI food-recognition model (transfer learning, TensorFlow/Keras).

Phase 1: frozen ImageNet backbone, train the classification head.
Phase 2: unfreeze the top of the backbone and fine-tune with a low learning rate.
Then evaluates on the held-out test split (target: >= 90% accuracy, NFR 1.3.5.1) and writes:

    ml/models/food_model.keras   (loaded by the backend)
    ml/models/labels.txt
    ml/models/food_model.tflite  (optional on-device use)
    ml/models/evaluation.txt     (accuracy + per-class report + confusion matrix for your report)
    ml/models/training_curves.png

Usage:
  python train_food_model.py                       # MobileNetV2 (fast, mobile friendly)
  python train_food_model.py --arch efficientnetv2b0 --epochs 12 --fine-tune-epochs 12
"""
import argparse
from pathlib import Path

import numpy as np
import tensorflow as tf

HERE = Path(__file__).parent


def build_model(arch: str, num_classes: int, img_size: int):
    inputs = tf.keras.Input(shape=(img_size, img_size, 3), name="image")  # pixels 0-255
    aug = tf.keras.Sequential([
        tf.keras.layers.RandomFlip("horizontal"),
        tf.keras.layers.RandomRotation(0.08),
        tf.keras.layers.RandomZoom(0.15),
        tf.keras.layers.RandomContrast(0.15),
    ], name="augmentation")
    x = aug(inputs)
    if arch == "mobilenetv2":
        x = tf.keras.layers.Rescaling(1 / 127.5, offset=-1, name="preprocess")(x)  # -> [-1, 1]
        base = tf.keras.applications.MobileNetV2(include_top=False, weights="imagenet",
                                                 input_shape=(img_size, img_size, 3))
    elif arch == "efficientnetv2b0":
        base = tf.keras.applications.EfficientNetV2B0(include_top=False, weights="imagenet",
                                                      input_shape=(img_size, img_size, 3),
                                                      include_preprocessing=True)
    else:
        raise ValueError(arch)
    base.trainable = False
    x = base(x, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.3)(x)
    outputs = tf.keras.layers.Dense(num_classes, activation="softmax", name="food")(x)
    return tf.keras.Model(inputs, outputs, name=f"calorai_{arch}"), base


def load_split(root: Path, split: str, img_size: int, batch: int, shuffle: bool, class_names=None):
    return tf.keras.utils.image_dataset_from_directory(
        root / split, image_size=(img_size, img_size), batch_size=batch, shuffle=shuffle,
        label_mode="int", class_names=class_names, crop_to_aspect_ratio=True, seed=42)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "dataset"))
    ap.add_argument("--out", default=str(HERE / "models"))
    ap.add_argument("--arch", default="mobilenetv2", choices=["mobilenetv2", "efficientnetv2b0"])
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--fine-tune-epochs", type=int, default=10)
    ap.add_argument("--unfreeze", type=int, default=40, help="top backbone layers to fine-tune")
    args = ap.parse_args()

    data, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    train_ds = load_split(data, "train", args.img_size, args.batch, True)
    class_names = train_ds.class_names
    val_ds = load_split(data, "val", args.img_size, args.batch, False, class_names)
    test_ds = load_split(data, "test", args.img_size, args.batch, False, class_names)
    auto = tf.data.AUTOTUNE
    train_ds, val_ds, test_ds = (d.prefetch(auto) for d in (train_ds, val_ds, test_ds))
    print(f"{len(class_names)} classes: {class_names}")

    model, base = build_model(args.arch, len(class_names), args.img_size)
    ckpt = str(out / "food_model.keras")
    callbacks = [
        tf.keras.callbacks.ModelCheckpoint(ckpt, monitor="val_accuracy", save_best_only=True),
        tf.keras.callbacks.EarlyStopping(monitor="val_accuracy", patience=4,
                                         restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.3, patience=2),
    ]

    # Phase 1 — train head
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3),
                  loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    h1 = model.fit(train_ds, validation_data=val_ds, epochs=args.epochs, callbacks=callbacks)

    # Phase 2 — fine-tune top layers (BatchNorm layers stay frozen)
    base.trainable = True
    for layer in base.layers[:-args.unfreeze]:
        layer.trainable = False
    for layer in base.layers:
        if isinstance(layer, tf.keras.layers.BatchNormalization):
            layer.trainable = False
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-5),
                  loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    h2 = model.fit(train_ds, validation_data=val_ds, epochs=args.fine_tune_epochs,
                   callbacks=callbacks)

    model = tf.keras.models.load_model(ckpt)  # best checkpoint
    (out / "labels.txt").write_text("\n".join(class_names), encoding="utf-8")

    # ---- Evaluation on the unseen test split ----
    y_true = np.concatenate([y.numpy() for _, y in test_ds])
    y_prob = model.predict(test_ds, verbose=0)
    y_pred = y_prob.argmax(axis=1)
    acc = float((y_pred == y_true).mean())
    top3 = float(np.mean([t in np.argsort(p)[-3:] for t, p in zip(y_true, y_prob)]))
    lines = [f"Architecture: {args.arch}", f"Classes: {len(class_names)}",
             f"Test images: {len(y_true)}", f"Top-1 accuracy: {acc:.4f}",
             f"Top-3 accuracy: {top3:.4f}",
             f"Target (>= 0.90): {'MET' if acc >= 0.90 else 'NOT MET'}", ""]
    try:
        from sklearn.metrics import classification_report, confusion_matrix
        lines.append(classification_report(y_true, y_pred, target_names=class_names, digits=3))
        lines.append("Confusion matrix (rows = true, cols = predicted):")
        lines.append(np.array2string(confusion_matrix(y_true, y_pred), max_line_width=400))
    except ImportError:
        pass
    report = "\n".join(lines)
    (out / "evaluation.txt").write_text(report, encoding="utf-8")
    print(report)

    # ---- Training curves ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        acc_hist = h1.history["accuracy"] + h2.history["accuracy"]
        val_hist = h1.history["val_accuracy"] + h2.history["val_accuracy"]
        plt.figure(figsize=(7, 4))
        plt.plot(acc_hist, label="train")
        plt.plot(val_hist, label="validation")
        plt.axvline(len(h1.history["accuracy"]) - 0.5, color="gray", ls="--", label="fine-tune starts")
        plt.xlabel("epoch"); plt.ylabel("accuracy"); plt.legend(); plt.tight_layout()
        plt.savefig(out / "training_curves.png", dpi=150)
    except ImportError:
        pass

    # ---- Optional TFLite export (for on-device inference) ----
    try:
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        (out / "food_model.tflite").write_bytes(converter.convert())
    except Exception as e:  # noqa: BLE001
        print("TFLite export skipped:", e)

    print(f"\nSaved model to {ckpt}")


if __name__ == "__main__":
    main()
