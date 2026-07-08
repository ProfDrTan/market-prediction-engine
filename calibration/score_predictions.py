"""
Automated Calibration Scorer — the automation upgrade over Team 1's process.

Team 1 scored predictions manually via a "R10 QA and Learning Log Lead" role
writing markdown by hand each week. This script does the same comparison
programmatically: pulls the actual weekly return, checks each model's call
against it, updates that model's trust weight, and writes a calibration
record — no human step required.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calibration.trust_weights import update_trust

import yfinance as yf

PREDICTIONS_DIR = Path(__file__).resolve().parents[1] / "data" / "predictions"
CALIBRATION_DIR = Path(__file__).resolve().parents[1] / "data" / "calibration"


def get_actual_weekly_return(ticker: str, week_start: date) -> float:
    """Actual % change over the 5 trading days following week_start."""
    end = week_start + timedelta(days=10)
    hist = yf.Ticker(ticker).history(start=week_start.isoformat(), end=end.isoformat(), interval="1d")
    closes = hist["Close"].tolist()
    if len(closes) < 2:
        raise ValueError(f"Insufficient actuals data for {ticker} week of {week_start}")
    # first 5 trading days = the prediction window
    window = closes[:6]
    return round((window[-1] - window[0]) / window[0] * 100, 2)


def direction_from_pct(pct: float) -> str:
    if pct > 0.3:
        return "up"
    elif pct < -0.3:
        return "down"
    return "flat"


def score_prediction_file(prediction_path: Path) -> dict:
    prediction = json.loads(prediction_path.read_text())
    ticker = prediction["ticker"]
    week_start = date.fromisoformat(prediction["prediction_date"])

    actual_pct = get_actual_weekly_return(ticker, week_start)
    actual_direction = direction_from_pct(actual_pct)

    results = {
        "ticker": ticker,
        "week_start": week_start.isoformat(),
        "actual_pct": actual_pct,
        "actual_direction": actual_direction,
        "model_scores": [],
    }

    for call in prediction["model_calls"]:
        direction_correct = call["direction"] == actual_direction
        range_hit = call["range_low"] <= actual_pct <= call["range_high"]
        new_weight = update_trust(call["model_name"], direction_correct, range_hit)
        results["model_scores"].append({
            "model_name": call["model_name"],
            "direction_correct": direction_correct,
            "range_hit": range_hit,
            "updated_trust_weight": new_weight,
        })

    # also score the final synthesized (weighted ensemble) call
    synth_direction_correct = prediction["weighted_direction"] == actual_direction
    synth_range_hit = prediction["weighted_range_low"] <= actual_pct <= prediction["weighted_range_high"]
    results["synthesis_direction_correct"] = synth_direction_correct
    results["synthesis_range_hit"] = synth_range_hit

    return results


def main():
    if not PREDICTIONS_DIR.exists():
        print("No predictions directory found.")
        return

    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    pending = sorted(PREDICTIONS_DIR.glob("*.json"))

    for pred_file in pending:
        cal_file = CALIBRATION_DIR / pred_file.name.replace("prediction_", "calibration_")
        if cal_file.exists():
            continue  # already scored
        try:
            result = score_prediction_file(pred_file)
            cal_file.write_text(json.dumps(result, indent=2))
            print(f"Scored {pred_file.name}: synthesis direction correct = {result['synthesis_direction_correct']}")
        except ValueError as e:
            print(f"Skipping {pred_file.name}: {e}")  # actuals not available yet


if __name__ == "__main__":
    main()
