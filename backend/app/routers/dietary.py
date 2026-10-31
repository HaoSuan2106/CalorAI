"""Dietary Restriction Profile module."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Allergy, MedicalCondition, User
from ..schemas import DietaryProfileIn, DietaryProfileOut
from ..security import get_current_user
from ..services.dietary_profile_service import (COMMON_ALLERGENS, COMMON_CONDITIONS,
                                                DIET_OPTIONS, RELIGIOUS_OPTIONS,
                                                get_or_create_profile)

router = APIRouter(prefix="/dietary-profile", tags=["Dietary Restriction Profile"])


def _out(p) -> DietaryProfileOut:
    return DietaryProfileOut(
        profile_id=p.profile_id,
        religious_restriction=p.religious_restriction,
        diet_preference=p.diet_preference or "none",
        allergies=[a.allergen_name for a in p.allergies],
        medical_conditions=[c.condition_name for c in p.medical_conditions],
        updated_at=p.updated_at,
    )


@router.get("/options")
def options():
    return {
        "allergens": COMMON_ALLERGENS,
        "religious": [{"value": k, "label": v} for k, v in RELIGIOUS_OPTIONS.items()],
        "diets": [{"value": k, "label": v} for k, v in DIET_OPTIONS.items()],
        "medical_conditions": COMMON_CONDITIONS,
    }


@router.get("", response_model=DietaryProfileOut)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(get_or_create_profile(db, user))


@router.put("", response_model=DietaryProfileOut)
def save_profile(data: DietaryProfileIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    rel = (data.religious_restriction or "").strip().lower() or None
    if rel is not None and rel not in RELIGIOUS_OPTIONS:
        raise HTTPException(422, f"Unknown religious restriction '{rel}'")
    diet = data.diet_preference.strip().lower()
    if diet not in DIET_OPTIONS:
        raise HTTPException(422, f"Unknown diet preference '{diet}'")

    p = get_or_create_profile(db, user)
    p.religious_restriction = rel
    p.diet_preference = diet
    p.allergies = [Allergy(allergen_name=a) for a in data.allergies]
    p.medical_conditions = [MedicalCondition(condition_name=c) for c in data.medical_conditions]
    db.commit()
    db.refresh(p)
    return _out(p)
