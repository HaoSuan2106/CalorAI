import os
import tempfile

import pytest

# Tests use a throwaway SQLite database, so MySQL is not needed to run them.
_db_file = os.path.join(tempfile.mkdtemp(), "calorai_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
os.environ["MODEL_PATH"] = os.path.join(tempfile.gettempdir(), "no_model_here.keras")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


_counter = {"n": 0}


@pytest.fixture
def auth(client):
    """Registers a fresh user and returns its Authorization headers."""
    _counter["n"] += 1
    email = f"user{_counter['n']}@test.com"
    r = client.post("/auth/register", json={
        "full_name": "Tan Wei Ming", "email": email, "password": "secret123",
        "age": 22, "gender": "male", "height_cm": 172, "weight_kg": 68,
        "activity_level": "moderate", "health_goal": "maintenance",
    })
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", json={"email": email, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def food_id(client, auth, name: str) -> int:
    foods = client.get("/foods", params={"q": name}, headers=auth).json()
    return next(f["food_id"] for f in foods if f["food_name"] == name)
