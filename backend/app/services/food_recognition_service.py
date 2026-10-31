"""Food Recognition Service: runs the TensorFlow food classifier trained by ml/train_food_model.py.

The model takes RGB images with pixel values 0-255 (preprocessing is built into the model) and
outputs softmax probabilities over the classes listed in labels.txt.
"""
import difflib
import io
import logging
import os
import threading
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from ..config import settings

log = logging.getLogger("calorai.recognition")


class ModelNotAvailable(RuntimeError):
    pass


@dataclass
class Prediction:
    label: str
    confidence: float


def normalise_label(label: str) -> str:
    return label.replace("_", " ").replace("-", " ").strip().lower()


class FoodRecognitionService:
    _model = None
    _labels: list[str] = []
    _input_size = (224, 224)
    _lock = threading.Lock()
    _load_error: str | None = None

    @classmethod
    def is_available(cls) -> bool:
        return os.path.exists(settings.MODEL_PATH) and os.path.exists(settings.LABELS_PATH)

    @classmethod
    def is_loaded(cls) -> bool:
        return cls._model is not None

    @classmethod
    def load(cls):
        with cls._lock:
            if cls._model is not None:
                return
            if not cls.is_available():
                raise ModelNotAvailable(
                    "Food recognition model not found. Train it with ml/train_food_model.py "
                    "(see README), or use manual search.")
            try:
                os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
                import tensorflow as tf  # imported lazily: heavy and optional
            except ImportError as e:
                raise ModelNotAvailable(
                    "TensorFlow is not installed. Run: pip install -r requirements-ai.txt") from e
            model = tf.keras.models.load_model(settings.MODEL_PATH, compile=False)
            with open(settings.LABELS_PATH, encoding="utf-8") as f:
                cls._labels = [line.strip() for line in f if line.strip()]
            shape = model.input_shape
            cls._input_size = (int(shape[1] or 224), int(shape[2] or 224))
            # warm-up so the first real request meets the 5 s requirement
            model.predict(np.zeros((1, *cls._input_size, 3), dtype=np.float32), verbose=0)
            cls._model = model
            log.info("Food model loaded: %d classes, input %s", len(cls._labels), cls._input_size)

    @classmethod
    def warm_up_in_background(cls):
        def _run():
            try:
                cls.load()
            except Exception as e:  # noqa: BLE001 — startup must not fail because of the model
                cls._load_error = str(e)
                log.warning("Food model not loaded: %s", e)
        threading.Thread(target=_run, daemon=True).start()

    @classmethod
    def _prepare(cls, image_bytes: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
        # centre-crop to square, then resize (matches training preprocessing)
        img = ImageOps.fit(img, cls._input_size, Image.Resampling.BILINEAR)
        return np.asarray(img, dtype=np.float32)[None, ...]

    @classmethod
    def classify_food(cls, image_bytes: bytes, top_k: int = 3) -> list[Prediction]:
        cls.load()
        x = cls._prepare(image_bytes)
        probs = cls._model.predict(x, verbose=0)[0]
        idx = np.argsort(probs)[::-1][:top_k]
        return [Prediction(cls._labels[i], float(probs[i])) for i in idx]


def match_food_name(label: str, food_names: list[str]) -> str | None:
    """Map a model class label (e.g. 'nasi_lemak') to a FoodItem name ('Nasi Lemak')."""
    target = normalise_label(label)
    lookup = {normalise_label(n): n for n in food_names}
    if target in lookup:
        return lookup[target]
    # singular/plural and near matches ('donut' vs 'donuts', 'satay' vs 'chicken satay')
    for key, name in lookup.items():
        if key.rstrip("s") == target.rstrip("s") or key.endswith(" " + target):
            return name
    close = difflib.get_close_matches(target, list(lookup), n=1, cutoff=0.8)
    return lookup[close[0]] if close else None
