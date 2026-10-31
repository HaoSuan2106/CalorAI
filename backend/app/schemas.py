"""Request/response models. Pydantic validation is the system's Validation Service."""
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Gender = Literal["male", "female", "other"]
ActivityLevel = Literal["sedentary", "light", "moderate", "active", "very_active"]
HealthGoal = Literal["weight_loss", "maintenance", "muscle_gain"]
MealCategory = Literal["breakfast", "lunch", "dinner", "snack"]
SourceType = Literal["photo", "label_scan", "manual"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- User management ----------
class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    age: int = Field(ge=13, le=120)
    gender: Gender
    height_cm: float = Field(ge=80, le=250)
    weight_kg: float = Field(ge=25, le=300)
    activity_level: ActivityLevel = "moderate"
    health_goal: HealthGoal = "maintenance"

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Full name is required")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("Password must contain both letters and numbers")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    age: Optional[int] = Field(default=None, ge=13, le=120)
    gender: Optional[Gender] = None
    height_cm: Optional[float] = Field(default=None, ge=80, le=250)
    weight_kg: Optional[float] = Field(default=None, ge=25, le=300)
    activity_level: Optional[ActivityLevel] = None
    health_goal: Optional[HealthGoal] = None


class Targets(BaseModel):
    calories: float
    carbs: float
    protein: float
    fat: float
    sugar_limit: float
    sodium_limit: float
    fat_limit: float
    fibre: float


class UserOut(ORM):
    user_id: int
    full_name: str
    email: str
    age: int
    gender: str
    height_cm: float
    weight_kg: float
    activity_level: str
    health_goal: str
    created_at: datetime
    targets: Optional[Targets] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Dietary restriction profile ----------
class DietaryProfileIn(BaseModel):
    religious_restriction: Optional[str] = Field(default=None, max_length=50)
    diet_preference: str = Field(default="none", max_length=20)
    allergies: list[str] = Field(default_factory=list)
    medical_conditions: list[str] = Field(default_factory=list)

    @field_validator("allergies", "medical_conditions")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        seen, out = set(), []
        for item in v:
            item = item.strip()[:50]
            if item and item.lower() not in seen:
                seen.add(item.lower())
                out.append(item)
        return out


class DietaryProfileOut(DietaryProfileIn):
    profile_id: int
    updated_at: Optional[datetime] = None


class Conflict(BaseModel):
    kind: Literal["allergy", "religious", "diet"]
    tag: str
    severity: Literal["low", "medium", "high"]
    message: str


# ---------- Food items ----------
class NutritionValues(BaseModel):
    calories: float = Field(default=0, ge=0, le=9999)
    carbs: float = Field(default=0, ge=0, le=9999)
    protein: float = Field(default=0, ge=0, le=9999)
    fat: float = Field(default=0, ge=0, le=9999)
    sugar: float = Field(default=0, ge=0, le=9999)
    sodium: float = Field(default=0, ge=0, le=9999)  # mg
    fibre: float = Field(default=0, ge=0, le=9999)


class FoodItemOut(ORM):
    food_id: int
    food_name: str
    food_category: str
    calories_per_100g: float
    carbs_per_100g: float
    protein_per_100g: float
    fat_per_100g: float
    sugar_per_100g: float
    sodium_per_100g: float
    fibre_per_100g: float
    allergen_tags: Optional[str] = ""
    default_portion_g: float = 100
    conflicts: list[Conflict] = Field(default_factory=list)


class FoodCreate(NutritionValues):
    """Custom/scanned product. Nutrition values are per serving; stored per 100 g."""
    food_name: str = Field(min_length=1, max_length=100)
    food_category: str = Field(default="Scanned Product", max_length=50)
    serving_size_g: float = Field(gt=0, le=5000)
    tags: list[str] = Field(default_factory=list)
    ingredients_text: str = Field(default="", max_length=5000)


# ---------- Meals ----------
class MealItemIn(BaseModel):
    food_id: int
    portion_size_g: float = Field(gt=0, le=5000)
    # If the user edited the nutrition values ("Edit Details Manually"), they are stored as-is
    override: Optional[NutritionValues] = None


class MealCreate(BaseModel):
    meal_category: MealCategory
    source_type: SourceType = "manual"
    meal_datetime: Optional[datetime] = None
    items: list[MealItemIn] = Field(min_length=1, max_length=20)


class MealItemOut(ORM):
    meal_item_id: int
    food_id: int
    food_name: str = ""
    portion_size_g: float
    calories: float
    carbs: float
    protein: float
    fat: float
    sugar: float
    sodium: float


class RiskOut(ORM):
    risk_type: str
    severity: str


class ScoreFactor(BaseModel):
    factor: str
    impact: float
    detail: str


class Alternative(BaseModel):
    food_id: int
    food_name: str
    reason: str


class MealScoreOut(BaseModel):
    score_id: int
    overall_score: float
    grade: str
    summary: str
    factors: list[ScoreFactor]
    alternatives: list[Alternative]
    risks: list[RiskOut]


class MealOut(ORM):
    meal_id: int
    meal_category: str
    meal_datetime: datetime
    source_type: str
    total_calories: float
    total_carbs: float
    total_protein: float
    total_fat: float
    total_sugar: float
    total_sodium: float
    items: list[MealItemOut] = Field(default_factory=list)
    score: Optional[MealScoreOut] = None


class MealSaveResponse(MealOut):
    alerts: list["NotificationOut"] = Field(default_factory=list)


# ---------- Notifications ----------
class NotificationOut(ORM):
    notification_id: int
    related_meal_id: Optional[int] = None
    notification_type: str
    message: str
    is_read: bool
    created_at: datetime


MealSaveResponse.model_rebuild()


# ---------- Dashboard ----------
class DaySummaryOut(BaseModel):
    date: date
    calories: float
    carbs: float
    protein: float
    fat: float
    sugar: float
    sodium: float
    calorie_goal: float
    meals_logged: int = 0
    avg_score: Optional[float] = None
