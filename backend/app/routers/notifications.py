"""Notification & Alert module."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification, User
from ..schemas import NotificationOut
from ..security import get_current_user
from ..services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notification & Alert"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(limit: int = 100, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    NotificationService(db, user).check_meal_reminders()
    return list(db.scalars(select(Notification)
                           .where(Notification.user_id == user.user_id)
                           .order_by(Notification.created_at.desc(),
                                     Notification.notification_id.desc())
                           .limit(min(limit, 500))))


@router.get("/unread-count")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    NotificationService(db, user).check_meal_reminders()
    ids = db.scalars(select(Notification.notification_id).where(
        Notification.user_id == user.user_id, Notification.is_read.is_(False))).all()
    return {"unread": len(ids)}


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_as_read(notification_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.user_id:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return n


@router.post("/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.user_id)
               .values(is_read=True))
    db.commit()
    return {"ok": True}
