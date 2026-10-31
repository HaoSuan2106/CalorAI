"""Daily calorie goal and nutrient targets for a user.

Calories: Mifflin-St Jeor BMR x activity factor, adjusted for the health goal.
Limits: WHO guidance — free sugar < 10% of energy (5% for diabetes), sodium < 2000 mg
(1500 mg for hypertension), fat <= 30-35% of energy, fibre >= 25 g.
"""
from ..models import User

ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}
GOAL_ADJUSTMENT = {"weight_loss": -500, "maintenance": 0, "muscle_gain": 300}


def bmr(user: User) -> float:
    base = 10 * user.weight_kg + 6.25 * user.height_cm - 5 * user.age
    if user.gender == "male":
        return base + 5
    if user.gender == "female":
        return base - 161
    return base - 78


def calorie_goal(user: User) -> float:
    tdee = bmr(user) * ACTIVITY_FACTORS.get(user.activity_level, 1.55)
    goal = tdee + GOAL_ADJUSTMENT.get(user.health_goal, 0)
    floor = 1500 if user.gender == "male" else 1200
    return round(max(goal, floor))


def conditions_of(user: User) -> set[str]:
    if not user.profile:
        return set()
    return {c.condition_name.strip().lower() for c in user.profile.medical_conditions}


def daily_targets(user: User) -> dict[str, float]:
    cal = calorie_goal(user)
    conditions = conditions_of(user)
    diabetic = any("diabet" in c for c in conditions)
    hypertensive = any("hypertens" in c or "blood pressure" in c for c in conditions)

    carb_share = 0.45 if diabetic else 0.50
    protein_g = cal * 0.20 / 4
    if user.health_goal == "muscle_gain":
        protein_g = max(protein_g, 1.6 * user.weight_kg)
    else:
        protein_g = max(protein_g, 0.8 * user.weight_kg)

    return {
        "calories": cal,
        "carbs": round(cal * carb_share / 4),
        "protein": round(protein_g),
        "fat": round(cal * 0.30 / 9),
        "sugar_limit": round(cal * (0.05 if diabetic else 0.10) / 4),
        "sodium_limit": 1500 if hypertensive else 2000,
        "fat_limit": round(cal * 0.35 / 9),
        "fibre": 25,
    }
