"""Meal Scoring Engine.

Scores each meal 0-100 by comparing its nutrient composition against the user's per-meal
share of their daily targets, deducting points for each identified nutrition risk and dietary
conflict. Every deduction is recorded as a factor, so the score is fully explainable.
"""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FoodItem, Meal, MealScore, NutritionRisk, User
from .dietary_profile_service import (ConflictResult, check_conflicts, food_conflicts,
                                      food_tags)
from .nutrition_goals import conditions_of, daily_targets

MEAL_SHARE = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.30, "snack": 0.15}
LIGHT_CATEGORIES = {"Beverage", "Fruit", "Snack & Kuih", "Dessert"}

RISK_NUTRIENT = {
    "excess_calories": ("calories_per_100g", "lower"),
    "excess_sugar": ("sugar_per_100g", "lower"),
    "excess_sodium": ("sodium_per_100g", "lower"),
    "excess_fat": ("fat_per_100g", "lower"),
    "excess_carbs": ("carbs_per_100g", "lower"),
    "insufficient_protein": ("protein_per_100g", "higher"),
    "insufficient_fibre": ("fibre_per_100g", "higher"),
}
REASON = {
    "calories_per_100g": "fewer calories",
    "sugar_per_100g": "less sugar",
    "sodium_per_100g": "less sodium",
    "fat_per_100g": "less fat",
    "carbs_per_100g": "fewer carbohydrates",
    "protein_per_100g": "more protein",
    "fibre_per_100g": "more fibre",
}


def grade_for(score: float) -> tuple[str, str]:
    if score >= 80:
        return "A", "Excellent"
    if score >= 65:
        return "B", "Good"
    if score >= 50:
        return "C", "Fair"
    return "D", "Poor"


def health_index(f: FoodItem) -> float:
    return (f.protein_per_100g * 2 + f.fibre_per_100g * 3 - f.sugar_per_100g
            - f.sodium_per_100g / 100 - f.fat_per_100g * 0.5 - f.calories_per_100g / 50)


