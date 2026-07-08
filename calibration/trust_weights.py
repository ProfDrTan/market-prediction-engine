"""
Trust Weights — the self-learning core of this system.

Team 1's "LLM horse race" tracked which model was closest to actual outcomes,
but only as a manual weekly QA note — it never fed back into future predictions.

This module closes that loop: each model's calibration score (direction hit +
range accuracy) updates a running trust weight via exponential moving average.
Higher-trust models get more influence in next week's synthesized prediction.
This is the concrete mechanism behind "the system gets better over time" —
it is a weighting scheme grounded in tracked accuracy, not a claim that the
system predicts markets reliably.
"""
import json
from pathlib import Path

TRUST_FILE = Path(__file__).resolve().parents[1] / "data" / "trust" / "trust_weights.json"
EMA_ALPHA = 0.3  # weight given to the most recent week's score vs. history
MIN_WEIGHT = 0.05  # no model's weight can be driven to zero — keeps ensemble diverse
DEFAULT_WEIGHT = 1.0


def load_weights() -> dict:
    if TRUST_FILE.exists():
        return json.loads(TRUST_FILE.read_text())
    return {}


def save_weights(weights: dict) -> None:
    TRUST_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRUST_FILE.write_text(json.dumps(weights, indent=2))


def score_to_unit_interval(direction_correct: bool, range_hit: bool) -> float:
    """
    Converts a calibration result into a 0-1 score.
    Direction correct is worth more than range accuracy, since direction
    is the harder, more decision-relevant call.
    """
    score = 0.0
    if direction_correct:
        score += 0.7
    if range_hit:
        score += 0.3
    return score


def update_trust(model_name: str, direction_correct: bool, range_hit: bool) -> float:
    weights = load_weights()
    current = weights.get(model_name, DEFAULT_WEIGHT)
    week_score = score_to_unit_interval(direction_correct, range_hit)
    # EMA update: blend history with this week's performance
    updated = (1 - EMA_ALPHA) * current + EMA_ALPHA * (week_score * 2)  # scale to keep around 1.0 baseline
    updated = max(updated, MIN_WEIGHT)
    weights[model_name] = round(updated, 4)
    save_weights(weights)
    return weights[model_name]


def get_normalized_weights(model_names: list[str]) -> dict:
    """Returns weights for the given models, normalized to sum to 1.0."""
    weights = load_weights()
    raw = {m: weights.get(m, DEFAULT_WEIGHT) for m in model_names}
    total = sum(raw.values()) or 1.0
    return {m: round(w / total, 4) for m, w in raw.items()}
