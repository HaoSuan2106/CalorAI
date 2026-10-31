"""Loads the reference food database (seed/foods.csv) into FoodItem on first start.

Values are approximate per-100 g (per-100 ml for beverages) figures. Verify/extend them with
the Malaysian Food Composition Database (MyFCD) before final evaluation.
"""
import csv

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import FoodItem


def seed_food_items(db: Session) -> int:
    if db.scalar(select(func.count()).select_from(FoodItem)):
        return 0
    added = 0
    with open(settings.SEED_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            db.add(FoodItem(
                food_name=row["food_name"],
                food_category=row["food_category"],
                calories_per_100g=float(row["calories"]),
                carbs_per_100g=float(row["carbs"]),
                protein_per_100g=float(row["protein"]),
                fat_per_100g=float(row["fat"]),
                sugar_per_100g=float(row["sugar"]),
                sodium_per_100g=float(row["sodium"]),
                fibre_per_100g=float(row["fibre"]),
                allergen_tags=",".join(t for t in row["tags"].split("|") if t),
            ))
            added += 1
    db.commit()
    return added
