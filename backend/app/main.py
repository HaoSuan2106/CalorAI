"""CalorAI backend API. Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .routers import (auth, dashboard, dietary, foods, label_scan, meals, notifications,
                      recognition, users)
from .services.food_recognition_service import FoodRecognitionService
from .services.nutrition_label_scanner import tesseract_available

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    FoodRecognitionService.warm_up_in_background()
    yield


app = FastAPI(title="CalorAI API", version="1.0.0", lifespan=lifespan,
              description="AI-Powered Calorie Counter and Nutrition Tracking System")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for r in (auth, users, dietary, foods, meals, recognition, label_scan, notifications, dashboard):
    app.include_router(r.router)


@app.get("/", tags=["Health"])
def health():
    return {
        "status": "ok",
        "app": "CalorAI",
        "food_model_loaded": FoodRecognitionService.is_loaded(),
        "food_model_file_found": FoodRecognitionService.is_available(),
        "tesseract_available": tesseract_available(),
    }
