"""
Multi-Model Synthesis — queries several LLMs with identical structured prompts,
then combines their calls into one prediction using trust-weighted averaging
instead of a simple majority vote or unweighted average (Team 1's approach).

Requires OPENROUTER_API_KEY (free-tier models) as a GitHub Actions secret.
Uses OpenRouter so multiple providers (not just Anthropic) are queried, matching
Team 1's four-model comparison but with weights that evolve based on tracked
accuracy.
"""
import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agents.schemas import ModelCall, SynthesisOutput, TechnicalOutput, MacroOutput, AlmanacOutput
from calibration.trust_weights import get_normalized_weights

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Free-tier models on OpenRouter, matching Team 1's multi-model approach
MODELS = [
    {"name": "Nemotron", "id": "nvidia/nemotron-3-super-120b-a12b:free"},
    {"name": "GPT-OSS", "id": "openai/gpt-oss-120b:free"},
    {"name": "Gemma", "id": "google/gemma-4-31b-it:free"},
    {"name": "Laguna", "id": "poolside/laguna-m.1:free"},
]

DIRECTION_TO_NUM = {"down": -1, "flat": 0, "up": 1}
NUM_TO_DIRECTION = {-1: "down", 0: "flat", 1: "up"}
CONFIDENCE_LEVELS = ["low", "medium", "high"]


def build_prompt(ticker: str, technical: TechnicalOutput, macro: MacroOutput, almanac: AlmanacOutput) -> str:
    return (
        f"You are one voice in a panel forecasting {ticker}'s move over the next 5 trading days. "
        f"Technical: trend={technical.trend}, RSI={technical.rsi}, momentum_20d={technical.momentum_20d}%. "
        f"Macro regime: {macro.regime} ({macro.notes}). "
        f"Seasonal bias for this month: {almanac.seasonal_bias} "
        f"(avg {almanac.avg_return_this_month*100:.1f}%, win rate {almanac.win_rate_this_month*100:.0f}% "
        f"over {almanac.years_of_history} years). "
        f"Respond with ONLY a JSON object, no other text: "
        f'{{"direction": "up|down|flat", "range_low": <float percent>, "range_high": <float percent>, '
        f'"confidence": "low|medium|high", "reasoning": "<one sentence>"}}. '
        f"This is a probabilistic estimate for an educational project, not investment advice."
    )


def call_openrouter(api_key: str, model_id: str, prompt: str) -> dict:
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["choices"][0]["message"]["content"]
    # strip markdown fences if present
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


def query_all_models(ticker: str, technical, macro, almanac) -> list[ModelCall]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    prompt = build_prompt(ticker, technical, macro, almanac)
    calls = []
    for model in MODELS:
        try:
            result = call_openrouter(api_key, model["id"], prompt)
            calls.append(ModelCall(
                model_name=model["name"],
                direction=result["direction"],
                range_low=float(result["range_low"]),
                range_high=float(result["range_high"]),
                confidence=result["confidence"],
                reasoning=result.get("reasoning", ""),
            ))
        except Exception as e:
            print(f"  {model['name']}: ERROR {e}")
    return calls


def synthesize(ticker: str, model_calls: list[ModelCall]) -> SynthesisOutput:
    """
    Combines model calls into one prediction using trust weights instead of
    a simple average — this is the enhancement over Team 1's unweighted
    four-model comparison.
    """
    if not model_calls:
        raise ValueError("No model calls to synthesize")

    model_names = [c.model_name for c in model_calls]
    weights = get_normalized_weights(model_names)

    weighted_direction_sum = sum(
        DIRECTION_TO_NUM[c.direction] * weights[c.model_name] for c in model_calls
    )
    if weighted_direction_sum > 0.15:
        weighted_direction = "up"
    elif weighted_direction_sum < -0.15:
        weighted_direction = "down"
    else:
        weighted_direction = "flat"

    weighted_low = sum(c.range_low * weights[c.model_name] for c in model_calls)
    weighted_high = sum(c.range_high * weights[c.model_name] for c in model_calls)

    conf_scores = {"low": 0, "medium": 1, "high": 2}
    weighted_conf_num = sum(conf_scores[c.confidence] * weights[c.model_name] for c in model_calls)
    weighted_confidence = CONFIDENCE_LEVELS[round(weighted_conf_num)]

    return SynthesisOutput(
        ticker=ticker,
        prediction_date=date.today(),
        model_calls=model_calls,
        weighted_direction=weighted_direction,
        weighted_range_low=round(weighted_low, 2),
        weighted_range_high=round(weighted_high, 2),
        weighted_confidence=weighted_confidence,
        weights_used=weights,
    )
