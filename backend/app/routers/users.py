"""Profile maintenance."""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import ProfileUpdate, UserOut
from ..security import get_current_user
from ..serializers import user_out
from ..services.dashboard_service import DashboardService

router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.put("/me", response_model=UserOut)
def update_me(data: ProfileUpdate, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.flush()
    # the calorie goal may have changed — keep today's summary consistent
    DashboardService(db, user).refresh_daily_summary(date.today())
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.delete("/me", status_code=204)
def delete_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Permanently deletes the account and all personal/health data (data-protection right)."""
    db.delete(user)
    db.commit()
