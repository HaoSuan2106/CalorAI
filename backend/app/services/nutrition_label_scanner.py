"""Nutrition Label Scanner: image preprocessing -> Tesseract OCR -> structured nutrition values
and ingredient list.

Flow (Figure 4.13): preprocess (deskew, denoise, contrast) -> extractText(); retried with a
different preprocessing variant while OCR confidence < 0.7 and attempts < 3 -> parse values.
"""
import io
import re
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageOps

from ..config import settings
from .dietary_profile_service import ALLERGEN_TAGS, tags_in_text

MIN_CONFIDENCE = 0.70
MAX_ATTEMPTS = 3


class OCRNotAvailable(RuntimeError):
    pass


# ----------------------------------------------------------------- image preprocessing
def _load_gray(image_bytes: bytes) -> np.ndarray:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:  # noqa: BLE001
        raise ValueError("Unsupported or corrupted image file") from e
    gray = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    longest = max(h, w)
    if longest < 1500:  # Tesseract works best when text is ~30 px high
        f = 1800 / longest
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    elif longest > 2600:
        f = 2400 / longest
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return gray


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Projection-profile deskew: the rotation that gives the sharpest text-line profile."""
    h, w = gray.shape
    f = 800 / max(h, w)
    small = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    sh, sw = bw.shape
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-10, 10.5, 1.0):
        m = cv2.getRotationMatrix2D((sw / 2, sh / 2), float(angle), 1.0)
        rot = cv2.warpAffine(bw, m, (sw, sh), flags=cv2.INTER_NEAREST, borderValue=0)
        score = float(np.var(rot.sum(axis=1, dtype=np.float64)))
        if score > best_score:
            best_angle, best_score = float(angle), score
    if best_angle == 0:
        return gray
    m = cv2.getRotationMatrix2D((w / 2, h / 2), best_angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def preprocess_image(image_bytes: bytes) -> list[tuple[str, np.ndarray, int]]:
    """Returns preprocessing variants in the order they are tried: (name, image, psm)."""
    gray = _deskew(_load_gray(image_bytes))
    denoised = cv2.medianBlur(gray, 3)
    contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised)
    _, otsu = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(contrast, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 31, 10)
    return [("otsu", otsu, 6), ("adaptive", adaptive, 6), ("contrast", contrast, 4)]


# ----------------------------------------------------------------- OCR
def _tesseract():
    import pytesseract
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    try:
        pytesseract.get_tesseract_version()
    except Exception as e:  # noqa: BLE001
        raise OCRNotAvailable(
            "Tesseract OCR is not installed or TESSERACT_CMD in .env is wrong.") from e
    return pytesseract


def tesseract_available() -> bool:
    try:
        _tesseract()
        return True
    except OCRNotAvailable:
        return False


def extract_text(image: np.ndarray, psm: int = 6) -> tuple[str, float]:
    """Returns (text with line breaks, mean word confidence 0-1)."""
    pt = _tesseract()
    data = pt.image_to_data(image, lang="eng", config=f"--oem 3 --psm {psm}",
                            output_type=pt.Output.DICT)
    lines: dict[tuple, list[str]] = {}
    confs = []
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        confs.append(conf)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
    text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
    return text, (sum(confs) / len(confs) / 100 if confs else 0.0)


# ----------------------------------------------------------------- parsing
NUTRIENT_LINES = [
    # key, label pattern, exclude pattern
    ("calories", r"\b(energy|calories?|kalori|tenaga)\b", None),
    ("fibre", r"\b(dietary\s+)?fib(re|er)\b|\bserat\b", None),
    ("sugar", r"\b(total\s+)?sugars?\b|\bgula\b", r"\badded\b|\bincludes?\b|\balcohols?\b"),
    ("carbs", r"\b(total\s+)?carbohydrates?\b|\bkarbohidrat\b|\bcarbs?\b", None),
    ("protein", r"\bprotein\b", None),
    ("fat", r"\b(total\s+)?fat\b|\blemak\b",
     r"saturated|\btrans\b|mono|poly|\btepu\b|from\s+fat"),
    ("sodium", r"\b(sodium|natrium)\b", None),
]
NUMBER = re.compile(r"(\d+(?:\.\d+)?)\s*(kcal|cal|kj|mg|g|ml|%)?", re.IGNORECASE)


def _clean_line(line: str) -> str:
    line = re.sub(r"calories\s+from\s+fat\s*\d*", " ", line, flags=re.IGNORECASE)
    # common OCR confusions inside numbers: O->0, l/I->1, comma decimals
    line = re.sub(r"(?<=\d)[oO]|[oO](?=\d)", "0", line)
    line = re.sub(r"\b[oO](?=\s*(m?g|kcal|%)\b)", "0", line)
    line = re.sub(r"(?<=\d)[lI|]|[lI|](?=\d)", "1", line)
    line = re.sub(r"(\d),(\d{3})\b", r"\1\2", line)   # 1,050 kJ -> 1050
    line = re.sub(r"(\d),(\d{1,2})\b", r"\1.\2", line)  # 3,5 g -> 3.5
    line = line.replace("<", "")
    return line


def _column_order(text: str) -> list[str]:
    """Which basis each numeric column is: ['per_100g', 'per_serving'] etc."""
    t = text.lower()
    p100 = re.search(r"per\s*100\s*(g|ml)|\b100\s*(g|ml)\b|setiap\s*100", t)
    pserv = re.search(r"per\s*(serving|hidangan|sajian)|amount\s+per\s+serving|setiap\s+hidangan", t)
    if p100 and pserv:
        return ["per_100g", "per_serving"] if p100.start() < pserv.start() else ["per_serving", "per_100g"]
    if p100:
        return ["per_100g"]
    return ["per_serving"]


def _serving_size(text: str) -> float | None:
    t = text.lower()
    for pat in (r"(serving\s*size|saiz\s*hidangan|saiz\s*sajian)[^\n]{0,40}?(\d+(?:\.\d+)?)\s*(g|ml)\b",
                r"per\s*(serving|hidangan|sajian)\s*\(?\s*(\d+(?:\.\d+)?)\s*(g|ml)\b"):
        m = re.search(pat, t)
        if m:
            val = float(m.group(2))
            if 1 <= val <= 2000:
                return val
    return None


def parse_nutrition_values(raw_text: str) -> dict:
    columns = _column_order(raw_text)
    serving = _serving_size(raw_text)
    cols: dict[str, dict[str, float]] = {"per_100g": {}, "per_serving": {}}

    for raw_line in raw_text.splitlines():
        line = _clean_line(raw_line)
        low = line.lower()
        if low.count(",") >= 3 or _INGREDIENT_START.search(low):
            continue  # ingredient list, not a nutrition row
        for key, label, exclude in NUTRIENT_LINES:
            m = re.search(label, low)
            if not m or (exclude and re.search(exclude, low)):
                continue
            if key in cols[columns[0]]:
                break  # first matching line wins (e.g. 'Total Sugars' before 'Added Sugars')
            values = []
            for num in NUMBER.finditer(low[m.end():]):
                unit = (num.group(2) or "").lower()
                if unit == "%":
                    continue
                values.append((float(num.group(1)), unit))
            if key == "calories":
                kcal = [v for v, u in values if u in ("kcal", "cal")]
                kj = [v / 4.184 for v, u in values if u == "kj"]
                nums = kcal or kj or [v for v, u in values if u == ""]
            elif key == "sodium":
                nums = [v * 1000 if u == "g" else v for v, u in values]
            else:
                nums = [v for v, u in values if u in ("g", "")]
            for col, v in zip(columns, nums):
                cols[col][key] = round(v, 2)
            break  # one nutrient per line

    found = sorted(set(cols["per_100g"]) | set(cols["per_serving"]))
    keys = ["calories", "carbs", "protein", "fat", "sugar", "sodium", "fibre"]
    size = serving or 100.0
    per_100g, per_serving = {}, {}
    for k in keys:
        if k in cols["per_100g"]:
            per_100g[k] = cols["per_100g"][k]
            per_serving[k] = cols["per_serving"].get(k, round(per_100g[k] * size / 100, 2))
        elif k in cols["per_serving"]:
            per_serving[k] = cols["per_serving"][k]
            per_100g[k] = round(per_serving[k] * 100 / size, 2)
        else:
            per_100g[k] = per_serving[k] = 0.0
    return {
        "serving_size_g": serving,
        "basis": "per_serving" if serving else "per_100g",
        "per_serving": per_serving,
        "per_100g": per_100g,
        "found": found,
        "missing": [k for k in keys if k not in found],
    }


_INGREDIENT_START = re.compile(r"\b(ingredients?|bahan[\s-]*bahan|ramuan|kandungan)\b\s*[:;.\-]?\s*",
                               re.IGNORECASE)
_INGREDIENT_STOP = re.compile(
    r"\n\s*\n|\b(allergens?|contains|mengandungi|may\s+contain|nutrition|maklumat\s+pemakanan|"
    r"storage|store\s+in|best\s+before|manufactured|produced\s+by|net\s+w(eigh)?t|berat\s+bersih)\b",
    re.IGNORECASE)
_CONTAINS = re.compile(r"\b(contains?|mengandungi|allergens?(\s+information)?)\b\s*[:\-]?\s*([^\n]+)",
                       re.IGNORECASE)


def _split_top_level(body: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in body:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch in ",;" and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    out = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip(" .:-*")
        if 1 < len(p) <= 80:
            out.append(p)
    return out[:60]


def parse_ingredient_list(raw_text: str) -> dict:
    ingredients: list[str] = []
    m = _INGREDIENT_START.search(raw_text)
    if m:
        body = raw_text[m.end():]
        stop = _INGREDIENT_STOP.search(body)
        if stop:
            body = body[:stop.start()]
        ingredients = _split_top_level(body.replace("\n", " "))
    contains_tags: set[str] = set()
    for cm in _CONTAINS.finditer(raw_text):
        contains_tags |= tags_in_text(cm.group(3))
    return {"ingredients": ingredients, "contains_tags": sorted(contains_tags)}


@dataclass
class ScanResult:
    raw_text: str
    confidence: float
    attempts: int
    nutrition: dict
    ingredients: list[str]
    tags: set[str] = field(default_factory=set)


def scan_label(image_bytes: bytes) -> ScanResult:
    best_text, best_conf, attempts = "", -1.0, 0
    for _, img, psm in preprocess_image(image_bytes)[:MAX_ATTEMPTS]:
        attempts += 1
        text, conf = extract_text(img, psm)
        if conf > best_conf:
            best_text, best_conf = text, conf
        if conf >= MIN_CONFIDENCE:
            break
    nutrition = parse_nutrition_values(best_text)
    ing = parse_ingredient_list(best_text)
    tags = set(ing["contains_tags"])
    for i in ing["ingredients"]:
        tags |= tags_in_text(i)
    return ScanResult(best_text, max(best_conf, 0.0), attempts, nutrition, ing["ingredients"], tags)


def accuracy_label(conf: float) -> str:
    return "high" if conf >= 0.8 else "medium" if conf >= MIN_CONFIDENCE else "low"


__all__ = ["scan_label", "parse_nutrition_values", "parse_ingredient_list", "accuracy_label",
           "OCRNotAvailable", "tesseract_available", "ALLERGEN_TAGS"]
