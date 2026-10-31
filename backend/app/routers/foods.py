"""Food database: browse/search for manual logging, and add custom/scanned products."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import FoodItem, User
from ..schemas import FoodCreate, FoodItemOut
from ..security import get_current_user
from ..serializers import food_out
from ..services.dietary_profile_service import tags_in_text
from ..services.meal_logging_service import nutrition_for_portion

router = APIRouter(prefix="/foods", tags=["Meal Logging"])


@router.get("", response_model=list[FoodItemOut])
def list_foods(q: str | None = None, category: str | None = None,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(FoodItem).order_by(FoodItem.food_name)
    if q:
        stmt = stmt.where(FoodItem.food_name.ilike(f"%{q.strip()}%"))
    if category:
        stmt = stmt.where(FoodItem.food_category == category)
    return [food_out(f, user) for f in db.scalars(stmt)]


@router.get("/categories", response_model=list[str])
def categories(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return sorted(set(db.scalars(select(FoodItem.food_category))))


@router.get("/{food_id}")
def get_food(food_id: int, portion_g: float | None = Query(default=None, gt=0, le=5000),
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    food = db.get(FoodItem, food_id)
    if food is None:
        raise HTTPException(404, "Food item not found")
    out = food_out(food, user)
    grams = portion_g or out.default_portion_g
    return {"food": out, "portion_g": grams, "nutrition": nutrition_for_portion(food, grams)}


@router.post("", response_model=FoodItemOut, status_code=201)
def create_food(data: FoodCreate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    k = 100.0 / data.serving_size_g
    per100 = {f: round(getattr(data, f) * k, 2)
              for f in ("calories", "carbs", "protein", "fat", "sugar", "sodium", "fibre")}
    if per100["calories"] > 950 or max(per100["carbs"], per100["protein"], per100["fat"]) > 100:
        raise HTTPException(422, "The values are too high for the serving size. "
                                 "Please check the serving size and nutrition values.")
    tags = ({t.strip().lower() for t in data.tags if t.strip()} | tags_in_text(data.food_name)
            | tags_in_text(data.ingredients_text))
    tag_str = ""
    for t in sorted(tags):  # VARCHAR(100)
        if len(tag_str) + len(t) + 1 > 100:
            break
        tag_str = f"{tag_str},{t}" if tag_str else t
    food = FoodItem(
        food_name=data.food_name.strip(), food_category=data.food_category or "Scanned Product",
        calories_per_100g=per100["calories"], carbs_per_100g=per100["carbs"],
        protein_per_100g=per100["protein"], fat_per_100g=per100["fat"],
        sugar_per_100g=per100["sugar"], sodium_per_100g=min(per100["sodium"], 9999.99),
        fibre_per_100g=per100["fibre"], allergen_tags=tag_str,
    )
    db.add(food)
    db.commit()
    db.refresh(food)
    return food_out(food, user)
