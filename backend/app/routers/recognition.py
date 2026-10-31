"""Food Recognition Controller (Figure 4.12): recognizeFood(image)."""
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import FoodItem, User
from ..security import get_current_user
from ..serializers import food_out
from ..services.food_recognition_service import (FoodRecognitionService, ModelNotAvailable,
                                                 match_food_name)
from ..services.meal_logging_service import nutrition_for_portion

router = APIRouter(prefix="/recognition", tags=["Food Recognition"])

LOW_CONFIDENCE = 0.5


async def read_image(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty image")
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Image is larger than {settings.MAX_UPLOAD_MB} MB")
    return data


@router.get("/status")
def status():
    return {"model_file_found": FoodRecognitionService.is_available(),
            "model_loaded": FoodRecognitionService.is_loaded(),
            "error": FoodRecognitionService._load_error}


@router.post("/predict")
async def recognize_food(image: UploadFile = File(...), user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    data = await read_image(image)
    started = time.perf_counter()
    try:
        preds = await run_in_threadpool(FoodRecognitionService.classify_food, data, 3)
    except ModelNotAvailable as e:
        raise HTTPException(503, str(e))
    except Exception as e:  # noqa: BLE001 — e.g. unreadable image
        raise HTTPException(400, f"Could not process the image: {e}")

    foods = list(db.scalars(select(FoodItem)))
    by_name = {f.food_name: f for f in foods}
    names = list(by_name)
    predictions = []
    for p in preds:
        name = match_food_name(p.label, names)
        food = by_name.get(name) if name else None
        entry = {"label": p.label, "confidence": round(p.confidence, 4), "food": None}
        if food:
            fo = food_out(food, user)
            entry["food"] = fo
            entry["default_portion_g"] = fo.default_portion_g
            entry["nutrition"] = nutrition_for_portion(food, fo.default_portion_g)
        predictions.append(entry)

    best = predictions[0] if predictions else None
    return {
        "predictions": predictions,
        "best": best,
        "low_confidence": best is None or best["confidence"] < LOW_CONFIDENCE or best["food"] is None,
        "processing_ms": round((time.perf_counter() - started) * 1000),
    }
