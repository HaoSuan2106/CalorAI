"""Label Scanning Controller (Figure 4.13): scanLabel(image)."""
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..models import User
from ..security import get_current_user
from ..services.dietary_profile_service import (ALLERGEN_TAGS, check_conflicts, tags_in_text)
from ..services.nutrition_label_scanner import OCRNotAvailable, accuracy_label, scan_label
from .recognition import read_image

router = APIRouter(prefix="/label-scan", tags=["Nutrition Label Scanning"])


def categorise_ingredients(ingredients: list[str], user: User) -> list[dict]:
    out = []
    for name in ingredients:
        tags = tags_in_text(name)
        conflicts = check_conflicts(tags, name, user.profile, subject=name)
        if any(c.kind == "allergy" for c in conflicts):
            category = "allergy"
        elif conflicts:
            category = "restricted"
        elif tags & ALLERGEN_TAGS:
            category = "common_allergen"
        else:
            category = "safe"
        out.append({"name": name, "tags": sorted(tags), "category": category,
                    "message": conflicts[0].message if conflicts else None})
    return out


@router.post("")
async def scan(image: UploadFile = File(...), user: User = Depends(get_current_user)):
    data = await read_image(image)
    started = time.perf_counter()
    try:
        result = await run_in_threadpool(scan_label, data)
    except OCRNotAvailable as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    conflicts = check_conflicts(result.tags, " ".join(result.ingredients), user.profile,
                                subject="This product")
    return {
        "confidence": round(result.confidence, 3),
        "accuracy": accuracy_label(result.confidence),
        "attempts": result.attempts,
        "nutrition": result.nutrition,
        "ingredients": categorise_ingredients(result.ingredients, user),
        "tags": sorted(result.tags),
        "conflicts": [c.as_dict() for c in conflicts],
        "raw_text": result.raw_text,
        "processing_ms": round((time.perf_counter() - started) * 1000),
    }
