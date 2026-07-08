"""
Main Pipeline — runs all four agents for each tracked ticker, queries the
multi-model panel, synthesizes a trust-weighted prediction, and saves it.

Run weekly via GitHub Actions (see .github/workflows/weekly-pipeline.yml).
"""
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agents.technical import technical_agent
from agents.macro import macro_agent
from agents.almanac import almanac_agent
from agents.llm.multi_model_runner import query_all_models, synthesize

TICKERS = ["^GSPC", "^NDX", "IWM"]  # S&P 500, Nasdaq 100, Russell 2000
PREDICTIONS_DIR = Path(__file__).resolve().parent / "data" / "predictions"


def run_for_ticker(ticker: str, macro_output) -> dict:
    print(f"Running pipeline for {ticker}...")
    technical = technical_agent.run(ticker)
    almanac = almanac_agent.run(ticker)

    print(f"  Technical: {technical.trend}, RSI {technical.rsi}")
    print(f"  Almanac: {almanac.seasonal_bias} bias for month {almanac.month}")
    print(f"  Macro regime: {macro_output.regime}")

    model_calls = query_all_models(ticker, technical, macro_output, almanac)
    if not model_calls:
        print(f"  No model calls succeeded for {ticker}, skipping synthesis.")
        return None

    synthesis = synthesize(ticker, model_calls)
    print(f"  Synthesized: {synthesis.weighted_direction} "
          f"({synthesis.weighted_range_low}% to {synthesis.weighted_range_high}%), "
          f"confidence {synthesis.weighted_confidence}")

    return {
        "ticker": ticker,
        "prediction_date": date.today().isoformat(),
        "technical": asdict(technical),
        "macro": asdict(macro_output),
        "almanac": asdict(almanac),
        "model_calls": [asdict(c) for c in model_calls],
        "weighted_direction": synthesis.weighted_direction,
        "weighted_range_low": synthesis.weighted_range_low,
        "weighted_range_high": synthesis.weighted_range_high,
        "weighted_confidence": synthesis.weighted_confidence,
        "weights_used": synthesis.weights_used,
    }


def main():
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Macro is regime-level, not ticker-specific — run once and share across tickers
    macro_output = macro_agent.run()

    for ticker in TICKERS:
        try:
            result = run_for_ticker(ticker, macro_output)
        except Exception as e:
            print(f"ERROR running pipeline for {ticker}: {e}")
            continue
        if result is None:
            continue

        safe_ticker = ticker.replace("^", "")
        out_path = PREDICTIONS_DIR / f"prediction_{date.today().isoformat()}_{safe_ticker}.json"
        out_path.write_text(json.dumps(result, indent=2))
        print(f"  Saved to {out_path}")


if __name__ == "__main__":
    main()
