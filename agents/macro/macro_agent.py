"""
Macro Agent — classifies the current macro regime (risk-on/risk-off/neutral)
from weekly changes in DXY, 10Y yield, oil, gold, and VIX level, plus a
Fed rhetoric-vs-substance divergence signal.
"""
import json
import sys
from datetime import date, datetime
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

FED_EVENTS_PATH = Path(__file__).resolve().parent / "fed_events.json"
FED_DIVERGENCE_LOOKBACK_DAYS = 10


def pct_change_1w(ticker: str) -> float:
    hist = yf.Ticker(ticker).history(period="10d", interval="1d")
    closes = hist["Close"].tolist()
    if len(closes) < 6:
        raise ValueError(f"Insufficient data for {ticker}")
    return round((closes[-1] - closes[-6]) / closes[-6] * 100, 2)


def _substance_read(event: dict) -> str:
    """
    Derive what the Fed communication actually implied, independent of how
    markets/headlines characterized its tone. Anchored on the hard vote
    breakdown plus the realized yield reaction, not on adjectives.
    """
    hike_dissents = event.get("dissents_for_hike", 0)
    cut_dissents = event.get("dissents_for_cut", 0)
    yield_reaction = event.get("yield_10y_reaction_bps", 0)

    if hike_dissents > cut_dissents and yield_reaction > 0:
        return "hawkish"
    if cut_dissents > hike_dissents and yield_reaction < 0:
        return "dovish"
    return "mixed"


def score_fed_divergence(events_path: Path = FED_EVENTS_PATH, as_of: date | None = None) -> tuple[str, str]:
    """
    Returns (vote, notes) where vote is "risk-off" | "risk-on" | "neutral".

    Logic: if the market's initial tone-read of a recent Fed communication
    diverges from what the hard substance (dissent votes + realized yield
    reaction) implies, weight the substance -- a hawkish substance read votes
    risk-off (higher-for-longer rates pressure duration-sensitive assets);
    a dovish substance read votes risk-on. If there's no recent event, or the
    tone-read and substance agree, this contributes no vote (neutral).
    """
    if not events_path.exists():
        return "neutral", "No Fed events log found."

    with open(events_path) as f:
        events = json.load(f).get("events", [])
    if not events:
        return "neutral", "No Fed events logged."

    latest = max(events, key=lambda e: e["date"])
    event_date = datetime.strptime(latest["date"], "%Y-%m-%d").date()
    today = as_of or date.today()

    if (today - event_date).days > FED_DIVERGENCE_LOOKBACK_DAYS:
        return "neutral", f"Most recent Fed event ({latest['date']}) is outside the {FED_DIVERGENCE_LOOKBACK_DAYS}-day lookback window."

    substance = _substance_read(latest)
    tone = latest.get("market_initial_read", "neutral")

    if substance == "mixed" or substance == tone:
        return "neutral", f"Fed {latest['date']}: tone read '{tone}' vs substance read '{substance}' -- no material divergence, no vote added."

    vote = "risk-off" if substance == "hawkish" else "risk-on"
    notes = (
        f"Fed {latest['date']}: market tone read as '{tone}' but substance "
        f"(dissents_for_hike={latest.get('dissents_for_hike', 0)}, "
        f"dissents_for_cut={latest.get('dissents_for_cut', 0)}, "
        f"10Y reaction {latest.get('yield_10y_reaction_bps', 0):+d}bps) reads '{substance}' "
        f"-- divergence detected, voting {vote}."
    )
    return vote, notes


def classify_regime(dxy_chg, yield_chg, oil_chg, gold_chg, vix_level, fed_vote="neutral") -> str:
    """
    Simple, transparent rule-based classifier (not a black box):
    risk-off signals: rising yields + rising DXY + rising VIX + rising gold (flight to safety)
    risk-on signals: falling yields + falling VIX, with oil/gold stable or falling
    fed_vote: additional vote from score_fed_divergence(), "risk-off" | "risk-on" | "neutral"
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

    if fed_vote == "risk-off":
        risk_off_votes += 1
    elif fed_vote == "risk-on":
        risk_on_votes += 1

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

    fed_vote, fed_notes = score_fed_divergence()
    regime = classify_regime(dxy_chg, yield_chg, oil_chg, gold_chg, vix_level, fed_vote)

    notes = (
        f"DXY {dxy_chg:+.2f}%, 10Y yield {yield_chg:+.2f}%, "
        f"Oil {oil_chg:+.2f}%, Gold {gold_chg:+.2f}%, VIX {vix_level}. "
        f"{fed_notes}"
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
