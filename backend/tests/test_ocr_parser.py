"""Test cases for the Nutrition Label Scanning module's text parsing (no Tesseract needed)."""
import numpy as np
import cv2

from app.services.dietary_profile_service import tags_in_text
from app.services.nutrition_label_scanner import (parse_ingredient_list, parse_nutrition_values,
                                                  preprocess_image)

US_LABEL = """Nutrition Facts
Serving Size 1 Bar (55g)
Servings Per Container 12
Amount Per Serving
Calories 210 Calories from Fat 70
% Daily Value*
Total Fat 8g 12%
Saturated Fat 3.5g 18%
Trans Fat Og
Cholesterol 0mg 0%
Sodium 160mg 7%
Total Carbohydrate 31g 10%
Dietary Fiber 4g 16%
Sugars 12g
Protein 5g
*Percent Daily Values are based on a 2,000 calorie diet.
"""

MY_LABEL = """MAKLUMAT PEMAKANAN / NUTRITION INFORMATION
Saiz hidangan / Serving size: 30 g
Per 100 g   Per serving (30 g)
Tenaga / Energy 1,960 kJ 468 kcal 588 kJ 140 kcal
Karbohidrat / Carbohydrate 60,0 g 18,0 g
Jumlah gula / Total sugars 20.0 g 6.0 g
Protein 6.7 g 2.0 g
Lemak / Fat 22.0 g 6.6 g
Lemak tepu / Saturated fat 10.0 g 3.0 g
Natrium / Sodium 400 mg 120 mg
Ingredients: Wheat flour, sugar, palm oil, milk powder, cocoa powder (5%), emulsifier
(soy lecithin), salt, raising agents.
Contains: wheat, milk, soy. May contain traces of peanuts.
"""


def test_us_label_per_serving():
    n = parse_nutrition_values(US_LABEL)
    s = n["per_serving"]
    assert n["serving_size_g"] == 55
    assert s["calories"] == 210
    assert s["fat"] == 8          # not saturated/trans fat
    assert s["sodium"] == 160
    assert s["carbs"] == 31
    assert s["fibre"] == 4
    assert s["sugar"] == 12
    assert s["protein"] == 5
    assert n["missing"] == []
    assert round(n["per_100g"]["calories"], 1) == round(210 * 100 / 55, 1)


def test_malaysian_bilingual_label_two_columns():
    n = parse_nutrition_values(MY_LABEL)
    assert n["serving_size_g"] == 30
    assert n["per_100g"]["calories"] == 468      # kcal preferred over kJ
    assert n["per_serving"]["calories"] == 140
    assert n["per_100g"]["carbs"] == 60.0        # comma decimal handled
    assert n["per_serving"]["sugar"] == 6.0
    assert n["per_100g"]["fat"] == 22.0          # saturated fat line ignored
    assert n["per_serving"]["sodium"] == 120


def test_kj_only_is_converted():
    n = parse_nutrition_values("Per 100g\nEnergy 418 kJ\nProtein 3g")
    assert n["per_100g"]["calories"] == 99.9


def test_ingredient_list_and_allergens():
    ing = parse_ingredient_list(MY_LABEL)
    names = ing["ingredients"]
    assert names[0] == "Wheat flour"
    assert "cocoa powder (5%)" in names
    assert "emulsifier (soy lecithin)" in names   # comma inside brackets not split
    assert not any("Contains" in n for n in names)
    assert {"gluten", "dairy", "soy"} <= set(ing["contains_tags"])


def test_tagging_false_friends():
    assert "dairy" not in tags_in_text("coconut milk, sugar")
    assert "dairy" in tags_in_text("coconut milk, milk powder")
    assert "peanuts" in tags_in_text("peanut butter")
    assert "dairy" not in tags_in_text("peanut butter")
    assert "pork" in tags_in_text("Lard")
    assert "egg" not in tags_in_text("eggplant")


def test_preprocessing_produces_three_variants():
    img = np.full((400, 600, 3), 255, np.uint8)
    cv2.putText(img, "Protein 5g", (40, 200), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
    ok, buf = cv2.imencode(".png", img)
    variants = preprocess_image(buf.tobytes())
    assert [v[0] for v in variants] == ["otsu", "adaptive", "contrast"]
    assert max(variants[0][1].shape) >= 1500  # upscaled for Tesseract
