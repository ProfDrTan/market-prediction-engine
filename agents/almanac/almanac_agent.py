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


MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


def chewable_summary(output: AlmanacOutput, ticker: str) -> str:
    """Plain-language read of the AlmanacOutput -- what a raw
    win_rate/avg_return pair actually means in practice, and how much
    weight it deserves. Does not change the underlying score/bias
    calculation in run() above; this is a presentation layer only."""
    month_name = MONTH_NAMES[output.month] if 0 < output.month < 13 else str(output.month)
    years = output.years_of_history
    win_pct = output.win_rate_this_month * 100
    avg_pct = output.avg_return_this_month * 100
    wins = round(output.win_rate_this_month * years)

    if years < 10:
        reliability = (f"Only {years} years of data -- treat this as a weak, "
                        f"low-confidence signal, not a real edge.")
    elif 0.45 <= output.win_rate_this_month <= 0.55:
        reliability = (f"Win rate is close to a coin flip across {years} years -- "
                        f"seasonality alone shouldn't move your sizing much this month.")
    else:
        reliability = (f"That's a {'consistent' if years >= 15 else 'moderately consistent'} "
                        f"historical lean over {years} years, worth weighting alongside "
                        f"technical/macro reads, but not a signal to trade on alone.")

    return (
        f"{ticker} has closed {'higher' if avg_pct >= 0 else 'lower'} in {wins} of the last "
        f"{years} {month_name}s ({win_pct:.0f}% win rate), averaging "
        f"{'+' if avg_pct >= 0 else ''}{avg_pct:.2f}% for the month. "
        f"Seasonal bias: {output.seasonal_bias}. {reliability}"
    )
