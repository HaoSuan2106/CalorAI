"""Meal Logging Controller logic: save / update / delete meals and trigger scoring + alerts."""
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import FoodItem, Meal, MealItem, Notification, User
from ..schemas import MealCreate
from .dashboard_service import DashboardService
from .meal_scoring_engine import MealScoringEngine
from .notification_service import NotificationService

DEFAULT_PORTIONS = {
    "Rice Dish": 350, "Noodle Dish": 350, "Western": 250, "Vegetables & Salad": 150,
    "Meat & Seafood": 150, "Egg & Soy": 100, "Bread & Roti": 100, "Snack & Kuih": 60,
    "Dessert": 100, "Fruit": 150, "Beverage": 250,
}


def default_portion(food: FoodItem) -> float:
    return DEFAULT_PORTIONS.get(food.food_category, 100)


def nutrition_for_portion(food: FoodItem, grams: float) -> dict[str, float]:
    k = grams / 100.0
    return {
        "calories": round(food.calories_per_100g * k, 2),
        "carbs": round(food.carbs_per_100g * k, 2),
        "protein": round(food.protein_per_100g * k, 2),
        "fat": round(food.fat_per_100g * k, 2),
        "sugar": round(food.sugar_per_100g * k, 2),
        "sodium": round(food.sodium_per_100g * k, 2),
        "fibre": round(food.fibre_per_100g * k, 2),
    }


class MealLoggingService:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    def _build_items(self, data: MealCreate) -> list[MealItem]:
        items = []
        for it in data.items:
            food = self.db.get(FoodItem, it.food_id)
            if food is None:
                raise HTTPException(404, f"Food item {it.food_id} not found")
            n = it.override.model_dump() if it.override else nutrition_for_portion(food, it.portion_size_g)
            mi = MealItem(food_id=food.food_id, portion_size_g=it.portion_size_g,
                          **{k: min(n[k], 9999.99) for k in
                             ("calories", "carbs", "protein", "fat", "sugar", "sodium")})
            mi.food = food
            items.append(mi)
        return items

    def save_meal(self, data: MealCreate, meal: Meal | None = None) -> tuple[Meal, list[Notification]]:
        old_day: date | None = None
        if meal is None:
            meal = Meal(user_id=self.user.user_id, created_at=datetime.now())
            self.db.add(meal)
        else:
            old_day = meal.meal_datetime.date()
            meal.items.clear()
            self.db.flush()

        meal.meal_category = data.meal_category
        meal.source_type = data.source_type
        meal.meal_datetime = (data.meal_datetime or datetime.now()).replace(tzinfo=None)
        meal.items = self._build_items(data)
        meal.calculate_total_nutrition()
        self.db.flush()  # assigns meal_id

        _, conflicts = MealScoringEngine(self.db, self.user).evaluate_meal(meal)

        dash = DashboardService(self.db, self.user)
        summary = dash.refresh_daily_summary(meal.meal_datetime.date())
        if old_day and old_day != meal.meal_datetime.date():
            dash.refresh_daily_summary(old_day)

        notifier = NotificationService(self.db, self.user)
        alerts = notifier.send_conflict_alerts(meal, conflicts)
        if summary.summary_date == date.today():
            alerts += notifier.send_excess_nutrition_alerts(summary, meal)

        self.db.commit()
        self.db.refresh(meal)
        return meal, alerts

    def delete_meal(self, meal: Meal) -> None:
        day = meal.meal_datetime.date()
        self.db.execute(update(Notification)
                        .where(Notification.related_meal_id == meal.meal_id)
                        .values(related_meal_id=None))
        self.db.delete(meal)
        self.db.flush()
        DashboardService(self.db, self.user).refresh_daily_summary(day)
        self.db.commit()
