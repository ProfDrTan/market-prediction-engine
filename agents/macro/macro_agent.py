"""
Macro Agent — classifies the current macro regime (risk-on/risk-off/neutral)
from weekly changes in DXY, 10Y yield, oil, gold, and VIX level.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schemas import MacroOutput

import yfinance as yf

TICKERS = {
    "dxy": "DX-Y.NYB",
    "yield_10y": "^TNX",
    "oil": "CL=F",
    "gold": "GC=F",
    "vix": "^VIX",
}


def pct_change_1w(ticker: str) -> float:
    hist = yf.Ticker(ticker).history(period="10d", interval="1d")
    closes = hist["Close"].tolist()
    if len(closes) < 6:
        raise ValueError(f"Insufficient data for {ticker}")
    return round((closes[-1] - closes[-6]) / closes[-6] * 100, 2)


def classify_regime(dxy_chg, yield_chg, oil_chg, gold_chg, vix_level) -> str:
    """
    Simple, transparent rule-based classifier (not a black box):
    risk-off signals: rising yields + rising DXY + rising VIX + rising gold (flight to safety)
    risk-on signals: falling yields + falling VIX, with oil/gold stable or falling
    """
    risk_off_votes = 0
    risk_on_votes = 0

    if yield_chg > 0.5:
        risk_off_votes += 1
    elif yield_chg < -0.5:
        risk_on_votes += 1

    if dxy_chg > 0.5:
        risk_off_votes += 1
    elif dxy_chg < -0.5:
        risk_on_votes += 1

    if vix_level > 20:
        risk_off_votes += 1
    elif vix_level < 15:
        risk_on_votes += 1

    if gold_chg > 1.0:
        risk_off_votes += 1

    if risk_off_votes > risk_on_votes:
        return "risk-off"
    elif risk_on_votes > risk_off_votes:
        return "risk-on"
    return "neutral"


def run() -> MacroOutput:
    dxy_chg = pct_change_1w(TICKERS["dxy"])
    yield_chg = pct_change_1w(TICKERS["yield_10y"])
    oil_chg = pct_change_1w(TICKERS["oil"])
    gold_chg = pct_change_1w(TICKERS["gold"])
    vix_hist = yf.Ticker(TICKERS["vix"]).history(period="5d", interval="1d")
    vix_level = round(vix_hist["Close"].tolist()[-1], 2)

    regime = classify_regime(dxy_chg, yield_chg, oil_chg, gold_chg, vix_level)

    notes = (
        f"DXY {dxy_chg:+.2f}%, 10Y yield {yield_chg:+.2f}%, "
        f"Oil {oil_chg:+.2f}%, Gold {gold_chg:+.2f}%, VIX {vix_level}"
    )

    return MacroOutput(
        regime=regime,
        dxy_change_1w=dxy_chg,
        yield_10y_change_1w=yield_chg,
        oil_change_1w=oil_chg,
        gold_change_1w=gold_chg,
        vix_level=vix_level,
        notes=notes,
    )
