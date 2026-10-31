"""User Management Controller: registration and login (Figure 4.11)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DietaryProfile, User
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from ..security import create_access_token, hash_password, verify_password
from ..serializers import user_out

router = APIRouter(prefix="/auth", tags=["User Management"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "This email is already registered.")
    user = User(
        full_name=data.full_name, email=email, password_hash=hash_password(data.password),
        age=data.age, gender=data.gender, height_cm=data.height_cm, weight_kg=data.weight_kg,
        activity_level=data.activity_level, health_goal=data.health_goal,
    )
    user.profile = DietaryProfile(diet_preference="none")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    return TokenResponse(access_token=create_access_token(user.user_id), user=user_out(user))
