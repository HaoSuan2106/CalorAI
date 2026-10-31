"""Builds the train/val/test image folders used by train_food_model.py.

Collects images from one or more source folders laid out as <source>/<class_name>/*.jpg
(e.g. Food-101's `food-101/images` folder, and your own Malaysian food photos) and copies a
random split into:

    ml/dataset/train/<class>/   ml/dataset/val/<class>/   ml/dataset/test/<class>/

Class folder names must match a FoodItem name in backend/seed/foods.csv after replacing
underscores with spaces, e.g. `nasi_lemak` -> "Nasi Lemak", `chicken_wings` -> "Chicken Wings".

Examples:
  python prepare_dataset.py --source D:/food-101/images --classes fried_rice pizza sushi ramen
  python prepare_dataset.py --source D:/food-101/images D:/my_malaysian_food --all --per-class 300
"""
import argparse
import random
import shutil
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Food-101 classes that exist in the CalorAI food database
FOOD101_IN_DB = [
    "caesar_salad", "cheesecake", "chicken_curry", "chicken_wings", "chocolate_cake",
    "donuts", "dumplings", "french_fries", "fried_rice", "grilled_salmon", "hamburger",
    "ice_cream", "omelette", "pancakes", "pho", "pizza", "ramen", "spaghetti_bolognese",
    "spaghetti_carbonara", "spring_rolls", "steak", "sushi", "waffles", "fish_and_chips",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", nargs="+", required=True, help="folder(s) containing class folders")
    ap.add_argument("--classes", nargs="*", help="class folder names to include")
    ap.add_argument("--all", action="store_true", help="include every class folder found")
    ap.add_argument("--food101-db", action="store_true",
                    help="include the Food-101 classes that exist in the food database")
    ap.add_argument("--per-class", type=int, default=400, help="max images per class")
    ap.add_argument("--out", default=str(Path(__file__).parent / "dataset"))
    ap.add_argument("--split", nargs=3, type=float, default=[0.8, 0.1, 0.1])
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    found: dict[str, list[Path]] = {}
    for src in args.source:
        for d in Path(src).iterdir():
            if d.is_dir():
                imgs = [p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXT]
                found.setdefault(d.name.lower(), []).extend(imgs)

    wanted = set(c.lower() for c in (args.classes or []))
    if args.food101_db:
        wanted |= set(FOOD101_IN_DB)
    if args.all:
        wanted |= set(found)
    missing = sorted(wanted - set(found))
    if missing:
        print("WARNING: no folder found for:", ", ".join(missing))
    classes = sorted(wanted & set(found))
    if not classes:
        raise SystemExit("No classes selected. Use --classes, --food101-db or --all.")

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    rng = random.Random(args.seed)
    tr, va, _ = args.split
    for c in classes:
        imgs = found[c][:]
        rng.shuffle(imgs)
        imgs = imgs[:args.per_class]
        n_tr, n_va = int(len(imgs) * tr), int(len(imgs) * va)
        parts = {"train": imgs[:n_tr], "val": imgs[n_tr:n_tr + n_va], "test": imgs[n_tr + n_va:]}
        for split, files in parts.items():
            dst = out / split / c
            dst.mkdir(parents=True, exist_ok=True)
            for i, f in enumerate(files):
                shutil.copy2(f, dst / f"{i:05d}{f.suffix.lower()}")
        print(f"{c:28s} train={len(parts['train']):4d} val={len(parts['val']):4d} "
              f"test={len(parts['test']):4d}")
    print(f"\nDataset ready in {out} ({len(classes)} classes)")


if __name__ == "__main__":
    main()
