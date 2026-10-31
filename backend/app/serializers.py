from .models import FoodItem, Meal, User
from .schemas import (Conflict, FoodItemOut, MealItemOut, MealOut, MealScoreOut, RiskOut,
                      Targets, UserOut)
from .services.dietary_profile_service import food_conflicts
from .services.meal_logging_service import default_portion
from .services.meal_scoring_engine import feedback_of
from .services.nutrition_goals import daily_targets


def user_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.targets = Targets(**daily_targets(user))
    return out


def food_out(food: FoodItem, user: User | None = None) -> FoodItemOut:
    out = FoodItemOut.model_validate(food)
    out.default_portion_g = default_portion(food)
    if user is not None:
        out.conflicts = [Conflict(**c.as_dict()) for c in food_conflicts(food, user.profile)]
    return out


def meal_out(meal: Meal, model=MealOut, **extra):
    score = None
    if meal.score is not None:
        fb = feedback_of(meal.score)
        score = MealScoreOut(
            score_id=meal.score.score_id,
            overall_score=meal.score.overall_score,
            grade=fb.get("grade", ""),
            summary=fb.get("summary", ""),
            factors=fb.get("factors", []),
            alternatives=fb.get("alternatives", []),
            risks=[RiskOut.model_validate(r) for r in meal.score.risks],
        )
    items = []
    for i in meal.items:
        mi = MealItemOut.model_validate(i)
        mi.food_name = i.food.food_name if i.food else ""
        items.append(mi)
    return model(
        meal_id=meal.meal_id, meal_category=meal.meal_category, meal_datetime=meal.meal_datetime,
        source_type=meal.source_type, total_calories=meal.total_calories,
        total_carbs=meal.total_carbs, total_protein=meal.total_protein,
        total_fat=meal.total_fat, total_sugar=meal.total_sugar, total_sodium=meal.total_sodium,
        items=items, score=score, **extra,
    )
