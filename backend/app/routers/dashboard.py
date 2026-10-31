"""Dashboard & Analytics module."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import get_current_user
from ..serializers import meal_out
from ..services.dashboard_service import DashboardService, meals_between
from ..services.nutrition_goals import daily_targets

router = APIRouter(prefix="/dashboard", tags=["Dashboard & Analytics"])


@router.get("/today")
def today(day: date | None = None, user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    d = day or date.today()
    svc = DashboardService(db, user)
    summary = svc.get_daily_summary(d)
    targets = daily_targets(user)
    return {
        "summary": summary,
        "targets": targets,
        "remaining_calories": round(summary["calorie_goal"] - summary["calories"]),
        "meals": [meal_out(m) for m in meals_between(db, user, d, d)],
        "week": svc.get_progress_trend(7, d)["days"],
    }


@router.get("/progress")
def progress(period: Literal["week", "month", "quarter"] = "week",
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    days = {"week": 7, "month": 30, "quarter": 90}[period]
    return {"period": period, **DashboardService(db, user).get_progress_trend(days),
            "targets": daily_targets(user)}


@router.get("/weekly-report")
def weekly_report(end: date | None = None, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    return DashboardService(db, user).weekly_report(end)
