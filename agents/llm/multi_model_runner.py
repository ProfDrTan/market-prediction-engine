"""
Multi-Model Synthesis — queries several LLMs with identical structured prompts,
then combines their calls into one prediction using trust-weighted averaging
instead of a simple majority vote or unweighted average (Team 1's approach).

Requires OPENROUTER_API_KEY (free-tier models) as a GitHub Actions secret.

=== PROMPT FORMAT — CHANGED 2026-07-09, see build-log.html changelog ===
This used to ask every model for ONLY a JSON object. That failed reliably for
reasoning models (Nemotron, Laguna): they write out their thinking before the
answer, and either burn the whole token budget before reaching the JSON, or
produce JSON buried inside prose that a strict `json.loads` rejects outright.

Team 1's repo (sinder38/Team-1-Prac-A-Project) hits and solves this exact
problem: their system prompt explicitly says "DO NOT OUTPUT JSON FORMAT" and
uses a plain KEY: value text format instead, parsed by scanning every line
for a colon rather than trying to parse the whole response as one JSON blob.
That parser degrades gracefully around reasoning text; a JSON parser doesn't.
MPE now uses the same approach — see agents/llm/base_llm.py equivalent logic
inlined below (MPE doesn't have a separate base_llm.py, so it lives here).
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

MODELS = [
    {"name": "Nemotron", "id": "nvidia/nemotron-3-super-120b-a12b:free"},
    {"name": "GPT-OSS", "id": "openai/gpt-oss-20b:free"},
    {"name": "Gemma", "id": "google/gemma-4-31b-it:free"},
    {"name": "Laguna", "id": "poolside/laguna-m.1:free"},
]

DIRECTION_TO_NUM = {"down": -1, "flat": 0, "up": 1}
NUM_TO_DIRECTION = {-1: "down", 0: "flat", 1: "up"}
CONFIDENCE_LEVELS = ["low", "medium", "high"]

CALL_DELAY_SECONDS = 4
RETRY_DELAY_SECONDS = 12

# System instruction — matches Team 1's wording closely, adapted to MPE's fields.
SYSTEM_INSTRUCTION = (
    "You are a strict financial data formatter. "
    "You MUST output exactly the requested keys in PLAIN TEXT format, separated by colons. "
    "DO NOT OUTPUT JSON FORMAT. "
    "For the range, you MUST strictly use the word 'to' (e.g., 0.5 to 2.0). "
    "Do NOT wrap your response in markdown code blocks."
)


def build_prompt(ticker: str, technical: TechnicalOutput, macro: MacroOutput, almanac: AlmanacOutput) -> str:
    return (
        f"You are one voice in a panel forecasting {ticker}'s move over the next 5 trading days. "
        f"Technical: trend={technical.trend}, RSI={technical.rsi}, momentum_20d={technical.momentum_20d}%. "
        f"Macro regime: {macro.regime} ({macro.notes}). "
        f"Seasonal bias for this month: {almanac.seasonal_bias} "
        f"(avg {almanac.avg_return_this_month*100:.1f}%, win rate {almanac.win_rate_this_month*100:.0f}% "
        f"over {almanac.years_of_history} years). "
        f"Respond in this exact plain-text format, one field per line:\n"
        f"DIRECTION: up, down, or flat\n"
        f"RANGE_LOW: <float percent>\n"
        f"RANGE_HIGH: <float percent>\n"
        f"CONFIDENCE: low, medium, or high\n"
        f"REASONING: <one sentence>\n"
        f"This is a probabilistic estimate for an educational project, not investment advice."
    )


def parse_fields(text) -> dict:
    """
    Scans every line of the raw response for a `KEY: value` pattern, the same
    way Team 1's base_llm.py does — tolerant of reasoning text, extra prose,
    or markdown before/after the actual fields, instead of requiring the
    entire response to be one parseable JSON blob.
    """
    if not text:
        raise ValueError("empty response content")

    lines = {
        line.split(":", 1)[0].strip().upper(): line.split(":", 1)[1].strip()
        for line in text.strip().splitlines()
        if ":" in line
    }

    def require(key: str) -> str:
        value = lines.get(key, "").strip()
        if not value:
            raise ValueError(f"missing required field '{key}' in response")
        return value

    def parse_range(key: str) -> tuple[float, float]:
        val = require(key + "_LOW") if key == "RANGE" else require(key)
        return val

    direction_raw = require("DIRECTION").lower()
    direction = next((d for d in ("up", "down", "flat") if d in direction_raw), None)
    if direction is None:
        raise ValueError(f"could not parse DIRECTION from {direction_raw!r}")

    def parse_float_field(key: str) -> float:
        val = require(key)
        nums = re.findall(r"[-+]?\d*\.?\d+", val)
        if not nums:
            raise ValueError(f"no numeric value found for '{key}' in {val!r}")
        return float(nums[0])

    confidence_raw = require("CONFIDENCE").lower()
    confidence = next((c for c in CONFIDENCE_LEVELS if c in confidence_raw), None)
    if confidence is None:
        raise ValueError(f"could not parse CONFIDENCE from {confidence_raw!r}")

    return {
        "direction": direction,
        "range_low": parse_float_field("RANGE_LOW"),
        "range_high": parse_float_field("RANGE_HIGH"),
        "confidence": confidence,
        "reasoning": lines.get("REASONING", "").strip(),
    }


def call_openrouter(api_key: str, model_id: str, prompt: str) -> dict:
    body = json.dumps({
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 700,  # reasoning models spend tokens on their thinking trace first
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choice = (data.get("choices") or [{}])[0]
    text = choice.get("message", {}).get("content")
    if not text:
        detail = f" (finish_reason={choice.get('finish_reason')!r})"
        raise ValueError(f"empty response content{detail}")
    return parse_fields(text)


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
    """Retry on ANY exception with exponential backoff (1s, 2s, 4s), matching
    Team 1's approach — not just rate-limit errors specifically, since
    transient failures aren't always a 429."""
    max_retries = 3
    last_exc = None
    for attempt in range(max_retries):
        try:
            return call_openrouter(api_key, model["id"], prompt)
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                delay = 2 ** attempt * RETRY_DELAY_SECONDS / 4  # 3s, 6s, 12s-ish backoff
                print(f"  {model['name']}: {e}, retrying after {delay:.0f}s ({attempt+1}/{max_retries})")
                time.sleep(delay)
    raise last_exc


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
