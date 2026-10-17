"""Explainable weighted index over eligible measured scores only."""
import math

CATEGORIES = ("mobility", "green", "parking", "sports", "commute")


def calculate_life_score(scores, weights=None):
    requested = {key: 20.0 for key in CATEGORIES}
    if weights is not None:
        requested = {key: float(weights.get(key, 0)) for key in CATEGORIES}
    if any(not math.isfinite(value) or not 0 <= value <= 100 for value in requested.values()):
        raise ValueError("Weights must be finite values between 0 and 100")
    eligible = {key: float(value) for key, value in scores.items() if key in CATEGORIES
                and isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and 0 <= value <= 100}
    selected = {key: value for key, value in requested.items() if key in eligible and value > 0}
    total = sum(selected.values())
    normalized = {key: value / total * 100 for key, value in selected.items()} if total else {}
    value = round(sum(eligible[key] * weight / 100 for key, weight in normalized.items()), 1) if normalized else None
    partial = len(selected) < len(CATEGORIES)
    return {"value": value, "status": "partial" if normalized and partial
            else "available" if normalized else "unavailable",
            "label": ("Partial LifeScore" if partial else "Personalized LifeScore") if normalized else "LifeScore unavailable",
            "requested_weights": requested, "normalized_weights": normalized,
            "contributions": [{"category": key, "score": eligible[key], "weight_percent": weight}
                              for key, weight in normalized.items()],
            "excluded": {key: "No validated numeric category score" if key not in eligible
                         else "Weight is zero" for key in CATEGORIES if key not in normalized},
            "explanation": "Weighted mean of eligible scores with positive weights; missing scores are excluded, never zero."}
