"""Meal Logging module: save, history, update, delete."""
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Meal, MealItem, MealScore, User
from ..schemas import MealCreate, MealOut, MealSaveResponse, NotificationOut
from ..security import get_current_user
from ..serializers import meal_out
from ..services.meal_logging_service import MealLoggingService

router = APIRouter(prefix="/meals", tags=["Meal Logging"])


def _own_meal(db: Session, user: User, meal_id: int) -> Meal:
    meal = db.get(Meal, meal_id)
    if meal is None or meal.user_id != user.user_id:
        raise HTTPException(404, "Meal not found")
    return meal


@router.post("", response_model=MealSaveResponse, status_code=201)
def save_meal(data: MealCreate, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    meal, alerts = MealLoggingService(db, user).save_meal(data)
    return meal_out(meal, MealSaveResponse,
                    alerts=[NotificationOut.model_validate(a) for a in alerts])


@router.get("", response_model=list[MealOut])
def meal_history(start: date | None = None, end: date | None = None,
                 category: str | None = None, limit: int = 200,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = (select(Meal).where(Meal.user_id == user.user_id)
            .options(selectinload(Meal.items).selectinload(MealItem.food),
                     selectinload(Meal.score).selectinload(MealScore.risks))
            .order_by(Meal.meal_datetime.desc()).limit(min(limit, 1000)))
    if start:
        stmt = stmt.where(Meal.meal_datetime >= datetime.combine(start, time.min))
    if end:
        stmt = stmt.where(Meal.meal_datetime <= datetime.combine(end, time.max))
    if category:
        stmt = stmt.where(Meal.meal_category == category.lower())
    return [meal_out(m) for m in db.scalars(stmt)]


@router.get("/{meal_id}", response_model=MealOut)
def get_meal(meal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return meal_out(_own_meal(db, user, meal_id))


@router.put("/{meal_id}", response_model=MealSaveResponse)
def update_meal(meal_id: int, data: MealCreate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    meal, alerts = MealLoggingService(db, user).save_meal(data, _own_meal(db, user, meal_id))
    return meal_out(meal, MealSaveResponse,
                    alerts=[NotificationOut.model_validate(a) for a in alerts])


@router.delete("/{meal_id}", status_code=204)
def delete_meal(meal_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    MealLoggingService(db, user).delete_meal(_own_meal(db, user, meal_id))
