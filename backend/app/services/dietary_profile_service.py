"""Dietary Profile Service: ingredient tagging and conflict detection against a user's
allergies, religious restriction and diet preference."""
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import DietaryProfile, FoodItem, User

# Canonical ingredient tag -> keywords (English + Malay) that indicate it in food names or
# ingredient lists. Matched on word boundaries.
TAG_KEYWORDS: dict[str, list[str]] = {
    "peanuts": ["peanut", "peanuts", "groundnut", "groundnuts", "kacang tanah", "arachis"],
    "tree_nuts": ["almond", "almonds", "cashew", "cashews", "walnut", "walnuts", "hazelnut",
                  "hazelnuts", "pecan", "pistachio", "macadamia", "tree nut", "tree nuts"],
    "shellfish": ["shrimp", "shrimps", "prawn", "prawns", "crab", "lobster", "belacan", "udang",
                  "shellfish", "crustacean", "crustaceans", "oyster", "clam", "mussel", "scallop",
                  "squid", "sotong", "cockle", "cockles"],
    "fish": ["fish", "anchovy", "anchovies", "ikan", "ikan bilis", "tuna", "salmon", "sardine",
             "sardines", "cod", "mackerel", "fish sauce"],
    "dairy": ["milk", "milk powder", "cream", "butter", "cheese", "whey", "casein", "caseinate",
              "lactose", "yogurt", "yoghurt", "ghee", "susu", "dairy", "buttermilk"],
    "egg": ["egg", "eggs", "egg white", "egg yolk", "albumin", "telur", "mayonnaise"],
    "gluten": ["wheat", "wheat flour", "gluten", "barley", "rye", "malt", "malt extract",
               "semolina", "spelt", "tepung gandum"],
    "soy": ["soy", "soya", "soybean", "soybeans", "soy sauce", "tofu", "kicap", "edamame",
            "tempeh", "soy lecithin"],
    "sesame": ["sesame", "bijan", "tahini"],
    "pork": ["pork", "lard", "bacon", "ham", "porcine", "babi", "char siu", "pepperoni",
             "salami", "prosciutto"],
    "alcohol": ["alcohol", "wine", "rum", "beer", "ethanol", "liqueur", "mirin", "sake",
                "brandy", "arak", "whisky", "vodka"],
    "beef": ["beef", "daging lembu", "bovine"],
    "chicken": ["chicken", "ayam"],
    "mutton": ["mutton", "lamb", "kambing"],
    "gelatin": ["gelatin", "gelatine"],
    "honey": ["honey", "madu"],
}

COMMON_ALLERGENS = ["Peanuts", "Tree nuts", "Shellfish", "Fish", "Dairy", "Egg", "Gluten", "Soy",
                    "Sesame"]
RELIGIOUS_OPTIONS = {"halal": "Halal", "kosher": "Kosher", "no_beef": "No Beef (Hindu)"}
DIET_OPTIONS = {"none": "None", "vegetarian": "Vegetarian", "vegan": "Vegan", "keto": "Keto",
                "paleo": "Paleo"}
COMMON_CONDITIONS = ["Diabetes", "Hypertension", "High Cholesterol", "Kidney Disease"]

RELIGIOUS_RULES: dict[str, dict[str, str]] = {
    # tag -> severity
    "halal": {"pork": "high", "alcohol": "high", "gelatin": "medium"},
    "kosher": {"pork": "high", "shellfish": "high", "gelatin": "medium"},
    "no_beef": {"beef": "high"},
}
MEAT_TAGS = {"chicken", "beef", "pork", "mutton", "fish", "shellfish", "gelatin"}
DIET_RULES: dict[str, set[str]] = {
    "vegetarian": MEAT_TAGS,
    "vegan": MEAT_TAGS | {"dairy", "egg", "honey"},
    "paleo": {"gluten", "dairy", "soy", "peanuts"},
}

ALLERGEN_TAGS = {"peanuts", "tree_nuts", "shellfish", "fish", "dairy", "egg", "gluten", "soy",
                 "sesame"}

_patterns = {
    tag: re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(kws, key=len, reverse=True))
                    + r")\b", re.IGNORECASE)
    for tag, kws in TAG_KEYWORDS.items()
}


# Phrases that contain a keyword but are NOT that allergen (e.g. coconut milk is not dairy)
_FALSE_FRIENDS = re.compile(
    r"\b(coconut milk|coconut cream|santan|almond milk|soy milk|soya milk|oat milk|peanut butter|"
    r"cocoa butter|shea butter|cream of tartar)\b", re.IGNORECASE)


def tags_in_text(text: str) -> set[str]:
    text = text or ""
    tags = {tag for tag, pat in _patterns.items() if pat.search(text)}
    if "dairy" in tags and not _patterns["dairy"].search(_FALSE_FRIENDS.sub(" ", text)):
        tags.discard("dairy")
    # the false-friend phrase itself still carries its real allergen (peanut butter -> peanuts)
    return tags


def allergy_to_tag(name: str) -> str | None:
    """Map a user-entered allergy ('Peanuts', 'prawn', 'Tree nuts') to a canonical tag."""
    n = name.strip().lower().replace("-", " ")
    key = n.replace(" ", "_")
    if key in TAG_KEYWORDS:
        return key
    found = tags_in_text(n)
    return next(iter(found)) if len(found) == 1 else None


@dataclass
class ConflictResult:
    kind: str  # allergy | religious | diet
    tag: str
    severity: str
    message: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def food_tags(food: FoodItem) -> set[str]:
    return food.tags | tags_in_text(food.food_name)


def check_conflicts(tags: set[str], text: str, profile: DietaryProfile | None,
                    subject: str = "This food") -> list[ConflictResult]:
    if profile is None:
        return []
    out: list[ConflictResult] = []
    text_l = (text or "").lower()

    for allergy in profile.allergies:
        tag = allergy_to_tag(allergy.allergen_name)
        hit = (tag in tags) if tag else bool(
            re.search(r"\b" + re.escape(allergy.allergen_name.lower()) + r"\b", text_l))
        if hit:
            out.append(ConflictResult("allergy", tag or allergy.allergen_name.lower(), "high",
                                      f"{subject} may contain {allergy.allergen_name}, "
                                      f"which is in your allergy list."))

    rel = (profile.religious_restriction or "").lower()
    for tag, severity in RELIGIOUS_RULES.get(rel, {}).items():
        if tag in tags:
            label = RELIGIOUS_OPTIONS.get(rel, rel.title())
            what = "gelatin of unknown source" if tag == "gelatin" else tag
            out.append(ConflictResult("religious", tag, severity,
                                      f"{subject} may contain {what}, which does not comply "
                                      f"with your {label} restriction."))

    diet = (profile.diet_preference or "none").lower()
    for tag in sorted(DIET_RULES.get(diet, set()) & tags):
        out.append(ConflictResult("diet", tag, "medium",
                                  f"{subject} contains {tag.replace('_', ' ')}, which is not "
                                  f"suitable for a {diet} diet."))
    return out


def food_conflicts(food: FoodItem, profile: DietaryProfile | None) -> list[ConflictResult]:
    return check_conflicts(food_tags(food), food.food_name, profile, subject=food.food_name)


def get_or_create_profile(db: Session, user: User) -> DietaryProfile:
    if user.profile is None:
        user.profile = DietaryProfile(user_id=user.user_id, diet_preference="none")
        db.add(user.profile)
        db.commit()
        db.refresh(user)
    return user.profile
