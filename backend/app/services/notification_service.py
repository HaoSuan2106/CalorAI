"""Notification Service: meal reminders, dietary-conflict alerts and excess-nutrition alerts."""
from datetime import date, datetime, time

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..models import DailySummary, Meal, Notification, User
from .dietary_profile_service import ConflictResult
from .nutrition_goals import daily_targets

MEAL_REMINDER_DEADLINES = {
    "breakfast": time(10, 30),
    "lunch": time(14, 30),
    "dinner": time(20, 30),
}
CONFLICT_TYPES = {"allergy": "allergy_alert", "religious": "religious_alert", "diet": "diet_alert"}


class NotificationService:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    def _create(self, ntype: str, message: str, meal_id: int | None = None) -> Notification:
        n = Notification(user_id=self.user.user_id, related_meal_id=meal_id,
                         notification_type=ntype, message=message[:255], is_read=False,
                         created_at=datetime.now())
        self.db.add(n)
        return n

    def _exists_today(self, ntype: str, message_prefix: str, day: date) -> bool:
        start = datetime.combine(day, time.min)
        end = datetime.combine(day, time.max)
        q = select(Notification.notification_id).where(and_(
            Notification.user_id == self.user.user_id,
            Notification.notification_type == ntype,
            Notification.message.like(f"{message_prefix}%"),
            Notification.created_at.between(start, end),
        ))
        return self.db.scalar(q) is not None

    # --- dietary conflicts (allergy / religious / diet) ---
    def send_conflict_alerts(self, meal: Meal, conflicts: list[ConflictResult]) -> list[Notification]:
        return [self._create(CONFLICT_TYPES[c.kind], f"Alert: {c.message}", meal.meal_id)
                for c in conflicts]

    # --- excess nutrition vs daily limits ---
    def send_excess_nutrition_alerts(self, summary: DailySummary, meal: Meal | None) -> list[Notification]:
        t = daily_targets(self.user)
        checks = [
            ("Daily calorie goal exceeded", summary.total_calories, t["calories"], "kcal"),
            ("Daily sugar limit exceeded", summary.total_sugar, t["sugar_limit"], "g"),
            ("Daily sodium limit exceeded", summary.total_sodium, t["sodium_limit"], "mg"),
            ("Daily fat limit exceeded", summary.total_fat, t["fat_limit"], "g"),
        ]
        out = []
        for title, value, limit, unit in checks:
            if value > limit and not self._exists_today("excess_nutrition_alert", title,
                                                        summary.summary_date):
                msg = (f"{title}: you've had {value:.0f} {unit} today (limit {limit:.0f} {unit}). "
                       f"Choose lighter options for the rest of the day.")
                out.append(self._create("excess_nutrition_alert", msg,
                                        meal.meal_id if meal else None))
        return out

    # --- meal reminders (FR 1.3.7.1) ---
    def check_meal_reminders(self, now: datetime | None = None) -> list[Notification]:
        now = now or datetime.now()
        today = now.date()
        start = datetime.combine(today, time.min)
        logged = set(self.db.scalars(select(Meal.meal_category).where(
            Meal.user_id == self.user.user_id, Meal.meal_datetime >= start)))
        out = []
        for category, deadline in MEAL_REMINDER_DEADLINES.items():
            deadline_dt = datetime.combine(today, deadline)
            if now < deadline_dt or deadline_dt < self.user.created_at or category in logged:
                continue
            title = f"Don't forget to log your {category}"
            if not self._exists_today("meal_reminder", title, today):
                out.append(self._create("meal_reminder",
                                        f"{title}! Consistent logging keeps your insights accurate."))
        if out:
            self.db.commit()
        return out
