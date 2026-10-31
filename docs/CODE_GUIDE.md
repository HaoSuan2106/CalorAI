# CalorAI — Technology, Structure & Code Guide

This guide explains **what technology CalorAI uses and why**, **how the project is organised**, **how the code works**, and **how to change or extend it**. Read [README.md](../README.md) first if you only want to install and run the app.

**Contents**

1. [Big picture: how the pieces fit together](#1-big-picture)
2. [Technology stack](#2-technology-stack)
3. [File structure (every file explained)](#3-file-structure)
4. [Backend code walkthrough](#4-backend-code-walkthrough)
5. [API reference](#5-api-reference)
6. [Database design in code](#6-database-design-in-code)
7. [Machine-learning pipeline](#7-machine-learning-pipeline)
8. [Mobile app code walkthrough](#8-mobile-app-code-walkthrough)
9. [End-to-end traces (follow one action through the code)](#9-end-to-end-traces)
10. [Testing](#10-testing)
11. [How to modify and extend](#11-how-to-modify-and-extend)
12. [Mapping to the report (Chapters 1 & 4)](#12-mapping-to-the-report)

---

## 1. Big picture

CalorAI is a **client–server** system built from three parts:

```
┌──────────────────────────┐     HTTP + JSON      ┌─────────────────────────────────────────┐
│  Flutter mobile app       │  (JWT in header)     │  FastAPI backend (Python)                │
│  mobile/lib/              │ ───────────────────▶ │  backend/app/                            │
│                           │                      │                                          │
│  Screens (UI)             │                      │  routers/   ← "controllers" (endpoints)  │
│  AppState (state)         │ ◀─────────────────── │  services/  ← business logic, AI, OCR    │
│  ApiClient (HTTP)         │     JSON responses   │  models.py  ← database tables (ORM)      │
│  OfflineStore (cache)     │                      │                                          │
│  ReminderService (notifs) │                      │      │ SQLAlchemy         │ loads         │
└──────────────────────────┘                      │      ▼                     ▼               │
                                                   │  ┌────────┐   ┌──────────────┐ ┌────────┐│
                                                   │  │ MySQL 8 │   │ TensorFlow   │ │Tesseract││
                                                   │  │ calorai │   │ food_model   │ │  OCR    ││
                                                   │  └────────┘   └──────────────┘ └────────┘│
                                                   └─────────────────────────────────────────┘
                                                                          ▲
                                                   ┌──────────────────────┴───────────┐
                                                   │ ml/ (offline, run once)           │
                                                   │ trains food_model.keras + labels  │
                                                   └──────────────────────────────────┘
```

**Why the AI runs on the server rather than the phone:**
- The sequence diagrams (Figures 4.12–4.14) show the controller calling the AI model and the OCR engine, so the design already puts them on the server.
- Tesseract and full TensorFlow are much easier to run in Python than inside Flutter.
- The phone stays light (NFR: 500 MB storage, 4 GB RAM), and you can retrain the model without reinstalling the app.
- Training still exports a `.tflite` file, so on-device inference is possible as future work.

**Why there is a backend at all**: Flutter shouldn't talk to MySQL directly. That would put database passwords inside the app, and anyone could extract them. The backend is the only thing that can access the database. It checks who the user is on every request.

---

## 2. Technology stack

### 2.1 Mobile app (`mobile/`)

| Technology | Version | What it is | Where / why it's used |
|---|---|---|---|
| **Flutter** | 3.44.8 | Google's cross-platform UI toolkit | The whole mobile app (specified in Table 1.1) |
| **Dart** | 3.12 | Flutter's programming language | All code in `mobile/lib/` |
| **Material 3** | (built-in) | Google's design system | Buttons, chips, navigation bar, dialogs |
| `provider` | 6.1 | Simple state management | `AppState` is shared with every screen through `ChangeNotifierProvider` |
| `http` | 1.6 | HTTP client | `ApiClient`, for all calls to the backend, including image uploads (multipart) |
| `shared_preferences` | 2.5 | Small key-value storage on the phone | Login token, cached user, server URL, offline food cache, queued meals, reminder times |
| `image_picker` | 1.2 | Opens the camera or gallery | Food photos and nutrition labels |
| `fl_chart` | 1.2 | Charts | 7-day trend line, calorie bar charts, macro donut |
| `intl` | 0.20 | Date and number formatting | "Mon, 29 Sep", "1,240" |
| `flutter_local_notifications` | 22.3 | Phone notifications | Scheduled meal reminders and instant allergy/excess alerts |
| `timezone` | 0.11 | Time-zone-aware dates | Needed to schedule reminders daily at a local time |
| **Gradle / Android SDK** | Gradle 9.1, AGP 8+ | Android build system | Builds the APK; configured in `android/app/build.gradle.kts` |

### 2.2 Backend (`backend/`)

| Technology | What it is | Where / why it's used |
|---|---|---|
| **Python 3.11** | Language | Whole backend. Python has the best AI/OCR libraries. |
| **FastAPI** | Modern web framework | Defines the REST endpoints (`routers/`). It validates requests automatically and generates documentation at `/docs`. |
| **Uvicorn** | ASGI web server | Runs the FastAPI app (`python -m uvicorn app.main:app`) |
| **Pydantic v2** | Data validation | `schemas.py`. This is the system's Validation Service: rejects bad emails, out-of-range height, short passwords, and so on. |
| **SQLAlchemy 2.0** | ORM (Object–Relational Mapper) | `models.py`. Python classes represent MySQL tables, so we write `db.add(user)` instead of SQL strings. It also prevents SQL injection. |
| **MySQL 8** | Relational database | Stores all 11 entities (Table 1.1) |
| **PyMySQL** + `cryptography` | MySQL driver | Lets SQLAlchemy talk to MySQL 8. `cryptography` is needed for MySQL 8's default password authentication. |
| **bcrypt** | Password hashing | `security.py`. Passwords are stored only as salted hashes (data dictionary: `password_hash`). |
| **PyJWT** | JSON Web Tokens | `security.py`. After login the app receives a signed token and sends it with every request. |
| **python-dotenv** | Loads `.env` files | `config.py`. Keeps the database password and secrets out of the code. |
| **python-multipart** | Parses file uploads | Needed by FastAPI for image uploads |
| **OpenCV** (`opencv-python-headless`) | Image processing | OCR preprocessing: grayscale, resize, deskew, denoise, contrast (CLAHE), thresholding |
| **Pillow** | Image loading | Opens uploaded photos and fixes phone rotation (EXIF) |
| **NumPy** | Arrays/maths | Image arrays, model input and output |
| **pytesseract** + **Tesseract 5** | OCR engine (from Google) | Reads text from nutrition labels (Table 1.1) |
| **TensorFlow / Keras** | Deep-learning framework | Loads and runs the trained food classifier (Table 1.1) |
| **pytest** + **httpx** | Testing | 31 automated tests in `backend/tests/` |

### 2.3 Machine learning (`ml/`)

| Technology | Use |
|---|---|
| **TensorFlow / Keras** | Building and training the model |
| **MobileNetV2** (default) | A lightweight CNN pretrained on ImageNet, chosen because the literature review (Aktı et al., 2022) found it balances accuracy and memory |
| **EfficientNetV2-B0** (option) | A slightly heavier, often more accurate alternative |
| **Transfer learning** | Reuses ImageNet features and only trains the last layers, so a few hundred images per food are enough |
| **scikit-learn** | Classification report and confusion matrix for the evaluation |
| **matplotlib** | Training-curve graph |
| **TFLite converter** | Exports a phone-sized model (`food_model.tflite`) |

---

## 3. File structure

```
FYP/
├── README.md                     Setup and run instructions
├── .gitignore                    Files Git should not track (.env, build output, datasets)
├── docs/
│   └── CODE_GUIDE.md             This document
│
├── backend/                      ───────────── PYTHON SERVER ─────────────
│   ├── requirements.txt          Python packages for the server and tests
│   ├── requirements-ai.txt       TensorFlow (separate because it's large)
│   ├── .env.example              Template for .env (DB password, secrets, paths)
│   ├── schema.sql                MySQL CREATE TABLE script (generated from models.py)
│   ├── seed/
│   │   └── foods.csv             84 reference foods: nutrition per 100 g + ingredient tags
│   ├── app/
│   │   ├── main.py               Creates the FastAPI app, registers routers, startup tasks
│   │   ├── config.py             Reads settings from .env
│   │   ├── database.py           DB connection, session factory, auto-create database/tables
│   │   ├── models.py             11 ORM classes = 11 tables (data dictionary)
│   │   ├── schemas.py            Request/response shapes + validation rules
│   │   ├── security.py           Password hashing, JWT creation, "who is the current user?"
│   │   ├── serializers.py        Converts DB objects into API response objects
│   │   ├── seed.py               Loads foods.csv into the food_item table on first start
│   │   ├── routers/              ── Controllers: one file per module, map URLs → functions
│   │   │   ├── auth.py           POST /auth/register, /auth/login
│   │   │   ├── users.py          GET/PUT/DELETE /users/me
│   │   │   ├── dietary.py        GET/PUT /dietary-profile
│   │   │   ├── foods.py          GET/POST /foods (food database, custom/scanned products)
│   │   │   ├── meals.py          CRUD /meals (save triggers scoring + alerts)
│   │   │   ├── recognition.py    POST /recognition/predict (food photo → AI)
│   │   │   ├── label_scan.py     POST /label-scan (label photo → OCR)
│   │   │   ├── notifications.py  GET /notifications, mark read
│   │   │   └── dashboard.py      GET /dashboard/today, /progress, /weekly-report
│   │   └── services/             ── Business logic (class diagram service classes)
│   │       ├── nutrition_goals.py           Calorie goal + nutrient limits
│   │       ├── dietary_profile_service.py   Ingredient tagging + conflict detection
│   │       ├── meal_logging_service.py      Save/update/delete meal pipeline
│   │       ├── meal_scoring_engine.py       MealScoringEngine
│   │       ├── notification_service.py      NotificationService
│   │       ├── dashboard_service.py         DashboardService
│   │       ├── food_recognition_service.py  FoodRecognitionService (TensorFlow)
│   │       └── nutrition_label_scanner.py   NutritionLabelScanner (OpenCV + Tesseract)
│   └── tests/
│       ├── conftest.py                    Test setup (temporary SQLite DB, helper fixtures)
│       ├── test_user_management.py        Registration, login, profile, goals
│       ├── test_meals_scoring_alerts.py   Profile, meals, scoring, alerts, dashboard
│       └── test_ocr_parser.py             Label text parsing, ingredient tagging, preprocessing
│
├── ml/                           ───────────── MODEL TRAINING ─────────────
│   ├── requirements.txt          TensorFlow, scikit-learn, matplotlib
│   ├── prepare_dataset.py        Builds dataset/train|val|test/<class>/ folders
│   ├── train_food_model.py       Trains, evaluates and exports the model
│   ├── dataset/                  (created by prepare_dataset.py)
│   └── models/                   (created by training) food_model.keras, labels.txt, evaluation.txt
│
└── mobile/                       ───────────── FLUTTER APP ─────────────
    ├── pubspec.yaml              App name, version, package dependencies
    ├── analysis_options.yaml     Lint rules
    ├── android/                  Android project (generated by Flutter, then edited):
    │   └── app/
    │       ├── build.gradle.kts           minSdk 29 (Android 10), desugaring for notifications
    │       └── src/main/AndroidManifest.xml  Permissions, notification receivers, http allowed
    ├── test/widget_test.dart     Unit tests for portion/nutrition logic
    └── lib/                      ── All Dart code
        ├── main.dart             Entry point; picks Login or Home screen
        ├── theme.dart            Colours, input/button styles
        ├── models.dart           Dart classes for API data (User, Meal, FoodItem…)
        ├── api/api_client.dart   HTTP wrapper, error handling, uploads
        ├── state/app_state.dart  Central app state + all actions (login, saveMeal, sync…)
        ├── services/
        │   ├── offline_store.dart     Food cache + offline meal queue
        │   └── reminder_service.dart  Local notifications (reminders + alerts)
        ├── widgets/
        │   ├── common.dart            Reusable UI: AppCard, Ring, MacroPill, ScoreBadge, banners
        │   └── meal_draft_editor.dart MealDraft model + portion/nutrition editor widget
        └── screens/              ── One file per screen
            ├── login_screen.dart           Figure 4.17
            ├── register_screen.dart        Figure 4.18 (+ step 2: body details)
            ├── server_settings.dart        Dialog to set backend URL
            ├── privacy_screen.dart         Terms & privacy policy (NFR security)
            ├── home_shell.dart             Bottom navigation (Home/History/+/Alerts/Profile)
            ├── dashboard_screen.dart       Figure 4.19
            ├── log_meal_sheet.dart         "Log Meal" bottom sheet (Figure 4.20 left)
            ├── food_recognition_screen.dart Figure 4.20 right
            ├── label_scan_screen.dart      Figure 4.21 (also "Add Custom Food")
            ├── manual_entry_screen.dart    Searchable food list
            ├── meal_editor_screen.dart     Confirm portion/category; edit meal
            ├── meal_detail_screen.dart     Meal score, risks, feedback, alternatives
            ├── history_screen.dart         Meal history by date + category
            ├── notifications_screen.dart   Figure 4.24
            ├── dietary_profile_screen.dart Figure 4.23
            ├── profile_screen.dart         Profile hub
            ├── edit_profile_screen.dart    Height, weight, activity, goal
            ├── reminder_settings_screen.dart Meal reminder times
            ├── progress_screen.dart        Daily / weekly / monthly analytics
            └── weekly_report_screen.dart   Figure 4.25
```

---

## 4. Backend code walkthrough

### 4.1 The layers

The backend follows a **layered architecture**. Each layer only talks to the one below it:

```
HTTP request
   │
   ▼
routers/*.py        "Controller" — reads the request, checks login, calls a service, returns JSON
   │
   ▼
schemas.py          Validates incoming JSON (Pydantic). Invalid → automatic 422 error
   │
   ▼
services/*.py       Business rules: scoring, conflicts, OCR, AI, notifications
   │
   ▼
models.py           ORM classes ↔ MySQL tables (SQLAlchemy)
   │
   ▼
MySQL
```

`serializers.py` sits beside the routers. It converts ORM objects, such as a `Meal` with its score, into response objects.

### 4.2 Startup — [main.py](../backend/app/main.py)

When you run `uvicorn app.main:app`:
1. `app = FastAPI(...)` creates the application.
2. `CORSMiddleware` allows requests from any origin, which is convenient during development.
3. Each router (`auth`, `users`, `meals`, …) is registered with `app.include_router`.
4. The `lifespan` function runs **once at startup**:
   - `init_db()` ([database.py:50](../backend/app/database.py)) creates the `calorai` MySQL database if it's missing (`_ensure_mysql_database`), then all tables (`Base.metadata.create_all`), then seeds the foods (`seed_food_items`).
   - `FoodRecognitionService.warm_up_in_background()` loads the TensorFlow model in a background thread. Loading takes a few seconds, and doing it at startup means the first photo meets the "result within 5 s" requirement.
5. `GET /` (the `health` function) reports whether the model and Tesseract are available.

### 4.3 Configuration — [config.py](../backend/app/config.py)

`load_dotenv` reads `backend/.env` into environment variables, and the `Settings` class exposes them with defaults:
`DATABASE_URL`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `TESSERACT_CMD`, `MODEL_PATH`, `LABELS_PATH`.
Relative paths like `../ml/models/food_model.keras` are resolved from the `backend/` folder by `_path()`.

### 4.4 Database connection — [database.py](../backend/app/database.py)

- `engine = create_engine(DATABASE_URL, pool_pre_ping=True)` is a pool of DB connections. `pool_pre_ping` reconnects automatically if MySQL dropped an idle connection, which supports the reliability NFR.
- `SessionLocal` is a factory for **sessions**. A session is a unit of work: you add or change objects, then `commit()`.
- `get_db()` is a **FastAPI dependency**. Any endpoint with `db: Session = Depends(get_db)` gets a fresh session that is closed automatically afterwards.
- For SQLite (used only by the tests) it switches on foreign keys, which SQLite leaves off by default.

### 4.5 Models — [models.py](../backend/app/models.py)

Each class is one table from the data dictionary. Example:

```python
class Meal(Base):
    __tablename__ = "meal"
    meal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.user_id", ondelete="CASCADE"))
    meal_category: Mapped[str] = mapped_column(String(20))
    ...
    items: Mapped[list["MealItem"]] = relationship(back_populates="meal", cascade="all, delete-orphan")
```

Key ideas:
- `Dec(6, 2)` = `DECIMAL(6,2)`, exactly as in the data dictionary. `asdecimal=False` makes Python receive normal floats.
- `relationship(...)` lets you navigate objects: `meal.items`, `meal.score.risks`, `user.profile.allergies`.
- `cascade="all, delete-orphan"` + `ondelete="CASCADE"`: deleting a user deletes their meals, profile and notifications. This is how account deletion (`DELETE /users/me`) works.
- `Meal.calculate_total_nutrition()` sums the items into `total_*`, matching the class-diagram method `calculateTotalNutrition()`.
- `FoodItem.tags` turns the comma-separated `allergen_tags` string into a Python set.
- `DailySummary` has `UniqueConstraint(user_id, summary_date)`, so there is one row per user per day.

### 4.6 Validation — [schemas.py](../backend/app/schemas.py)

Pydantic classes describe what JSON is allowed. FastAPI rejects anything else with **HTTP 422** before your code runs. Examples:
- `RegisterRequest`: `email: EmailStr` (real email format), `password` of 8–128 characters that must contain letters **and** digits (`_password` validator), `age` 13–120, `height_cm` 80–250, `weight_kg` 25–300, `gender` ∈ {male, female, other}.
- `MealCreate`: `meal_category` ∈ {breakfast, lunch, dinner, snack}, `source_type` ∈ {photo, label_scan, manual}, 1–20 items.
- `MealItemIn.override`: optional manually edited nutrition values (from "Edit Details Manually").
- `FoodCreate`: values **per serving** + `serving_size_g`; converted to per-100 g when saved.

### 4.7 Security — [security.py](../backend/app/security.py)

- **Registration**: `hash_password()` → `bcrypt.hashpw(password, gensalt())`. Each password gets a random salt, so equal passwords produce different hashes.
- **Login**: `verify_password()` → `bcrypt.checkpw`. On success `create_access_token(user_id)` builds a **JWT**: `{"sub": user_id, "exp": now+7 days}`, signed with `JWT_SECRET` (HS256).
- **Every protected endpoint** has `user: User = Depends(get_current_user)`. That function:
  1. reads the `Authorization: Bearer <token>` header
  2. verifies the signature and expiry with `jwt.decode`
  3. loads the `User` from the database
  4. returns **401** if any step fails
- **Data isolation**: every query filters by `user.user_id`, and `_own_meal()` in [meals.py](../backend/app/routers/meals.py) returns 404 when the meal belongs to someone else. A test checks this (`test_cannot_access_other_users_meal`).

### 4.8 Nutrition goals — [nutrition_goals.py](../backend/app/services/nutrition_goals.py)

```
BMR (Mifflin-St Jeor) = 10·weight + 6.25·height − 5·age + (5 male | −161 female | −78 other)
TDEE = BMR × activity factor   (sedentary 1.2, light 1.375, moderate 1.55, active 1.725, very active 1.9)
Calorie goal = TDEE − 500 (weight loss) | +0 (maintenance) | +300 (muscle gain), never below 1200/1500
```

`daily_targets(user)` then derives the following (WHO-based):

| Target | Normal | Adjusted when |
|---|---|---|
| Carbs | 50% of kcal ÷ 4 | 45% with **diabetes** |
| Protein | 20% of kcal ÷ 4, at least 0.8 g/kg | at least 1.6 g/kg for **muscle gain** |
| Fat | 30% of kcal ÷ 9 | — |
| Sugar limit | 10% of kcal ÷ 4 | 5% with **diabetes** |
| Sodium limit | 2000 mg | 1500 mg with **hypertension** |
| Fat limit | 35% of kcal ÷ 9 | — |
| Fibre | 25 g | — |

This is how "medical conditions" (FR 1.3.2.4) change the warnings.

### 4.9 Dietary conflicts — [dietary_profile_service.py](../backend/app/services/dietary_profile_service.py)

**Tags.** Every food carries **ingredient tags** such as `peanuts`, `dairy`, `gluten`, `pork`, `alcohol` or `chicken`.
- `TAG_KEYWORDS` maps each tag to English and Malay keywords. For example, `shellfish` ← shrimp, prawn, *udang*, *belacan*; `pork` ← lard, bacon, *babi*.
- `tags_in_text(text)` finds tags in any text (a food name or an ingredient list) using whole-word regex. "eggplant" does **not** match "egg".
- `_FALSE_FRIENDS` removes phrases that look like an allergen but aren't. "coconut milk" / *santan* is not dairy, and "peanut butter" is not dairy (it still counts as peanuts).

**Conflicts.** `check_conflicts(tags, text, profile)` compares the tags with the user's profile:
- **Allergies**: `allergy_to_tag("Prawns")` → `shellfish`. A custom allergy that isn't a known tag (e.g. "Nightshades") is matched against the text directly.
- **Religious** (`RELIGIOUS_RULES`):
  - Halal → pork and alcohol (high severity), gelatin (medium)
  - Kosher → pork and shellfish
  - No beef → beef
- **Diet** (`DIET_RULES`):
  - Vegetarian → any meat or fish
  - Vegan → the vegetarian list plus dairy, egg and honey
  - Paleo → gluten, dairy, soy and peanuts
  - Keto is handled by carbohydrate amount in the scoring engine.

The result is a list of `ConflictResult(kind, tag, severity, message)`. It is used in four places:
1. the food list (warning icon in Manual Entry)
2. recognition results (red banner before saving)
3. label scans (per-ingredient colouring)
4. meal scoring and alerts (after saving)

### 4.10 Saving a meal — [meal_logging_service.py](../backend/app/services/meal_logging_service.py)

`MealLoggingService.save_meal()` is the heart of the system. It implements the activity diagram (Figure 4.10) and sequence diagram 4.14:

```
1. _build_items(): for each item → look up FoodItem
                    nutrition = override (if user edited) OR per_100g × portion/100
2. meal.calculate_total_nutrition()
3. db.flush()                         → MySQL assigns meal_id
4. MealScoringEngine.evaluate_meal()  → MealScore + NutritionRisk rows, returns conflicts
5. DashboardService.refresh_daily_summary(date) → upsert DailySummary for that day
6. NotificationService.send_conflict_alerts()    → allergy/religious/diet alerts
7. NotificationService.send_excess_nutrition_alerts() → if today's totals exceed limits
8. db.commit()                        → everything saved together (all-or-nothing)
```

Because steps 1–7 run in **one transaction**, a failure part-way leaves no half-saved meal. This supports the "failure recovery without data corruption" NFR.

The same function also handles **updates**: it clears the old items, rebuilds them, re-scores, and refreshes the summary of both the old and new dates. `delete_meal()` unlinks notifications that point at the meal, deletes the meal (its items, score and risks cascade), then refreshes the summary.

`DEFAULT_PORTIONS` gives a sensible starting portion per category. For example, a rice dish starts at 350 g and a beverage at 250 ml.

### 4.11 Meal scoring — [meal_scoring_engine.py](../backend/app/services/meal_scoring_engine.py)

**How the score is built.** `generate_score()` starts at **100** and subtracts points. Each meal is compared with **its share of the daily targets**: breakfast 25%, lunch 35%, dinner 30%, snack 15% (`MEAL_SHARE`).

| Check | Condition | Points | Risk recorded |
|---|---|---|---|
| Calories | > 1.5× meal budget | −20 (−25 if weight-loss goal) | `excess_calories` high |
| | > 1.2× meal budget | −8 (−12 if weight-loss) | `excess_calories` medium |
| Sugar\* | > 2× meal share of limit | −20 | `excess_sugar` high |
| | > 1.2× | −10 | `excess_sugar` medium |
| Sodium | > 2× / > 1.2× | −20 / −10 | `excess_sodium` high / medium |
| Fat | > 45% / > 35% of the meal's energy | −12 / −6 | `excess_fat` |
| Carbs | keto: > 20 g; diabetes: > 1.2× target | −10 | `excess_carbs` |
| Protein\*\* | < 12% of energy (20% for muscle gain) | −8, otherwise **+3** | `insufficient_protein` |
| Fibre\*\* | < half the target | −6; at or above target **+3** | `insufficient_fibre` |
| Allergy conflict | any | −40 and **score capped at 30** | `allergy_conflict` high |
| Religious conflict | high severity / medium (gelatin) | −40 and **cap 30** / −20 | `religious_conflict` |
| Diet conflict | any | −20 | `diet_conflict` |

\* Sugar from whole fruit is ignored, because WHO "free sugars" exclude it.
\*\* Protein and fibre are only checked for main meals over 150 kcal, not drinks or snacks.

The final score is clamped to 0–100. **Grade**: A ≥ 80 (Excellent), B ≥ 65 (Good), C ≥ 50 (Fair), D < 50 (Poor).

**Explanations.** Every deduction or bonus is saved as a **factor** `{factor, impact, detail}`, which the app shows under "Why this score". This satisfies FR 1.3.6.3, "explain the factors contributing to the score".

**Feedback.** `generate_feedback()` writes a personalised summary that names the user's goal and the biggest problem.

**Healthier alternatives.** `suggest_healthy_alternatives()` (FR 1.3.6.4) works like this:
1. Take the meal's biggest-calorie item and the first nutrient risk (for example `excess_sodium` → compare `sodium_per_100g`).
2. Keep only foods that are at least **20% better** on that nutrient **and** have no conflict with the user's profile.
3. Rank same-category foods first, then by `health_index` (protein and fibre up; sugar, sodium, fat and calories down).
4. Return the top 3.

**Storage.** The result is stored as a `MealScore` row. `feedback_text` holds JSON `{grade, summary, factors, alternatives}`. One `NutritionRisk` row is stored per risk.

### 4.12 Notifications — [notification_service.py](../backend/app/services/notification_service.py)

| Method | Creates | When |
|---|---|---|
| `send_conflict_alerts` | `allergy_alert`, `religious_alert`, `diet_alert` | Right after a meal with conflicts is saved |
| `send_excess_nutrition_alerts` | `excess_nutrition_alert` | When today's total calories, sugar, sodium or fat goes over the limit. `_exists_today` prevents the same alert twice in one day. |
| `check_meal_reminders` | `meal_reminder` | When the app opens the Alerts list: if breakfast, lunch or dinner wasn't logged by 10:30 / 14:30 / 20:30 |

The phone also schedules its own reminders (see §8.6). The server-side check makes sure a reminder appears in the Alerts list even if the phone's notification was dismissed.

### 4.13 Dashboard — [dashboard_service.py](../backend/app/services/dashboard_service.py)

- `refresh_daily_summary(date)` re-adds all meals of that day into the `DailySummary` row. It runs after every save, update or delete, so the dashboard is a single quick read (NFR: dashboard within 2 s).
- `get_daily_summary(date)` returns today's totals, goal, meals logged and average score.
- `get_progress_trend(days)` returns one entry per day for 7, 30 or 90 days. Days without a summary row appear as zeros. It also returns stats: days logged, days within goal (±5%), average calories, sugar, sodium and score, and the logging streak.
- `weekly_report(end)` builds Figure 4.25: the calorie trend against the goal, the macro split (% of energy from carbs, protein and fat), risk counts by severity (a join of `nutrition_risk` → `meal_score` → `meal`), and alert counts by type.

### 4.14 Food recognition — [food_recognition_service.py](../backend/app/services/food_recognition_service.py)

Flow for `POST /recognition/predict` ([recognition.py](../backend/app/routers/recognition.py)):
1. `read_image()` rejects empty files and files over 10 MB.
2. `FoodRecognitionService.classify_food()`:
   - `load()` loads the model once and caches it in a class variable. `tensorflow` is imported **lazily**, so the server starts even if TensorFlow isn't installed.
   - `_prepare()` fixes the EXIF rotation, converts to RGB, centre-crops to a square, resizes to 224×224 and turns the image into an array of pixels (0–255). The model contains its own normalisation layer.
   - `model.predict()` gives a probability for each class; the top 3 are returned.
3. `match_food_name()` maps model labels to database foods: `"chicken_wings"` → "Chicken Wings", and `"satay"` → "Chicken Satay" (suffix match). There is also a fuzzy fallback using `difflib`.
4. The response holds each prediction plus its `FoodItem`, a default portion, nutrition for that portion, and conflicts. `low_confidence` is true when the top confidence is below 50% or the label isn't in the database, and the app then recommends manual search.
5. If the model isn't trained yet the endpoint returns **503** with instructions. The app shows that message and offers **Search manually**.

The model call runs in `run_in_threadpool` so a slow prediction doesn't block other users' requests.

### 4.15 OCR label scanning — [nutrition_label_scanner.py](../backend/app/services/nutrition_label_scanner.py)

This follows Figure 4.13 in three stages.

**Stage 1 — Preprocessing** (`preprocess_image`):
1. `_load_gray`: open the image, fix rotation, convert to grayscale, and resize so the longest side is about 1800–2400 px. Tesseract reads best when letters are about 30 px tall.
2. `_deskew`: try rotations from −10° to +10° and keep the one where the rows of text line up best (the **projection-profile** method).
3. `medianBlur` removes noise, and **CLAHE** improves contrast in shadows and glare.
4. Three variants are produced: **Otsu threshold**, **adaptive threshold** and plain **contrast**.

**Stage 2 — OCR with retry** (`scan_label`):
```
for each variant (max 3 attempts):
    text, confidence = extract_text(variant)      # pytesseract.image_to_data
    keep the best result
    stop if confidence ≥ 0.70
```
`extract_text` rebuilds the text **line by line** from Tesseract's word boxes, which keeps each nutrient on its own line. Confidence is the average word confidence.

**Stage 3 — Parsing**:

`parse_nutrition_values(text)` reads the nutrient table:
- `_clean_line` fixes typical OCR mistakes:
  - `Og` → `0g`, `l2` → `12`
  - comma decimals `60,0` → `60.0`
  - thousands `1,960` → `1960`
- For each line it finds a nutrient label in English or Malay (`NUTRIENT_LINES`), for example *Tenaga* (energy), *Lemak* (fat), *Gula* (sugar), *Natrium* (sodium). It skips look-alikes such as *saturated fat*, *added sugars* and *calories from fat*.
- It reads the numbers after the label and ignores `%` daily values. Energy prefers **kcal**; if only **kJ** is printed it divides by 4.184. Sodium in g is multiplied by 1000.
- `_column_order` detects Malaysian two-column labels ("Per 100 g | Per serving") and assigns each number to the right column. `_serving_size` finds "Serving size 30 g" or *Saiz hidangan*.
- It returns both `per_serving` and `per_100g`, plus which nutrients were `found` or `missing`.

`parse_ingredient_list(text)` reads the ingredients:
- It finds "Ingredients:" (or *Bahan-bahan*, *Ramuan*) and stops at "Contains", "Allergen", "Nutrition" or a blank line.
- It splits on commas **outside brackets**, so "emulsifier (soy lecithin)" stays one item.
- "Contains: milk, soy" statements are collected as tags.

**Response.** [label_scan.py](../backend/app/routers/label_scan.py) `categorise_ingredients()` labels each ingredient `allergy` (matches the user's allergies), `restricted` (religious/diet), `common_allergen` or `safe`. This is FR 1.3.4.3, "categorise according to allergies and non-allergies".

**Saving.** When the user confirms, the app calls `POST /foods` to create the product (the per-serving values are converted to per-100 g, and tags come from the ingredients), then `POST /meals` with `portion = serving size × servings`.

### 4.16 Seeding — [seed.py](../backend/app/seed.py) and [foods.csv](../backend/seed/foods.csv)

On first start, if `food_item` is empty, each CSV row becomes a `FoodItem`. Columns: `food_name, food_category, calories, carbs, protein, fat, sugar, sodium (mg), fibre, tags` (all per 100 g, or per 100 ml for drinks). Tags are separated by `|` in the CSV, for example `peanuts|fish|egg`.

---

## 5. API reference

All endpoints except `/`, `/auth/*` and `/dietary-profile/options` need `Authorization: Bearer <token>`. You can try them all at **http://localhost:8000/docs**.

| Method | Path | Purpose | Module |
|---|---|---|---|
| GET | `/` | Health: model loaded? Tesseract available? | — |
| POST | `/auth/register` | Create account (409 if the email already exists) | User Mgmt |
| POST | `/auth/login` | Returns `access_token` + user (401 if wrong) | User Mgmt |
| GET / PUT / DELETE | `/users/me` | View / update / delete own account | User Mgmt |
| GET | `/dietary-profile/options` | Chip options (allergens, religions, diets, conditions) | Dietary |
| GET / PUT | `/dietary-profile` | Read / replace allergies, religion, diet, conditions | Dietary |
| GET | `/foods?q=&category=` | Food list with per-user conflicts | Meal Logging |
| GET | `/foods/categories` | Distinct categories | Meal Logging |
| GET | `/foods/{id}?portion_g=` | One food + nutrition for a portion | Meal Logging |
| POST | `/foods` | Create a custom/scanned product (per-serving input) | Label Scanning |
| POST | `/meals` | Save meal → score, risks, alerts, summary (returns them) | Meal Logging + Scoring |
| GET | `/meals?start=&end=&category=` | History filtered by date range and category | Meal Logging |
| GET / PUT / DELETE | `/meals/{id}` | View / edit / delete one meal | Meal Logging |
| POST | `/recognition/predict` (multipart `image`) | Top-3 food predictions | Food Recognition |
| GET | `/recognition/status` | Model file found / loaded | Food Recognition |
| POST | `/label-scan` (multipart `image`) | OCR → nutrition, ingredients, conflicts | Label Scanning |
| GET | `/notifications` | List (also generates due meal reminders) | Notification |
| GET | `/notifications/unread-count` | Badge count | Notification |
| POST | `/notifications/{id}/read`, `/notifications/read-all` | Mark read | Notification |
| GET | `/dashboard/today` | Summary, targets, remaining kcal, today's meals, 7-day series | Dashboard |
| GET | `/dashboard/progress?period=week\|month\|quarter` | Daily series + stats | Dashboard |
| GET | `/dashboard/weekly-report?end=YYYY-MM-DD` | Figure 4.25 data | Dashboard |

Example — saving a meal:

```json
POST /meals
{
  "meal_category": "lunch",
  "source_type": "photo",
  "meal_datetime": "2026-10-16T12:30:00",
  "items": [
    { "food_id": 33, "portion_size_g": 250,
      "override": { "calories": 480, "protein": 38, "carbs": 24, "fat": 28, "sugar": 5, "sodium": 600 } }
  ]
}
```
The response is the saved meal with `items`, `score` (overall, grade, summary, factors, alternatives, risks) and `alerts` (notifications created by this save).

Error format: `{"detail": "message"}`, or for validation a list of `{loc, msg}`. The app turns both into readable messages (`ApiClient._detail`).

---

## 6. Database design in code

| Table (`models.py`) | Data dictionary | Key relationships |
|---|---|---|
| `user` | Table 4.5 | 1:1 dietary_profile, 1:* meal, notification, daily_summary |
| `dietary_profile` | 4.6 | `user_id` UNIQUE → 1:1 |
| `allergy` | 4.7 | * : 1 dietary_profile |
| `medical_condition` | 4.8 | * : 1 dietary_profile |
| `meal` | 4.9 | * : 1 user; 1:* meal_item; 1:1 meal_score |
| `meal_item` | 4.10 | * : 1 meal, * : 1 food_item |
| `food_item` | 4.11 | referenced by meal_item |
| `meal_score` | 4.12 | `meal_id` UNIQUE → 1:1; 1:* nutrition_risk |
| `nutrition_risk` | 4.13 | * : 1 meal_score |
| `notification` | 4.14 | * : 1 user; `related_meal_id` nullable (SET NULL on meal delete) |
| `daily_summary` | 4.15 | UNIQUE(user_id, summary_date) |

`meal_item` stores the computed nutrient values for its portion instead of recalculating them from `food_item` every time. This is the documented denormalisation from section 4.6 of your report: old meals stay correct even if a food's reference values are later corrected.

`backend/schema.sql` contains the equivalent `CREATE TABLE` statements. You can include them in your report, or run them in MySQL Workbench to create the schema by hand.

---

## 7. Machine-learning pipeline

### 7.1 [prepare_dataset.py](../ml/prepare_dataset.py)

```
source folders (<class>/*.jpg)  →  shuffle (seed 42)  →  take ≤ --per-class images
                                →  80% train / 10% val / 10% test
                                →  ml/dataset/{train,val,test}/<class>/00000.jpg …
```
- `--food101-db` selects the 24 Food-101 classes that already exist in `foods.csv`.
- `--classes nasi_lemak roti_canai …` adds your own folders.
- It warns about classes it can't find.

### 7.2 [train_food_model.py](../ml/train_food_model.py)

**Model structure** (`build_model`):
```
Input 224×224×3 (pixels 0–255)
 → Data augmentation (random flip, rotation ±8%, zoom 15%, contrast 15%)   ← training only
 → Rescaling to [-1, 1]                                                    ← MobileNetV2 format
 → MobileNetV2 backbone (ImageNet weights)
 → GlobalAveragePooling2D
 → Dropout 0.3
 → Dense(num_classes, softmax)
```
Augmentation makes the model robust to the different angles, lighting and plates people photograph food on. That challenge is raised in the literature review (Liu et al., 2025).

**Two-phase training:**
1. **Phase 1**: the backbone is frozen, and only the new classifier head is trained (Adam, learning rate 1e-3, up to 10 epochs).
2. **Phase 2 (fine-tuning)**: the top 40 backbone layers are unfrozen and trained with a tiny learning rate (1e-5), so the pretrained features adapt to food without being destroyed. BatchNorm layers stay frozen for stability.

**Callbacks:**
- `ModelCheckpoint` saves the best model by validation accuracy.
- `EarlyStopping` stops when validation accuracy hasn't improved for 4 epochs.
- `ReduceLROnPlateau` lowers the learning rate when progress stalls.

**Evaluation** on the unseen **test** split writes `evaluation.txt`:
- top-1 and top-3 accuracy
- "Target (≥ 0.90): MET / NOT MET"
- per-class precision, recall and F1, and a confusion matrix

Use these in Chapter 5 to evaluate NFR 1.3.5.1.

**Outputs:**
- `food_model.keras` and `labels.txt`, which the backend loads
- `training_curves.png`
- `food_model.tflite`, for optional on-device use

**If accuracy is too low:**
- add more or cleaner images per class (aim for 300 or more)
- use `--arch efficientnetv2b0`
- increase `--fine-tune-epochs`
- merge classes that look alike

---

## 8. Mobile app code walkthrough

### 8.1 Start-up — [main.dart](../mobile/lib/main.dart)

```
main()
 ├─ AppState().init()          load token/user/server URL from shared_preferences
 ├─ ReminderService.init()     set up notification plugin + time zone
 └─ runApp(ChangeNotifierProvider(AppState) → CalorAIApp)
        └─ _Root: watches AppState
             ├─ not ready yet     → spinner
             ├─ loggedIn == false → LoginScreen
             └─ loggedIn == true  → HomeShell
```
Logging in or out changes `AppState`. `_Root` rebuilds and swaps screens automatically, with no manual navigation needed.

### 8.2 State management — [app_state.dart](../mobile/lib/state/app_state.dart)

The app uses **Provider** with one `ChangeNotifier` called `AppState`.
- Screens **read** it with `context.watch<AppState>()`, which rebuilds the screen when it changes, or `context.select(...)`, which rebuilds only when one field changes.
- Screens **call actions** with `context.read<AppState>().login(...)`.

| Member | Purpose |
|---|---|
| `api` | The shared `ApiClient` (base URL + token) |
| `user`, `profile` | Logged-in user (with targets) and dietary profile |
| `unread` | Notification badge count |
| `pendingSync` | Number of meals waiting in the offline queue |
| `dataVersion` | A counter that is **incremented every time meals change**. Dashboard, History and Notifications compare it with the version they last loaded and reload when it differs. This is a simple way to keep every tab in sync. |
| `login / register / logout` | Auth. `login` saves the token to `shared_preferences`, so you stay logged in. |
| `saveMeal(payload)` | POST/PUT the meal. If the phone is **offline**, the meal is queued instead (`SaveResult.queuedOffline`). Alerts in the response are shown as phone notifications (`_pushAlerts`). |
| `syncPending()` | Uploads queued meals. It runs at login, when the app resumes, on pull-to-refresh and from "Sync now". |
| `foods()` | Downloads the food list and caches it. If offline, it returns the cache, which makes manual logging work without internet (NFR 1.3.7.1). |

If any request returns **401** (expired token), `api.onUnauthorized = logout` sends the user back to the login screen.

### 8.3 Networking — [api_client.dart](../mobile/lib/api/api_client.dart)

- `get / post / put / delete` add JSON headers and the `Bearer` token.
- `upload(path, filePath)` sends a **multipart** request with the image file (60 s timeout).
- `_send()` handles every response in one place:
  - `SocketException`, `TimeoutException` or `ClientException` → `ApiException(offline: true)`. This is how offline mode is detected.
  - A 2xx response → the decoded JSON.
  - Anything else → `ApiException(message from {"detail": ...}, status)`.
- `defaultBaseUrl = http://10.0.2.2:8000`. The Android emulator sees your PC at `10.0.2.2`. A real phone needs the PC's IP, which you set in Server settings and which is saved in `shared_preferences`.

### 8.4 Data models — [models.dart](../mobile/lib/models.dart)

These are plain Dart classes with `fromJson` constructors that mirror the API responses: `AppUser` (with `Targets`), `DietaryProfile`, `FoodItem` (with a `per100g` `Nutrition` and `conflicts`), `Meal` (with `items`, `score`, `alerts`), `MealScore` (`factors`, `alternatives`, `risks`), `AppNotification` and `DaySummary`.

`Nutrition` has helpers:
- `scaled(factor)`, for portion maths
- `[]`, to read a nutrient by key
- `set(key, value)`, used by the editable fields
- `toJson()`, which rounds to 2 decimals

### 8.5 Offline store — [offline_store.dart](../mobile/lib/services/offline_store.dart)

It stores two JSON strings in `shared_preferences`:
- `cached_foods`: the last downloaded food list
- `pending_meals`: a list of meal payloads that couldn't be uploaded

Each payload already contains `meal_datetime`, so a meal synced later still has its real time.

### 8.6 Phone notifications — [reminder_service.dart](../mobile/lib/services/reminder_service.dart)

- `init()` loads time-zone data (Asia/Kuala_Lumpur when the phone is UTC+8) and initialises the plugin.
- `schedule(prefs)`:
  1. cancels the old reminders (ids 1–3)
  2. asks for notification permission (Android 13+)
  3. schedules breakfast, lunch and dinner with `zonedSchedule(..., matchDateTimeComponents: DateTimeComponents.time)`, which means "repeat daily at this time"
  4. uses `inexactAllowWhileIdle`, which needs no special exact-alarm permission and saves battery
- `showAlert(title, body)` shows an immediate high-priority notification. It is used for allergy, religious and excess-nutrition alerts after a save.
- Reminder times and on/off are stored in `shared_preferences` and edited in `ReminderSettingsScreen`.

The Android side needs the receivers and permissions in [AndroidManifest.xml](../mobile/android/app/src/main/AndroidManifest.xml) and **core library desugaring** in [build.gradle.kts](../mobile/android/app/build.gradle.kts), as required by the plugin.

### 8.7 Navigation map

```
LoginScreen ──Register──▶ RegisterScreen (step 1 account → step 2 body details)
     │ Server settings dialog
     ▼ (after login)
HomeShell  [NavigationBar]
 ├─ 0 Home ─────── DashboardScreen ──▶ MealDetailScreen, ProgressScreen, WeeklyReportScreen
 ├─ 1 History ──── HistoryScreen ────▶ MealDetailScreen ──▶ MealEditorScreen (edit)
 ├─ 2 (+) ──────── showLogMealSheet
 │                   ├─ Scan Food Photo ──▶ FoodRecognitionScreen ──▶ MealDetailScreen
 │                   │                         └─ Search ──▶ ManualEntryScreen(pickOnly)
 │                   ├─ Scan Nutrition Label ─▶ LabelScanScreen ──▶ MealDetailScreen
 │                   ├─ Manual Entry ─────▶ ManualEntryScreen ──▶ MealEditorScreen ──▶ MealDetailScreen
 │                   │                         └─ "Can't find it?" ──▶ LabelScanScreen (custom food)
 │                   └─ …from Gallery (photo / label)
 ├─ 3 Alerts ───── NotificationsScreen ──▶ MealDetailScreen, ReminderSettingsScreen
 └─ 4 Profile ──── ProfileScreen ──▶ EditProfile, DietaryProfile, Progress, WeeklyReport,
                                     ReminderSettings, Privacy, Server settings, Log out, Delete
```

`HomeShell` uses an `IndexedStack`, so each tab keeps its scroll position when you switch away. `HomeShell.goToTab(context, i)` lets screens switch tabs; for example, "See all" on the dashboard goes to History. It also listens to app lifecycle events (`didChangeAppLifecycleState`), so it re-syncs and refreshes the badge when the app returns to the foreground.

### 8.8 Screens in detail

| Screen | Key code ideas |
|---|---|
| **Login** | `Form` + `TextFormField` validators show inline errors (mockup requirement); password eye toggle; errors from the server shown under the fields. |
| **Register** | Two steps in one `State` (`_step`). Step 1 is name, email, password, confirm, and a Terms checkbox linking to `PrivacyScreen`. Step 2 is age, gender, height, weight, activity and goal (FR 1.3.1.1 requires these). If the server says the email exists, it jumps back to step 1. |
| **Dashboard** | `FutureBuilder` on `/dashboard/today`. The calorie ring is drawn by `Ring`/`RingPainter`, a `CustomPainter` with arcs. The "Daily Macros" capsules (`MacroPill`) turn red when over the limit. There's a list of `MealTile`s, a "Log a Snack" shortcut, the 7-day `LineChart` with a dashed goal line, an offline-pending banner and pull-to-refresh. |
| **Log Meal sheet** | `showModalBottomSheet` with the three options from the mockup plus gallery buttons. `pickImage` limits images to 2000 px at 88% quality, so uploads are small and fast. |
| **Food Recognition** | Uploads the photo, shows the "95% Match" badge and "Is this Satay?", other top-3 suggestions as chips, a conflict banner, `MealDraftEditor` (portion stepper, nutrient fields, "Edit Details Manually"), **Confirm & Log Meal**, **Retake** and **Search**. If the model is unavailable or confidence is low, it shows the manual-search path. |
| **Label Scan** | Uploads the label and fills editable fields with the per-serving values, serving size and servings eaten. Shows an OCR-accuracy chip and the missing nutrients. Colour-coded ingredient chips can be removed or added. **Confirm & Save** → `createFood` → `saveMeal`. The raw OCR text is available in an expandable section, which helps you measure OCR accuracy. With no image it becomes "Add Custom Food". |
| **Manual Entry** | Search box plus category chips, filtering a cached list on the phone (instant, works offline). A red warning appears under foods that conflict with your profile. |
| **Meal Editor** | Wraps `MealDraftEditor`. Used for new manual meals and for editing a saved single-item meal (`PUT /meals/{id}`). |
| **Meal Detail (Score)** | Score ring and grade, summary, nutrient totals, risk chips coloured by severity, "Why this score" factors with +/− points, healthier alternatives, and the alerts raised by this save. Edit and delete actions. |
| **History** | Date stepper (◀ date ▶, calendar picker, "All dates") plus category chips → `GET /meals?start&end&category` (FR 1.3.3.2). |
| **Notifications** | Grouped by Today / Yesterday / date, with filter chips by type (reminders, allergy & religious, excess nutrients). Each type has its own icon and colour (`_styles`). Unread items are highlighted with a dot. Tapping marks one read and opens the related meal; there is also "Mark all read". |
| **Dietary Preferences** | Toggle chips for allergens, religion (single choice), diet (single choice) and medical conditions, plus custom text fields, all sent with `PUT /dietary-profile`. |
| **Progress** | `SegmentedButton` Daily / Weekly / Monthly. Daily shows progress bars against targets and a macro donut. Weekly and monthly show stat tiles and a `BarChart`, with over-goal days in orange. |
| **Weekly Report** | Week stepper, grouped bar chart (actual vs goal), macro donut, risk-summary `Table`, alerts-breakdown `Table` (Figure 4.25). |
| **Profile** | Daily goal, BMI and goal, profile tags, links to all settings, server address, privacy policy, log out, delete account (with confirmation). |

### 8.9 Reusable widgets

**[common.dart](../mobile/lib/widgets/common.dart)**

| Widget / helper | Purpose |
|---|---|
| `AppCard` | Rounded white card used everywhere; optional `onTap` |
| `Ring` / `RingPainter` | Circular progress, used for kcal left and the score badge |
| `MacroPill` | Fill-up capsule for each macro |
| `ScoreBadge` | Score ring, coloured green / olive / orange / red |
| `ConflictBanner` | Red or orange dietary-alert box |
| `MealCategorySelector` | Breakfast / lunch / dinner / snack choice chips |
| `EmptyState`, `ErrorRetry` | Friendly empty and error screens |
| `showMessage`, `showError` | Snackbars |
| `defaultCategoryForNow()` | Picks the meal category from the time of day |

**[meal_draft_editor.dart](../mobile/lib/widgets/meal_draft_editor.dart)**
- `MealDraft` holds the food, portion, category, time and the optional `manual` nutrition.
  - `nutrition` returns the manual values if set; otherwise it is `food.per100g × portion/100`.
  - `setPortion()` also scales manually edited values proportionally.
  - `toPayload(source)` builds the exact JSON that `POST /meals` expects.
- `MealDraftEditor` is the shared UI for photo, manual and edit flows. It has the portion stepper (±25 g, or ±50 ml for drinks), a typed portion field, read-only or editable nutrient boxes, and a date/time picker.

### 8.10 Theme — [theme.dart](../mobile/lib/theme.dart)

`AppColors` holds the mockup palette (deep green `#1B5E3F`, light grey background, red and orange for alerts). `inputDeco()`, `primaryButtonStyle()` and `secondaryButtonStyle()` give every form field and button the same look, so change them here to restyle the whole app.

---

## 9. End-to-end traces

### 9.1 "I photograph my nasi lemak and save it" (user has a peanut allergy)

| Step | Where | What happens |
|---|---|---|
| 1 | `home_shell.dart` | User taps (+) → `showLogMealSheet` |
| 2 | `log_meal_sheet.dart` `openFoodRecognition` | `image_picker` opens the camera and returns a file path |
| 3 | `food_recognition_screen.dart` `_recognize` | `api.upload('/recognition/predict', path)` |
| 4 | `routers/recognition.py` `recognize_food` | Checks JWT → reads image → thread pool |
| 5 | `food_recognition_service.py` `classify_food` | Resize 224×224 → `model.predict` → top 3, e.g. nasi_lemak 0.93 |
| 6 | `match_food_name` + `food_out` | "nasi_lemak" → FoodItem "Nasi Lemak" (tags peanuts, fish, egg) → conflict: allergy *peanuts* |
| 7 | Flutter | Shows the photo, "93% Match", "Is this Nasi Lemak?", a **red banner**, portion 350 g |
| 8 | `_confirm` → `AppState.saveMeal` | `POST /meals` with `MealDraft.toPayload('photo')` |
| 9 | `meal_logging_service.py` `save_meal` | Builds item (350 g → 644 kcal) → totals → flush |
| 10 | `meal_scoring_engine.py` | Calorie and sodium checks, allergy conflict −40 → **capped at 30**, risks saved, alternatives without peanuts |
| 11 | `dashboard_service.refresh_daily_summary` | Today's totals updated |
| 12 | `notification_service` | `allergy_alert` row created; excess alerts if daily limits are passed |
| 13 | `db.commit()` | All rows saved atomically |
| 14 | Flutter `_pushAlerts` | Phone notification "Allergy alert" |
| 15 | `MealDetailScreen` | Shows score 30 (D), factors, risks, alternatives; `dataVersion++` refreshes the Dashboard, History and Alerts tabs |

### 9.2 "I log a meal with no internet"

1. Manual Entry → `AppState.foods()` → the request fails with `ApiException(offline: true)` → the **cached** list is returned.
2. Pick a food → Meal Editor → `saveMeal` → offline again → the payload is appended to `pending_meals` and `pendingSync` = 1. A snackbar says it will sync.
3. The dashboard shows the orange "1 meal(s) saved offline" banner.
4. Later, when the app resumes or is refreshed, `syncPending()` posts each queued meal. It is scored on the server and the banner disappears.

### 9.3 "I scan a biscuit packet"

`LabelScanScreen._scan` → `POST /label-scan` → `scan_label()` (preprocess → OCR up to 3 tries → parse) → editable form + coloured ingredients → **Confirm & Save** → `POST /foods` (per-serving → per-100 g, tags from ingredients) → `POST /meals` (`source_type: label_scan`) → score screen.

---

## 10. Testing

### Backend — `cd backend && python -m pytest -v` (31 tests)

`conftest.py` points `DATABASE_URL` at a temporary **SQLite** file before the app is imported. The tests therefore never touch MySQL, and every run starts clean. The `auth` fixture registers a fresh user and returns its token header.

| File | What it proves |
|---|---|
| `test_user_management.py` | Successful registration, duplicate email (409), validation errors (422), wrong password (401), protected routes need a token, profile update, the Mifflin-St Jeor formula, account deletion |
| `test_meals_scoring_alerts.py` | Dietary profile save/replace/validation, food conflicts, portion scaling, manual overrides, history filters, delete, other users can't see your meals, update re-scores, label-scan product flow, impossible values rejected, healthy meal scores A, unhealthy meal gets risks and alternatives, allergy cap + alert, halal alert for beer, excess-sugar alert only once per day, hypertension lowers the sodium limit, notifications read/unread, dashboard/progress/weekly-report numbers |
| `test_ocr_parser.py` | US single-column label, Malaysian bilingual two-column label (kJ/kcal, comma decimals), kJ-only conversion, ingredient splitting with brackets, "Contains:" allergens, coconut-milk/peanut-butter false friends, preprocessing variants |

### Mobile — `cd mobile && flutter test`

`test/widget_test.dart` checks `MealDraft`: portion scaling, scaling of manual overrides, the API payload shape, and default portions.

### Static checks

`flutter analyze` (currently **no issues**). The debug APK also builds successfully.

You can turn these test files into the test-case table for your Chapter 5 test plan. Each test function name is one test case, and its asserts are the expected results.

---

## 11. How to modify and extend

| I want to… | Do this |
|---|---|
| **Add or fix a food** | Edit `backend/seed/foods.csv`. The seed only runs when the table is empty, so either add rows in MySQL Workbench, or drop the `calorai` database and restart the server. |
| **Teach the AI a new dish** | Add a folder `my_photos/<dish_name>/` (the name must match a `food_name`, with underscores for spaces) → `prepare_dataset.py --classes …` → `train_food_model.py` → restart the backend. The app needs no changes. |
| **Change scoring weights** | `meal_scoring_engine.py` → `generate_score()`. Each `penalise(...)` call is one rule. `MEAL_SHARE` controls per-meal budgets, and `grade_for()` controls grade boundaries. Re-run `pytest` afterwards. |
| **Change calorie/nutrient formulas** | `nutrition_goals.py` → `daily_targets()` |
| **Add an allergen / religious rule** | `dietary_profile_service.py`: add keywords to `TAG_KEYWORDS`, rules to `RELIGIOUS_RULES`/`DIET_RULES`, chip labels to `COMMON_ALLERGENS`. Add the chip in `mobile/lib/screens/dietary_profile_screen.dart` (`_allergens`, `_religious`, `_diets`). |
| **Support Malay OCR text better** | Install Tesseract's `msa` language data and change `lang="eng"` to `lang="eng+msa"` in `extract_text()`. Add Malay keywords to `NUTRIENT_LINES`. |
| **Change reminder deadlines** | Server: `MEAL_REMINDER_DEADLINES` in `notification_service.py`. Phone defaults: `ReminderService.defaults`. |
| **Add a new API endpoint** | Add a function with `@router.get(...)` in a `routers/*.py` file (use `Depends(get_current_user)`), put the logic in a service, and add a test. It appears in `/docs` automatically. |
| **Add a new screen** | Create `lib/screens/my_screen.dart` (a `StatefulWidget` with a `FutureBuilder` on `context.read<AppState>().api.get(...)`), then `Navigator.push` to it from an existing screen. |
| **Restyle the app** | `theme.dart` colours and button/input helpers |
| **Add a table column** | Add it to the class in `models.py`. `create_all` does **not** alter existing tables, so also run `ALTER TABLE …` in MySQL (or drop and recreate the dev database). Update `schemas.py` and `serializers.py` if the API should expose it. |
| **Deploy for real users** | Use HTTPS (put Nginx or a cloud host in front of Uvicorn), set a strong `JWT_SECRET`, remove `usesCleartextTraffic` from the Android manifest, and restrict CORS. |

---

## 12. Mapping to the report

### Functional requirements → code

| FR | Implemented in |
|---|---|
| 1.3.1.1 Registration (validate, reject duplicate email) | `schemas.RegisterRequest`, `routers/auth.register`, `register_screen.dart` |
| 1.3.1.2 Login + error message | `routers/auth.login`, `security.py`, `login_screen.dart` |
| 1.3.1.3 Profile maintenance | `routers/users.update_me`, `edit_profile_screen.dart` |
| 1.3.2.1–4 Allergies, religion, diet, medical | `routers/dietary.py`, `dietary_profile_service.py`, `nutrition_goals.py`, `dietary_profile_screen.dart` |
| 1.3.3.1 Save meal (category, portion, time) | `meal_logging_service.save_meal`, `MealDraftEditor` |
| 1.3.3.2 Meal history by date/category | `routers/meals.meal_history`, `history_screen.dart` |
| 1.3.3.3 Manual logging from full list | `routers/foods.list_foods`, `manual_entry_screen.dart` |
| 1.3.4.1 Capture/upload label | `log_meal_sheet.dart` (`openLabelScan`) |
| 1.3.4.2 OCR processing | `nutrition_label_scanner.scan_label` |
| 1.3.4.3 Show/edit/save values; ingredient categorisation | `parse_nutrition_values`, `parse_ingredient_list`, `categorise_ingredients`, `label_scan_screen.dart` |
| 1.3.5.1–2 Upload/capture food image | `log_meal_sheet.dart` (`openFoodRecognition`) |
| 1.3.5.3 Classification + confidence | `FoodRecognitionService.classify_food` |
| 1.3.5.4 Show result; confirm or modify | `food_recognition_screen.dart` |
| 1.3.6.1 Meal score | `MealScoringEngine.generate_score` |
| 1.3.6.2 Nutrition risk analysis | `penalise(...)` → `NutritionRisk` rows |
| 1.3.6.3 Personalised feedback + factors | `generate_feedback`, factors list, `meal_detail_screen.dart` |
| 1.3.6.4 Healthy alternatives respecting restrictions | `suggest_healthy_alternatives` |
| 1.3.7.1 Meal reminders | `ReminderService.schedule` (phone) + `check_meal_reminders` (server) |
| 1.3.7.2 Excess nutrition alert | `send_excess_nutrition_alerts` |
| 1.3.7.3 Religious alert | `check_conflicts` → `send_conflict_alerts` (`religious_alert`) |
| 1.3.7.4 Allergy alert | same, `allergy_alert` |
| 1.3.8.1 Daily summary + remaining kcal | `/dashboard/today`, `dashboard_screen.dart` |
| 1.3.8.2 Daily/weekly/monthly progress + charts | `/dashboard/progress`, `progress_screen.dart`, `weekly_report_screen.dart` |

### Non-functional requirements → code

| NFR | How it's addressed |
|---|---|
| Recognition and OCR ≤ 5 s | Model pre-loaded at startup; images downsized on the phone; OCR stops early at confidence ≥ 0.7. `processing_ms` is returned so you can measure it. |
| Dashboard ≤ 2 s | Precomputed `daily_summary` rows; one request for the whole dashboard |
| Scalability (new foods / databases) | New foods are CSV rows or scanned products; new dishes need only retraining; services are separate modules |
| Reliability / recovery | One transaction per meal save; `pool_pre_ping`; offline queue retries |
| Usability | Mockup-based UI, inline validation, friendly errors, empty states |
| Accuracy ≥ 90% / 95% | `evaluation.txt` from training; raw OCR text shown for checking |
| Security / privacy | bcrypt, JWT, per-user data isolation, privacy screen + Terms checkbox, account deletion |
| Offline capability | `OfflineStore` food cache + meal queue |

### Class diagram (Figure 4.16) → code

| Class | File |
|---|---|
| User, DietaryProfile, Allergy, MedicalCondition, Meal, MealItem, FoodItem, MealScore, NutritionRisk, Notification, DailySummary | `backend/app/models.py` (DB) + `mobile/lib/models.dart` (app) |
| FoodRecognitionService (`classifyFood`, `getConfidenceScore`) | `services/food_recognition_service.py` |
| NutritionLabelScanner (`preprocessImage`, `extractText`, `parseNutritionValues`, `parseIngredientList`) | `services/nutrition_label_scanner.py` — functions with the same names |
| MealScoringEngine (`generateScore`, `analyzeNutritionRisk`, `generateFeedback`, `suggestHealthyAlternatives`) | `services/meal_scoring_engine.py` — methods with the same names |
| NotificationService (`sendMealReminder`, `sendExcessNutritionAlert`, `sendReligiousRestrictionAlert`, `sendAllergyAlert`) | `services/notification_service.py` (`check_meal_reminders`, `send_excess_nutrition_alerts`, `send_conflict_alerts`) |
| DashboardService (`getDailySummary`, `getProgressTrend`, `generateCharts`) | `services/dashboard_service.py` (charts are drawn by the app with fl_chart) |
