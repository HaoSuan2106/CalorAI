"""Test cases for the User Management module (FR 1.3.1)."""
from app.models import User
from app.services.nutrition_goals import calorie_goal, daily_targets

VALID = {"full_name": "Aisyah Rahman", "email": "aisyah@test.com", "password": "abc12345",
         "age": 21, "gender": "female", "height_cm": 158, "weight_kg": 52}


def test_register_success(client):
    r = client.post("/auth/register", json=VALID)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "aisyah@test.com"
    assert "password_hash" not in body
    assert body["targets"]["calories"] > 1200


def test_register_duplicate_email_rejected(client):
    client.post("/auth/register", json={**VALID, "email": "dup@test.com"})
    r = client.post("/auth/register", json={**VALID, "email": "DUP@test.com"})
    assert r.status_code == 409


def test_register_validation(client):
    assert client.post("/auth/register", json={**VALID, "email": "not-an-email"}).status_code == 422
    assert client.post("/auth/register", json={**VALID, "email": "a1@test.com",
                                               "password": "short"}).status_code == 422
    assert client.post("/auth/register", json={**VALID, "email": "a2@test.com",
                                               "password": "lettersonly"}).status_code == 422
    assert client.post("/auth/register", json={**VALID, "email": "a3@test.com",
                                               "age": 5}).status_code == 422
    missing = {k: v for k, v in VALID.items() if k != "weight_kg"}
    assert client.post("/auth/register", json={**missing, "email": "a4@test.com"}).status_code == 422


def test_login_wrong_password(client):
    client.post("/auth/register", json={**VALID, "email": "login@test.com"})
    r = client.post("/auth/login", json={"email": "login@test.com", "password": "wrongpass1"})
    assert r.status_code == 401
    r = client.post("/auth/login", json={"email": "nobody@test.com", "password": "abc12345"})
    assert r.status_code == 401


def test_protected_endpoint_requires_token(client):
    assert client.get("/users/me").status_code == 401
    assert client.get("/users/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_update_profile(client, auth):
    r = client.put("/users/me", json={"weight_kg": 75, "activity_level": "active",
                                      "health_goal": "weight_loss"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["weight_kg"] == 75
    assert r.json()["health_goal"] == "weight_loss"
    assert client.put("/users/me", json={"height_cm": 20}, headers=auth).status_code == 422


def test_calorie_goal_formula():
    u = User(age=25, gender="male", height_cm=175, weight_kg=70,
             activity_level="moderate", health_goal="maintenance")
    # Mifflin-St Jeor: 10*70 + 6.25*175 - 5*25 + 5 = 1673.75; x1.55 = 2594
    assert calorie_goal(u) == 2594
    u.health_goal = "weight_loss"
    assert calorie_goal(u) == 2094
    t = daily_targets(u)
    assert t["sodium_limit"] == 2000


def test_delete_account(client):
    client.post("/auth/register", json={**VALID, "email": "bye@test.com"})
    tok = client.post("/auth/login", json={"email": "bye@test.com",
                                           "password": "abc12345"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.delete("/users/me", headers=h).status_code == 204
    assert client.get("/users/me", headers=h).status_code == 401