class MealScoringEngine:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user
        self.profile = user.profile
        self.targets = daily_targets(user)
        self.conditions = conditions_of(user)

    # ---- public API (matches the class diagram) ----
    def evaluate_meal(self, meal: Meal) -> tuple[MealScore, list[ConflictResult]]:
        score, factors, risks, conflicts = self.generate_score(meal)
        alternatives = self.suggest_healthy_alternatives(meal, [r for r, _ in risks], conflicts)
        feedback = self.generate_feedback(meal, score, factors, risks, alternatives)

        if meal.score is not None:
            self.db.delete(meal.score)
            self.db.flush()
        ms = MealScore(meal_id=meal.meal_id, overall_score=score, feedback_text=json.dumps(feedback))
        ms.risks = [NutritionRisk(risk_type=r, severity=s) for r, s in risks]
        self.db.add(ms)
        meal.score = ms
        return ms, conflicts

    def analyze_nutrition_risk(self, meal: Meal) -> list[tuple[str, str]]:
        return self.generate_score(meal)[2]

    # ---- scoring ----
    def generate_score(self, meal: Meal):
        t, share = self.targets, MEAL_SHARE.get(meal.meal_category, 0.3)
        foods = [i.food for i in meal.items]
        light_meal = meal.meal_category == "snack" or all(f.food_category in LIGHT_CATEGORIES
                                                          for f in foods)
        cal = meal.total_calories or 0
        fibre = sum((i.food.fibre_per_100g or 0) * i.portion_size_g / 100 for i in meal.items)
        # WHO free-sugar guidance excludes sugars naturally present in whole fruit
        free_sugar = sum(i.sugar for i in meal.items if i.food.food_category != "Fruit")

        score = 100.0
        factors: list[dict] = []
        risks: list[tuple[str, str]] = []

        def penalise(risk, severity, points, factor, detail):
            nonlocal score
            score -= points
            risks.append((risk, severity))
            factors.append({"factor": factor, "impact": -points, "detail": detail})

        # Calories vs this meal's share of the daily goal
        meal_cal_target = t["calories"] * share
        ratio = cal / meal_cal_target if meal_cal_target else 0
        loss_goal = self.user.health_goal == "weight_loss"
        if ratio > 1.5:
            penalise("excess_calories", "high", 25 if loss_goal else 20, "Calories",
                     f"{cal:.0f} kcal is {ratio:.1f}x your {meal.meal_category} budget "
                     f"of ~{meal_cal_target:.0f} kcal.")
        elif ratio > 1.2:
            penalise("excess_calories", "medium", 12 if loss_goal else 8, "Calories",
                     f"{cal:.0f} kcal is above your {meal.meal_category} budget "
                     f"of ~{meal_cal_target:.0f} kcal.")
        else:
            factors.append({"factor": "Calories", "impact": 0,
                            "detail": f"{cal:.0f} kcal fits your {meal.meal_category} budget "
                                      f"(~{meal_cal_target:.0f} kcal)."})

        # Sugar
        sugar_budget = t["sugar_limit"] * share
        diabetic = any("diabet" in c for c in self.conditions)
        if free_sugar > sugar_budget * 2:
            penalise("excess_sugar", "high", 20, "Sugar",
                     f"{free_sugar:.0f} g sugar is more than double your per-meal limit "
                     f"(~{sugar_budget:.0f} g){' — important with diabetes' if diabetic else ''}.")
        elif free_sugar > sugar_budget * 1.2:
            penalise("excess_sugar", "medium", 10, "Sugar",
                     f"{free_sugar:.0f} g sugar exceeds your per-meal limit (~{sugar_budget:.0f} g).")

        # Sodium
        sodium_budget = t["sodium_limit"] * share
        hypertensive = any("hypertens" in c or "blood pressure" in c for c in self.conditions)
        sodium = meal.total_sodium or 0
        if sodium > sodium_budget * 2:
            penalise("excess_sodium", "high", 20, "Sodium",
                     f"{sodium:.0f} mg sodium is more than double your per-meal limit "
                     f"(~{sodium_budget:.0f} mg){' — important with hypertension' if hypertensive else ''}.")
        elif sodium > sodium_budget * 1.2:
            penalise("excess_sodium", "medium", 10, "Sodium",
                     f"{sodium:.0f} mg sodium exceeds your per-meal limit (~{sodium_budget:.0f} mg).")

        # Fat (share of energy)
        if cal > 50:
            fat_pct = (meal.total_fat or 0) * 9 / cal
            if fat_pct > 0.45:
                penalise("excess_fat", "high", 12, "Fat",
                         f"{fat_pct:.0%} of this meal's energy comes from fat (aim for under 35%).")
            elif fat_pct > 0.35:
                penalise("excess_fat", "medium", 6, "Fat",
                         f"{fat_pct:.0%} of this meal's energy comes from fat (aim for under 35%).")

        # Carbohydrates — relevant for diabetes and keto
        diet = (self.profile.diet_preference if self.profile else "none") or "none"
        carbs = meal.total_carbs or 0
        if diet == "keto" and carbs > 20:
            penalise("excess_carbs", "medium", 10, "Carbohydrates",
                     f"{carbs:.0f} g carbs is high for a keto diet (aim for under 20 g per meal).")
        elif diabetic and carbs > t["carbs"] * share * 1.2:
            penalise("excess_carbs", "medium", 10, "Carbohydrates",
                     f"{carbs:.0f} g carbs is above your per-meal target (~{t['carbs'] * share:.0f} g) "
                     f"for blood-sugar control.")

        # Protein and fibre — only meaningful for main meals
        if not light_meal and cal > 150:
            protein_pct = (meal.total_protein or 0) * 4 / cal
            min_pct = 0.20 if self.user.health_goal == "muscle_gain" else 0.12
            if protein_pct < min_pct:
                penalise("insufficient_protein", "medium", 8, "Protein",
                         f"Only {protein_pct:.0%} of energy is from protein "
                         f"(aim for at least {min_pct:.0%}).")
            else:
                score += 3
                factors.append({"factor": "Protein", "impact": 3,
                                "detail": f"Good protein content ({meal.total_protein:.0f} g)."})
            fibre_target = t["fibre"] * share
            if fibre < fibre_target * 0.5:
                penalise("insufficient_fibre", "low", 6, "Fibre",
                         f"{fibre:.1f} g fibre is low (aim for ~{fibre_target:.0f} g). "
                         f"Add vegetables, fruit or whole grains.")
            elif fibre >= fibre_target:
                score += 3
                factors.append({"factor": "Fibre", "impact": 3,
                                "detail": f"Good fibre content ({fibre:.1f} g)."})

        # Dietary-restriction conflicts
        conflicts: list[ConflictResult] = []
        for item in meal.items:
            for c in food_conflicts(item.food, self.profile):
                if not any(x.kind == c.kind and x.tag == c.tag for x in conflicts):
                    conflicts.append(c)
        for c in conflicts:
            points = {"allergy": 40, "religious": 40, "diet": 20}[c.kind]
            if c.severity == "medium" and c.kind != "diet":
                points = 20
            penalise(f"{c.kind}_conflict", c.severity, points,
                     {"allergy": "Allergy", "religious": "Religious restriction",
                      "diet": "Diet preference"}[c.kind], c.message)
        if any(c.kind in ("allergy", "religious") and c.severity == "high" for c in conflicts):
            score = min(score, 30)

        return round(max(0.0, min(100.0, score)), 2), factors, risks, conflicts

    # ---- feedback ----
    def generate_feedback(self, meal, score, factors, risks, alternatives) -> dict:
        grade, label = grade_for(score)
        goal_text = {"weight_loss": "weight-loss", "muscle_gain": "muscle-building",
                     "maintenance": "maintenance"}.get(self.user.health_goal, "")
        negatives = [f for f in factors if f["impact"] < 0]
        if not negatives:
            summary = (f"{label} choice! This {meal.meal_category} fits your {goal_text} goal "
                       f"and dietary profile.")
        else:
            worst = sorted(negatives, key=lambda f: f["impact"])[0]
            summary = (f"{label} meal for your {goal_text} goal. Main concern: "
                       f"{worst['factor'].lower()} — {worst['detail']}")
        return {"grade": grade, "summary": summary, "factors": factors,
                "alternatives": alternatives}

    # ---- alternatives ----
    def suggest_healthy_alternatives(self, meal: Meal, risk_types: list[str],
                                     conflicts: list[ConflictResult], limit: int = 3) -> list[dict]:
        if not risk_types:
            return []
        main = max(meal.items, key=lambda i: i.calories or 0).food
        in_meal = {i.food_id for i in meal.items}
        nutrient_risks = [r for r in risk_types if r in RISK_NUTRIENT]
        key, direction = RISK_NUTRIENT[nutrient_risks[0]] if nutrient_risks else (None, None)

        candidates = []
        for f in self.db.scalars(select(FoodItem)):
            if f.food_id in in_meal or f.food_category == "Scanned Product":
                continue
            if food_conflicts(f, self.profile):
                continue
            if key:
                base, val = getattr(main, key) or 0, getattr(f, key) or 0
                better = val <= base * 0.8 if direction == "lower" else val >= base * 1.2 + 0.5
                if not better:
                    continue
            same = f.food_category == main.food_category
            candidates.append((same, health_index(f), f))
        candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)

        out = []
        for _, _, f in candidates[:limit]:
            if key:
                reason = f"{REASON[key]} than {main.food_name}"
            else:
                reason = "fits your dietary profile"
            out.append({"food_id": f.food_id, "food_name": f.food_name, "reason": reason})
        return out


def feedback_of(ms: MealScore) -> dict:
    try:
        return json.loads(ms.feedback_text)
    except (TypeError, ValueError):
        return {"grade": grade_for(ms.overall_score)[0], "summary": ms.feedback_text or "",
                "factors": [], "alternatives": []}


# Conflict check for an item that isn't in the database yet (e.g. a scanned label)
def conflicts_for_text(tags: set[str], text: str, user: User, subject: str) -> list[dict]:
    return [c.as_dict() for c in check_conflicts(tags, text, user.profile, subject)]


__all__ = ["MealScoringEngine", "feedback_of", "grade_for", "food_tags", "conflicts_for_text"]
