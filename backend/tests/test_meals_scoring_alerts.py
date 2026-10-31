"""Test cases for Dietary Profile, Meal Logging, Meal Scoring, Notification and Dashboard modules."""
from datetime import date, datetime, timedelta

from conftest import food_id


def set_profile(client, auth, **kw):
    body = {"religious_restriction": None, "diet_preference": "none", "allergies": [],
            "medical_conditions": [], **kw}
    r = client.put("/dietary-profile", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def log(client, auth, name, grams, category="lunch", **kw):
    r = client.post("/meals", json={"meal_category": category, "source_type": "manual",
                                    "items": [{"food_id": food_id(client, auth, name),
                                               "portion_size_g": grams}], **kw}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


# ---- Dietary restriction profile ----
def test_dietary_profile_crud(client, auth):
    p = set_profile(client, auth, religious_restriction="halal", diet_preference="vegetarian",
                    allergies=["Peanuts", "Shellfish", "peanuts"], medical_conditions=["Diabetes"])
    assert p["allergies"] == ["Peanuts", "Shellfish"]  # duplicates removed
    p = set_profile(client, auth, allergies=["Dairy"])
    assert p["allergies"] == ["Dairy"] and p["religious_restriction"] is None
    r = client.put("/dietary-profile", json={"diet_preference": "carnivore"}, headers=auth)
    assert r.status_code == 422


def test_food_list_flags_conflicts(client, auth):
    set_profile(client, auth, allergies=["Peanuts"], religious_restriction="halal")
    foods = {f["food_name"]: f for f in client.get("/foods", headers=auth).json()}
    assert len(foods) >= 80
    assert any(c["kind"] == "allergy" for c in foods["Nasi Lemak"]["conflicts"])
    assert any(c["kind"] == "religious" for c in foods["Bak Kut Teh"]["conflicts"])
    assert foods["White Rice"]["conflicts"] == []


# ---- Meal logging ----
def test_save_meal_portion_adjusts_nutrition(client, auth):
    meal = log(client, auth, "White Rice", 200)
    assert meal["total_calories"] == 260.0  # 130 kcal/100 g x 2
    assert meal["items"][0]["portion_size_g"] == 200
    assert meal["score"] is not None


def test_manual_override_values_are_kept(client, auth):
    fid = food_id(client, auth, "Chicken Satay")
    r = client.post("/meals", json={
        "meal_category": "dinner", "source_type": "photo",
        "items": [{"food_id": fid, "portion_size_g": 250,
                   "override": {"calories": 480, "protein": 38, "carbs": 24, "fat": 28,
                                "sugar": 5, "sodium": 600}}]}, headers=auth)
    assert r.status_code == 201
    assert r.json()["total_calories"] == 480


def test_meal_history_filter_and_delete(client, auth):
    yesterday = (datetime.now() - timedelta(days=1)).replace(hour=8, minute=0, microsecond=0)
    log(client, auth, "Oatmeal", 250, "breakfast", meal_datetime=yesterday.isoformat())
    m = log(client, auth, "Apple", 150, "snack")
    hist = client.get("/meals", params={"category": "snack"}, headers=auth).json()
    assert [x["meal_category"] for x in hist] == ["snack"]
    d = yesterday.date().isoformat()
    hist = client.get("/meals", params={"start": d, "end": d}, headers=auth).json()
    assert len(hist) == 1 and hist[0]["meal_category"] == "breakfast"
    assert client.delete(f"/meals/{m['meal_id']}", headers=auth).status_code == 204
    assert client.get(f"/meals/{m['meal_id']}", headers=auth).status_code == 404


def test_cannot_access_other_users_meal(client, auth):
    m = log(client, auth, "Apple", 100, "snack")
    other = client.post("/auth/register", json={
        "full_name": "Other User", "email": "other@test.com", "password": "secret123",
        "age": 30, "gender": "female", "height_cm": 160, "weight_kg": 55})
    assert other.status_code == 201
    tok = client.post("/auth/login", json={"email": "other@test.com",
                                           "password": "secret123"}).json()["access_token"]
    r = client.get(f"/meals/{m['meal_id']}", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 404


def test_update_meal_rescores(client, auth):
    m = log(client, auth, "White Rice", 100)
    fid = food_id(client, auth, "Grilled Chicken Breast")
    r = client.put(f"/meals/{m['meal_id']}", json={
        "meal_category": "lunch", "source_type": "manual",
        "items": [{"food_id": fid, "portion_size_g": 200}]}, headers=auth)
    assert r.status_code == 200
    assert r.json()["total_protein"] == 62.0


def test_scanned_label_product_flow(client, auth):
    """Label scan confirm: create the product from per-serving values, then log it."""
    set_profile(client, auth, allergies=["Dairy"])
    r = client.post("/foods", json={
        "food_name": "Choco Wafer Bar", "serving_size_g": 30, "calories": 140, "carbs": 18,
        "protein": 2, "fat": 6.6, "sugar": 6, "sodium": 120, "fibre": 1,
        "ingredients_text": "Wheat flour, sugar, palm oil, milk powder, soy lecithin"}, headers=auth)
    assert r.status_code == 201, r.text
    food = r.json()
    assert round(food["calories_per_100g"], 1) == 466.7        # 140 kcal per 30 g
    assert {"gluten", "dairy", "soy"} <= set(food["allergen_tags"].split(","))
    assert any(c["kind"] == "allergy" for c in food["conflicts"])
    meal = client.post("/meals", json={"meal_category": "snack", "source_type": "label_scan",
                                       "items": [{"food_id": food["food_id"], "portion_size_g": 60}]},
                       headers=auth).json()
    assert meal["total_calories"] == 280.0                       # two servings
    assert any(a["notification_type"] == "allergy_alert" for a in meal["alerts"])


def test_create_food_rejects_impossible_values(client, auth):
    r = client.post("/foods", json={"food_name": "Typo", "serving_size_g": 5, "calories": 300},
                    headers=auth)
    assert r.status_code == 422


# ---- Meal scoring ----
def test_healthy_meal_scores_high(client, auth):
    set_profile(client, auth)
    r = client.post("/meals", json={"meal_category": "lunch", "source_type": "manual", "items": [
        {"food_id": food_id(client, auth, "Grilled Chicken Breast"), "portion_size_g": 150},
        {"food_id": food_id(client, auth, "Brown Rice"), "portion_size_g": 200},
        {"food_id": food_id(client, auth, "Stir-fried Vegetables"), "portion_size_g": 200},
    ]}, headers=auth)
    score = r.json()["score"]
    assert score["overall_score"] >= 80, score
    assert score["grade"] == "A"
    assert score["alternatives"] == []


def test_unhealthy_meal_flags_risks_and_alternatives(client, auth):
    set_profile(client, auth)
    meal = log(client, auth, "Donuts", 300, "snack")
    score = meal["score"]
    types = {r["risk_type"] for r in score["risks"]}
    assert {"excess_calories", "excess_sugar"} <= types
    assert score["overall_score"] < 50
    assert score["factors"] and score["summary"]
    assert len(score["alternatives"]) >= 1


def test_allergy_conflict_caps_score_and_alerts(client, auth):
    set_profile(client, auth, allergies=["Peanuts"])
    meal = log(client, auth, "Nasi Lemak", 350, "breakfast")
    assert meal["score"]["overall_score"] <= 30
    assert any(r["risk_type"] == "allergy_conflict" and r["severity"] == "high"
               for r in meal["score"]["risks"])
    assert any(a["notification_type"] == "allergy_alert" for a in meal["alerts"])
    # alternatives never include foods that conflict with the profile
    for alt in meal["score"]["alternatives"]:
        f = client.get(f"/foods/{alt['food_id']}", headers=auth).json()["food"]
        assert f["conflicts"] == []


def test_religious_alert(client, auth):
    set_profile(client, auth, religious_restriction="halal")
    meal = log(client, auth, "Beer", 330, "dinner")
    assert any(a["notification_type"] == "religious_alert" for a in meal["alerts"])


def test_excess_nutrition_alert_once_per_day(client, auth):
    set_profile(client, auth)
    first = log(client, auth, "Chocolate Cake", 300, "snack")   # ~108 g sugar
    assert any(a["notification_type"] == "excess_nutrition_alert" and "sugar" in a["message"]
               for a in first["alerts"])
    second = log(client, auth, "Ice Cream", 200, "snack")
    assert not any("sugar" in a["message"] for a in second["alerts"])


def test_hypertension_uses_lower_sodium_limit(client, auth):
    set_profile(client, auth, medical_conditions=["Hypertension"])
    me = client.get("/users/me", headers=auth).json()
    assert me["targets"]["sodium_limit"] == 1500


# ---- Notifications ----
def test_notifications_read(client, auth):
    set_profile(client, auth, allergies=["Peanuts"])
    log(client, auth, "Chicken Satay", 150, "dinner")
    notes = client.get("/notifications", headers=auth).json()
    assert notes and not notes[0]["is_read"]
    nid = notes[0]["notification_id"]
    assert client.post(f"/notifications/{nid}/read", headers=auth).json()["is_read"]
    client.post("/notifications/read-all", headers=auth)
    assert client.get("/notifications/unread-count", headers=auth).json()["unread"] == 0


# ---- Dashboard ----
def test_dashboard_today_and_reports(client, auth):
    set_profile(client, auth)
    log(client, auth, "White Rice", 100, "lunch")
    log(client, auth, "Apple", 100, "snack")
    d = client.get("/dashboard/today", headers=auth).json()
    assert d["summary"]["calories"] == 182.0
    assert d["summary"]["meals_logged"] == 2
    assert d["remaining_calories"] == round(d["summary"]["calorie_goal"] - 182)
    assert len(d["week"]) == 7 and d["week"][-1]["date"] == date.today().isoformat()

    p = client.get("/dashboard/progress", params={"period": "month"}, headers=auth).json()
    assert len(p["days"]) == 30 and p["stats"]["days_logged"] == 1

    rep = client.get("/dashboard/weekly-report", headers=auth).json()
    assert len(rep["calorie_trend"]) == 7
    assert round(sum(v["percent"] for v in rep["macro_distribution"].values())) == 100
