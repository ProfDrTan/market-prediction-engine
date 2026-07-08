"""
Technical Agent — computes trend, RSI, moving-average distance, and momentum
for a given ticker using recent daily price history.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schemas import TechnicalOutput

import yfinance as yf


def compute_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d for d in deltas[-period:] if d > 0]
    losses = [-d for d in deltas[-period:] if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def run(ticker: str) -> TechnicalOutput:
    hist = yf.Ticker(ticker).history(period="1y", interval="1d")
    if hist.empty or len(hist) < 60:
        raise ValueError(f"Insufficient price history for {ticker}")

    closes = hist["Close"].tolist()
    current = closes[-1]

    ma50 = sum(closes[-50:]) / 50
    ma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else sum(closes) / len(closes)

    pct_from_50 = round((current - ma50) / ma50 * 100, 2)
    pct_from_200 = round((current - ma200) / ma200 * 100, 2)
    momentum_20d = round((current - closes[-21]) / closes[-21] * 100, 2) if len(closes) >= 21 else 0.0
    rsi = compute_rsi(closes)

    if pct_from_50 > 1 and pct_from_200 > 1:
        trend = "uptrend"
    elif pct_from_50 < -1 and pct_from_200 < -1:
        trend = "downtrend"
    else:
        trend = "sideways"

    notes = f"RSI {rsi} ({'overbought' if rsi > 70 else 'oversold' if rsi < 30 else 'neutral'})"

    return TechnicalOutput(
        ticker=ticker,
        trend=trend,
        rsi=rsi,
        pct_from_50dma=pct_from_50,
        pct_from_200dma=pct_from_200,
        momentum_20d=momentum_20d,
        notes=notes,
    )
