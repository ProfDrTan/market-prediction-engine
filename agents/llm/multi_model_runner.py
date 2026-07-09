"""
Multi-Model Synthesis — queries several LLMs with identical structured prompts,
then combines their calls into one prediction using trust-weighted averaging
instead of a simple majority vote or unweighted average (Team 1's approach).

Requires OPENROUTER_API_KEY (free-tier models) as a GitHub Actions secret.
Uses OpenRouter so multiple providers (not just Anthropic) are queried, matching
Team 1's four-model comparison but with weights that evolve based on tracked
accuracy.

Reliability notes (added after the first live run surfaced real failures):
- Free-tier OpenRouter models are rate-limited; firing 4 calls back-to-back
  per ticker across 3 tickers triggered 429s. A short pacing delay plus a
  single retry-on-429 fixes this without needing paid credits.
- Some free models don't reliably return clean JSON even when asked to.
  extract_json() pulls the first {...} block out of whatever text comes back
  instead of assuming the whole response is valid JSON.
- A model can return empty/None content; every step that touches the raw
  text now guards against that instead of assuming a string.
"""
import json
import os
import re
import sys
import time
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

# Pacing between calls to stay under free-tier per-minute rate limits.
CALL_DELAY_SECONDS = 4
RETRY_DELAY_SECONDS = 12


def build_prompt(ticker: str, technical: TechnicalOutput, macro: MacroOutput, almanac: AlmanacOutput) -> str:
    return (
        f"You are one voice in a panel forecasting {ticker}'s move over the next 5 trading days. "
        f"Technical: trend={technical.trend}, RSI={technical.rsi}, momentum_20d={technical.momentum_20d}%. "
        f"Macro regime: {macro.regime} ({macro.notes}). "
        f"Seasonal bias for this month: {almanac.seasonal_bias} "
        f"(avg {almanac.avg_return_this_month*100:.1f}%, win rate {almanac.win_rate_this_month*100:.0f}% "
        f"over {almanac.years_of_history} years). "
        f"Do not show your reasoning or thinking process. Respond with ONLY the JSON object below, "
        f"nothing before it and nothing after it: "
        f'{{"direction": "up|down|flat", "range_low": <float percent>, "range_high": <float percent>, '
        f'"confidence": "low|medium|high", "reasoning": "<one sentence>"}}. '
        f"This is a probabilistic estimate for an educational project, not investment advice."
    )


def extract_json(text, raw_response=None) -> dict:
    """
    Pulls the first {...} block out of a model's raw response instead of
    assuming the whole string is valid JSON. Handles markdown fences, stray
    prose before/after the JSON, and raises a clear error on empty content
    rather than crashing on .strip() against None.
    """
    if not text:
        # Surface WHY it was empty (finish_reason, any error field) instead of
        # a bare "empty response content" that gives no debugging signal.
        detail = ""
        if raw_response:
            choice = (raw_response.get("choices") or [{}])[0]
            detail = f" (finish_reason={choice.get('finish_reason')!r}, raw_choice={choice!r})"
        raise ValueError(f"empty response content{detail}")
    text = text.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object found in response: {text[:200]!r}")
    return json.loads(match.group(0))


def call_openrouter(api_key: str, model_id: str, prompt: str) -> dict:
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 700,  # reasoning models (e.g. Nemotron) spend tokens on their thinking trace before the JSON
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["choices"][0]["message"].get("content")
    return extract_json(text, raw_response=data)


def query_all_models(ticker: str, technical, macro, almanac) -> list[ModelCall]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    prompt = build_prompt(ticker, technical, macro, almanac)
    calls = []
    for i, model in enumerate(MODELS):
        if i > 0:
            time.sleep(CALL_DELAY_SECONDS)
        try:
            result = _call_with_retry(api_key, model, prompt)
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


def _call_with_retry(api_key: str, model: dict, prompt: str) -> dict:
    """One retry on 429 (rate limit) after a longer backoff; every other
    error type is not worth retrying and fails immediately."""
    try:
        return call_openrouter(api_key, model["id"], prompt)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"  {model['name']}: 429, retrying once after {RETRY_DELAY_SECONDS}s")
            time.sleep(RETRY_DELAY_SECONDS)
            return call_openrouter(api_key, model["id"], prompt)
        raise


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
