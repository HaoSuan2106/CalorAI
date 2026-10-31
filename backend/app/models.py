"""SQLAlchemy entities — one class per table in the data dictionary (Tables 4.5–4.15)."""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Integer, Numeric,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def Dec(p=6, s=2):
    return Numeric(p, s, asdecimal=False)


class User(Base):
    __tablename__ = "user"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(20))
    height_cm: Mapped[float] = mapped_column(Dec(5, 2))
    weight_kg: Mapped[float] = mapped_column(Dec(5, 2))
    activity_level: Mapped[str] = mapped_column(String(30), default="moderate")
    health_goal: Mapped[str] = mapped_column(String(50), default="maintenance")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    profile: Mapped["DietaryProfile"] = relationship(back_populates="user", uselist=False,
                                                     cascade="all, delete-orphan")
    meals: Mapped[list["Meal"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user",
                                                               cascade="all, delete-orphan")
    summaries: Mapped[list["DailySummary"]] = relationship(back_populates="user",
                                                           cascade="all, delete-orphan")


class DietaryProfile(Base):
    __tablename__ = "dietary_profile"

    profile_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.user_id", ondelete="CASCADE"), unique=True)
    religious_restriction: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    diet_preference: Mapped[str] = mapped_column(String(20), default="none")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    user: Mapped[User] = relationship(back_populates="profile")
    allergies: Mapped[list["Allergy"]] = relationship(back_populates="profile",
                                                      cascade="all, delete-orphan")
    medical_conditions: Mapped[list["MedicalCondition"]] = relationship(back_populates="profile",
                                                                        cascade="all, delete-orphan")


class Allergy(Base):
    __tablename__ = "allergy"

    allergy_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("dietary_profile.profile_id", ondelete="CASCADE"))
    allergen_name: Mapped[str] = mapped_column(String(50))

    profile: Mapped[DietaryProfile] = relationship(back_populates="allergies")


class MedicalCondition(Base):
    __tablename__ = "medical_condition"

    condition_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("dietary_profile.profile_id", ondelete="CASCADE"))
    condition_name: Mapped[str] = mapped_column(String(50))

    profile: Mapped[DietaryProfile] = relationship(back_populates="medical_conditions")


class FoodItem(Base):
    __tablename__ = "food_item"

    food_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    food_name: Mapped[str] = mapped_column(String(100), index=True)
    food_category: Mapped[str] = mapped_column(String(50))
    calories_per_100g: Mapped[float] = mapped_column(Dec(), default=0)
    carbs_per_100g: Mapped[float] = mapped_column(Dec(), default=0)
    protein_per_100g: Mapped[float] = mapped_column(Dec(), default=0)
    fat_per_100g: Mapped[float] = mapped_column(Dec(), default=0)
    sugar_per_100g: Mapped[float] = mapped_column(Dec(), default=0)
    sodium_per_100g: Mapped[float] = mapped_column(Dec(), default=0)  # mg
    fibre_per_100g: Mapped[float] = mapped_column(Dec(), default=0)
    # Comma-separated ingredient tags. Besides allergens (peanuts, dairy, ...) this also
    # carries the religious/diet tags (pork, alcohol, beef, chicken, ...) used for conflict checks.
    allergen_tags: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="")

    @property
    def tags(self) -> set[str]:
        return {t.strip().lower() for t in (self.allergen_tags or "").split(",") if t.strip()}


class Meal(Base):
    __tablename__ = "meal"

    meal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.user_id", ondelete="CASCADE"), index=True)
    meal_category: Mapped[str] = mapped_column(String(20))
    meal_datetime: Mapped[datetime] = mapped_column(DateTime, index=True)
    source_type: Mapped[str] = mapped_column(String(20))
    total_calories: Mapped[float] = mapped_column(Dec(), default=0)
    total_carbs: Mapped[float] = mapped_column(Dec(), default=0)
    total_protein: Mapped[float] = mapped_column(Dec(), default=0)
    total_fat: Mapped[float] = mapped_column(Dec(), default=0)
    total_sugar: Mapped[float] = mapped_column(Dec(), default=0)
    total_sodium: Mapped[float] = mapped_column(Dec(), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    user: Mapped[User] = relationship(back_populates="meals")
    items: Mapped[list["MealItem"]] = relationship(back_populates="meal", cascade="all, delete-orphan")
    score: Mapped[Optional["MealScore"]] = relationship(back_populates="meal", uselist=False,
                                                        cascade="all, delete-orphan")

    def calculate_total_nutrition(self) -> None:
        for field in ("calories", "carbs", "protein", "fat", "sugar", "sodium"):
            setattr(self, f"total_{field}", round(sum(getattr(i, field) or 0 for i in self.items), 2))


class MealItem(Base):
    __tablename__ = "meal_item"

    meal_item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meal_id: Mapped[int] = mapped_column(ForeignKey("meal.meal_id", ondelete="CASCADE"), index=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("food_item.food_id"))
    portion_size_g: Mapped[float] = mapped_column(Dec())
    calories: Mapped[float] = mapped_column(Dec(), default=0)
    carbs: Mapped[float] = mapped_column(Dec(), default=0)
    protein: Mapped[float] = mapped_column(Dec(), default=0)
    fat: Mapped[float] = mapped_column(Dec(), default=0)
    sugar: Mapped[float] = mapped_column(Dec(), default=0)
    sodium: Mapped[float] = mapped_column(Dec(), default=0)

    meal: Mapped[Meal] = relationship(back_populates="items")
    food: Mapped[FoodItem] = relationship()


class MealScore(Base):
    __tablename__ = "meal_score"

    score_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meal_id: Mapped[int] = mapped_column(ForeignKey("meal.meal_id", ondelete="CASCADE"), unique=True)
    overall_score: Mapped[float] = mapped_column(Dec(5, 2))
    # JSON document: {"grade", "summary", "factors": [...], "alternatives": [...]}
    feedback_text: Mapped[str] = mapped_column(Text)

    meal: Mapped[Meal] = relationship(back_populates="score")
    risks: Mapped[list["NutritionRisk"]] = relationship(back_populates="score",
                                                        cascade="all, delete-orphan")


class NutritionRisk(Base):
    __tablename__ = "nutrition_risk"

    risk_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    score_id: Mapped[int] = mapped_column(ForeignKey("meal_score.score_id", ondelete="CASCADE"))
    risk_type: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(10))

    score: Mapped[MealScore] = relationship(back_populates="risks")


class Notification(Base):
    __tablename__ = "notification"

    notification_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.user_id", ondelete="CASCADE"), index=True)
    related_meal_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("meal.meal_id", ondelete="SET NULL"), nullable=True)
    notification_type: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(255))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    user: Mapped[User] = relationship(back_populates="notifications")


class DailySummary(Base):
    __tablename__ = "daily_summary"
    __table_args__ = (UniqueConstraint("user_id", "summary_date", name="uq_user_date"),)

    summary_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.user_id", ondelete="CASCADE"))
    summary_date: Mapped[date] = mapped_column(Date)
    total_calories: Mapped[float] = mapped_column(Dec(), default=0)
    total_carbs: Mapped[float] = mapped_column(Dec(), default=0)
    total_protein: Mapped[float] = mapped_column(Dec(), default=0)
    total_fat: Mapped[float] = mapped_column(Dec(), default=0)
    total_sugar: Mapped[float] = mapped_column(Dec(), default=0)
    total_sodium: Mapped[float] = mapped_column(Dec(), default=0)
    calorie_goal: Mapped[float] = mapped_column(Dec(), default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    user: Mapped[User] = relationship(back_populates="summaries")
