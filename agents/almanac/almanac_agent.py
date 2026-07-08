"""
Almanac Agent — seasonal bias for the current calendar month, based on
historical monthly returns (reuses the tested seasonality logic from the
us-seasonality-tool project).
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schemas import AlmanacOutput

import yfinance as yf

LOOKBACK_YEARS = 20


def compute_monthly_stats(closes_with_dates, target_month: int):
    returns = []
    for i in range(1, len(closes_with_dates)):
        prev_date, prev_close = closes_with_dates[i - 1]
        curr_date, curr_close = closes_with_dates[i]
        if curr_date.month != target_month or prev_close == 0:
            continue
        returns.append((curr_close - prev_close) / prev_close)
    if not returns:
        return None, None, 0
    avg_return = sum(returns) / len(returns)
    win_rate = sum(1 for r in returns if r > 0) / len(returns)
    return avg_return, win_rate, len(returns)


def run(ticker: str, as_of: date | None = None) -> AlmanacOutput:
    as_of = as_of or date.today()
    hist = yf.Ticker(ticker).history(period=f"{LOOKBACK_YEARS}y", interval="1mo")
    if hist.empty:
        raise ValueError(f"No history for {ticker}")

    hist = hist.reset_index()
    closes_with_dates = [(row["Date"].date(), row["Close"]) for _, row in hist.iterrows()]

    avg_return, win_rate, years = compute_monthly_stats(closes_with_dates, as_of.month)

    if avg_return is None:
        bias, avg_return, win_rate = "neutral", 0.0, 0.5
    elif avg_return > 0.005 and win_rate > 0.55:
        bias = "bullish"
    elif avg_return < -0.005 and win_rate < 0.45:
        bias = "bearish"
    else:
        bias = "neutral"

    notes = f"{years} years of history for month {as_of.month}; avg {avg_return*100:.2f}%, win rate {win_rate*100:.0f}%"

    return AlmanacOutput(
        month=as_of.month,
        seasonal_bias=bias,
        avg_return_this_month=round(avg_return, 4),
        win_rate_this_month=round(win_rate, 4),
        years_of_history=years,
        notes=notes,
    )
