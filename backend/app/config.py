import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _path(value: str) -> str:
    """Resolve paths in .env relative to the backend folder."""
    p = Path(value)
    return str(p if p.is_absolute() else (BACKEND_DIR / p).resolve())


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "mysql+pymysql://root:password@localhost:3306/calorai")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-only-secret-please-change-in-dotenv-file")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "")
    MODEL_PATH: str = _path(os.getenv("MODEL_PATH", "../ml/models/food_model.keras"))
    LABELS_PATH: str = _path(os.getenv("LABELS_PATH", "../ml/models/labels.txt"))
    MAX_UPLOAD_MB: int = 10
    SEED_FILE: str = str(BACKEND_DIR / "seed" / "foods.csv")


settings = Settings()
