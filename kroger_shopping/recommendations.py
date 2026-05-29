import re
from typing import Any, Optional, Sequence

from . import unit_pricing
from .models import (
    IngredientPreferenceRule,
    PreferenceProfile,
    Product,
    ProductDetail,
    ProductNutritionInformation,
    ProductPreferenceScore,
    RankedProduct,
)


def ranked_product_sort_key(item: RankedProduct) -> tuple:
    unwanted_count = item.preference_score.unwanted_ingredient_count
    unit_price = unit_pricing.unit_price_for_product(item.product)
    return (
        unwanted_count is None,
        unwanted_count if unwanted_count is not None else 10**9,
        unit_price is None,
        unit_price.price if unit_price is not None else float("inf"),
        -item.preference_score.total,
        item.original_kroger_rank,
    )


def score_product_preference(
    product: Product,
    detail: Optional[ProductDetail],
    original_rank: int,
    candidate_count: int,
    preferences: PreferenceProfile,
) -> ProductPreferenceScore:
    score = 0.0
    reasons = []
    warnings = []
    inspected_fields = ["kroger_rank", "brand"]

    rank_points = max(candidate_count - original_rank + 1, 0) * preferences.kroger_rank_weight
    if rank_points:
        score += rank_points
        reasons.append(f"Kroger result order signal +{rank_points:.2f}")

    brand = (product.brand or (detail.brand if detail else None) or "").strip()
    if brand.lower().startswith("simple truth"):
        score += preferences.simple_truth_bonus
        reasons.append(f"Simple Truth brand +{preferences.simple_truth_bonus:.2f}")

    ingredients, ingredient_fields = extract_ingredient_text(
        detail.raw if detail else None,
        detail.nutrition_information if detail else None,
    )
    inspected_fields.extend(ingredient_fields)
    unwanted_ingredients = []
    ingredient_match_details = []
    unwanted_ingredient_count = None
    if ingredients:
        matches = match_unwanted_ingredients(ingredients, preferences.ingredient_rules)
        unwanted_ingredients = [match["label"] for match in matches]
        ingredient_match_details = matches
        unwanted_ingredient_count = len(matches)
        if matches:
            reasons.append(f"Simple Truth unwanted ingredients: {unwanted_ingredient_count}")
        else:
            reasons.append("Simple Truth unwanted ingredients: 0")
        for match in matches:
            score -= match["penalty"]
            reasons.append(f"Contains {match['label']} -{match['penalty']:.2f}")
    else:
        warnings.append("Ingredients not assessed; Kroger detail did not include ingredient data.")

    nutrition = detail.nutrition_information if detail and detail.nutrition_information else None
    if nutrition:
        inspected_fields.append("nutrition_information")
        score += preferences.nutrition_data_bonus
        reasons.append(f"Nutrition data available +{preferences.nutrition_data_bonus:.2f}")
        health_points = health_signal_points(nutrition, preferences.health_score_weight)
        if health_points:
            score += health_points
            reasons.append(f"Health/nutrition signal +{health_points:.2f}")
    else:
        warnings.append("Nutrition signals not assessed; Kroger detail did not include nutrition data.")

    return ProductPreferenceScore(
        total=round(score, 2),
        reasons=reasons,
        warnings=warnings,
        inspected_fields=sorted(set(inspected_fields)),
        unwanted_ingredient_count=unwanted_ingredient_count,
        unwanted_ingredients=unwanted_ingredients,
        ingredient_match_details=ingredient_match_details,
    )


def match_unwanted_ingredients(
    ingredient_text: str,
    rules: Sequence[IngredientPreferenceRule],
) -> list[dict[str, Any]]:
    normalized_ingredients = normalize_ingredient_text(ingredient_text)
    matches_by_label = {}
    for rule in rules:
        normalized_keyword = normalize_ingredient_text(rule.keyword)
        if not normalized_keyword:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])", normalized_ingredients):
            matches_by_label.setdefault(
                rule.label,
                {
                    "label": rule.label,
                    "keyword": rule.keyword,
                    "penalty": rule.penalty,
                },
            )
    matches = list(matches_by_label.values())
    suppress_broad_unwanted_matches(matches)
    return sorted(matches, key=lambda match: match["label"].lower())


def suppress_broad_unwanted_matches(matches: list[dict[str, Any]]) -> None:
    labels = {match["label"] for match in matches}
    suppressions = {
        "EDTA": ("Calcium disodium EDTA", "Disodium calcium EDTA", "Disodium dihydrogen EDTA", "Tetrasodium EDTA"),
        "Nitrates/nitrites": ("Potassium nitrate or nitrite", "Sodium nitrate/nitrite"),
        "Propionates": ("Calcium propionate", "Sodium propionate"),
        "Benzoates in food": ("Potassium benzoate", "Sodium benzoate"),
        "Guar gum": ("Hydroxypropyl guar gum",),
    }
    broad_labels = {
        broad_label
        for broad_label, specific_labels in suppressions.items()
        if broad_label in labels and any(label in labels for label in specific_labels)
    }
    if broad_labels:
        matches[:] = [match for match in matches if match["label"] not in broad_labels]


def normalize_ingredient_text(value: str) -> str:
    value = value.lower().replace("&", " ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_ingredient_text(
    raw: Optional[dict[str, Any]],
    nutrition_information: Optional[list[ProductNutritionInformation]] = None,
) -> tuple[str, list[str]]:
    values = []
    fields = []

    for index, nutrition in enumerate(nutrition_information or []):
        if nutrition.ingredient_statement:
            values.append(nutrition.ingredient_statement)
            fields.append(f"nutrition_information[{index}].ingredient_statement")

    if values or not raw:
        return " ".join(values), fields

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                next_path = f"{path}.{key}" if path else str(key)
                if "ingredient" in str(key).lower():
                    extracted = stringify_ingredient_value(nested)
                    if extracted:
                        values.append(extracted)
                        fields.append(next_path)
                visit(nested, next_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(raw, "raw")
    return " ".join(values), fields


def stringify_ingredient_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(stringify_ingredient_value(item) for item in value)
    if isinstance(value, dict):
        return " ".join(stringify_ingredient_value(item) for item in value.values())
    return ""


def health_signal_points(nutrition: Any, weight: float) -> float:
    nutrition_values = nutrition if isinstance(nutrition, list) else [nutrition]
    for nutrition_item in nutrition_values:
        if isinstance(nutrition_item, ProductNutritionInformation):
            candidates = {"nutritionalRating": nutrition_item.nutritional_rating}
            if nutrition_item.raw:
                candidates.update(nutrition_item.raw)
        elif isinstance(nutrition_item, dict):
            candidates = nutrition_item
        else:
            continue

        for key in ("healthScore", "nutritionScore", "score", "rating", "optUP", "nutritionalRating"):
            if key not in candidates:
                continue
            try:
                value = float(candidates[key])
            except (TypeError, ValueError):
                continue
            if value > 5:
                value = value / 20
            return round(max(min(value, 5), 0) * weight, 2)
    return 0.0
