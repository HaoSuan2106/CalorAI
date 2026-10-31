"""Dashboard Service: daily summaries, progress trends and the weekly report."""
from collections import Counter
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import DailySummary, Meal, MealScore, Notification, NutritionRisk, User
from .nutrition_goals import calorie_goal

FIELDS = ("calories", "carbs", "protein", "fat", "sugar", "sodium")


def _day_bounds(d: date) -> tuple[datetime, datetime]:
    return datetime.combine(d, time.min), datetime.combine(d, time.max)


def meals_between(db: Session, user: User, start: date, end: date) -> list[Meal]:
    return list(db.scalars(
        select(Meal)
        .where(Meal.user_id == user.user_id,
               Meal.meal_datetime >= datetime.combine(start, time.min),
               Meal.meal_datetime <= datetime.combine(end, time.max))
        .options(selectinload(Meal.items), selectinload(Meal.score))
        .order_by(Meal.meal_datetime)
    ))


class DashboardService:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    def refresh_daily_summary(self, d: date) -> DailySummary:
        meals = meals_between(self.db, self.user, d, d)
        summary = self.db.scalar(select(DailySummary).where(
            DailySummary.user_id == self.user.user_id, DailySummary.summary_date == d))
        if summary is None:
            summary = DailySummary(user_id=self.user.user_id, summary_date=d)
            self.db.add(summary)
        for f in FIELDS:
            # DECIMAL(6,2) column: cap at the column maximum
            setattr(summary, f"total_{f}",
                    min(round(sum(getattr(m, f"total_{f}") or 0 for m in meals), 2), 9999.99))
        summary.calorie_goal = calorie_goal(self.user)
        summary.generated_at = datetime.now()
        self.db.flush()
        return summary

    def get_daily_summary(self, d: date) -> dict:
        s = self.db.scalar(select(DailySummary).where(
            DailySummary.user_id == self.user.user_id, DailySummary.summary_date == d))
        meals = meals_between(self.db, self.user, d, d)
        scores = [m.score.overall_score for m in meals if m.score]
        base = {f: (getattr(s, f"total_{f}") if s else 0.0) for f in FIELDS}
        return {"date": d, **base,
                "calorie_goal": s.calorie_goal if s else calorie_goal(self.user),
                "meals_logged": len(meals),
                "avg_score": round(sum(scores) / len(scores), 1) if scores else None}

    def get_progress_trend(self, days: int, end: date | None = None) -> dict:
        end = end or date.today()
        start = end - timedelta(days=days - 1)
        rows = {s.summary_date: s for s in self.db.scalars(select(DailySummary).where(
            DailySummary.user_id == self.user.user_id,
            DailySummary.summary_date.between(start, end)))}
        meals = meals_between(self.db, self.user, start, end)
        by_day_scores: dict[date, list[float]] = {}
        by_day_count: Counter = Counter()
        for m in meals:
            d = m.meal_datetime.date()
            by_day_count[d] += 1
            if m.score:
                by_day_scores.setdefault(d, []).append(m.score.overall_score)

        goal_now = calorie_goal(self.user)
        series = []
        for i in range(days):
            d = start + timedelta(days=i)
            s = rows.get(d)
            sc = by_day_scores.get(d)
            series.append({
                "date": d, **{f: (getattr(s, f"total_{f}") if s else 0.0) for f in FIELDS},
                "calorie_goal": s.calorie_goal if s else goal_now,
                "meals_logged": by_day_count[d],
                "avg_score": round(sum(sc) / len(sc), 1) if sc else None,
            })

        logged = [x for x in series if x["meals_logged"]]
        within = [x for x in logged if x["calories"] <= x["calorie_goal"] * 1.05]
        all_scores = [m.score.overall_score for m in meals if m.score]
        streak = 0
        for x in reversed(series):
            if not x["meals_logged"]:
                break
            streak += 1
        n = len(logged) or 1
        return {
            "days": series,
            "stats": {
                "days_logged": len(logged),
                "days_within_goal": len(within),
                "avg_calories": round(sum(x["calories"] for x in logged) / n, 1),
                "avg_protein": round(sum(x["protein"] for x in logged) / n, 1),
                "avg_sugar": round(sum(x["sugar"] for x in logged) / n, 1),
                "avg_sodium": round(sum(x["sodium"] for x in logged) / n, 1),
                "avg_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
                "logging_streak": streak,
            },
        }

    def weekly_report(self, end: date | None = None) -> dict:
        end = end or date.today()
        start = end - timedelta(days=6)
        trend = self.get_progress_trend(7, end)
        logged = [d for d in trend["days"] if d["meals_logged"]] or [None]
        n = len(logged) if logged[0] else 1
        avg = {f: (sum(d[f] for d in logged) / n if logged[0] else 0) for f in ("carbs", "protein", "fat")}
        energy = {"carbs": avg["carbs"] * 4, "protein": avg["protein"] * 4, "fat": avg["fat"] * 9}
        total_e = sum(energy.values()) or 1

        risks = self.db.execute(
            select(NutritionRisk.risk_type, NutritionRisk.severity)
            .join(MealScore, MealScore.score_id == NutritionRisk.score_id)
            .join(Meal, Meal.meal_id == MealScore.meal_id)
            .where(Meal.user_id == self.user.user_id,
                   Meal.meal_datetime.between(*(_day_bounds(start)[0], _day_bounds(end)[1])))
        ).all()
        risk_counts: dict[str, dict[str, int]] = {}
        for rtype, sev in risks:
            risk_counts.setdefault(rtype, {"low": 0, "medium": 0, "high": 0})
            risk_counts[rtype][sev] = risk_counts[rtype].get(sev, 0) + 1

        alerts = Counter(self.db.scalars(
            select(Notification.notification_type).where(
                Notification.user_id == self.user.user_id,
                Notification.created_at.between(_day_bounds(start)[0], _day_bounds(end)[1]))))

        return {
            "start_date": start,
            "end_date": end,
            "calorie_trend": [{"date": d["date"], "calories": d["calories"],
                               "calorie_goal": d["calorie_goal"]} for d in trend["days"]],
            "macro_distribution": {
                k: {"avg_grams": round(avg[k], 1), "percent": round(energy[k] / total_e * 100, 1)}
                for k in energy},
            "risk_summary": [{"risk_type": k, **v} for k, v in sorted(risk_counts.items())],
            "alerts_breakdown": {
                "meal_reminder": alerts.get("meal_reminder", 0),
                "allergy_religious": (alerts.get("allergy_alert", 0) + alerts.get("religious_alert", 0)
                                      + alerts.get("diet_alert", 0)),
                "excess_nutrition": alerts.get("excess_nutrition_alert", 0),
            },
            "stats": trend["stats"],
        }
