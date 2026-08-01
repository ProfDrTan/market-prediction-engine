import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents" / "macro"))
import macro_agent  # noqa: E402


def write_events(tmp_path, events):
    p = tmp_path / "fed_events.json"
    p.write_text(json.dumps({"events": events}))
    return p


def test_divergence_hawkish_substance_dovish_tone_votes_risk_off(tmp_path):
    events = [{
        "date": "2026-07-29",
        "dissents_for_hike": 3,
        "dissents_for_cut": 0,
        "market_initial_read": "dovish",
        "yield_10y_reaction_bps": 5,
    }]
    p = write_events(tmp_path, events)
    vote, notes = macro_agent.score_fed_divergence(p, as_of=date(2026, 8, 1))
    assert vote == "risk-off"
    assert "divergence detected" in notes


def test_no_divergence_when_tone_matches_substance(tmp_path):
    events = [{
        "date": "2026-07-29",
        "dissents_for_hike": 3,
        "dissents_for_cut": 0,
        "market_initial_read": "hawkish",
        "yield_10y_reaction_bps": 5,
    }]
    p = write_events(tmp_path, events)
    vote, notes = macro_agent.score_fed_divergence(p, as_of=date(2026, 8, 1))
    assert vote == "neutral"
    assert "no material divergence" in notes


def test_dovish_substance_hawkish_tone_votes_risk_on(tmp_path):
    events = [{
        "date": "2026-07-29",
        "dissents_for_hike": 0,
        "dissents_for_cut": 2,
        "market_initial_read": "hawkish",
        "yield_10y_reaction_bps": -8,
    }]
    p = write_events(tmp_path, events)
    vote, notes = macro_agent.score_fed_divergence(p, as_of=date(2026, 8, 1))
    assert vote == "risk-on"


def test_event_outside_lookback_window_is_ignored(tmp_path):
    events = [{
        "date": "2026-06-01",
        "dissents_for_hike": 3,
        "dissents_for_cut": 0,
        "market_initial_read": "dovish",
        "yield_10y_reaction_bps": 5,
    }]
    p = write_events(tmp_path, events)
    vote, notes = macro_agent.score_fed_divergence(p, as_of=date(2026, 8, 1))
    assert vote == "neutral"
    assert "lookback window" in notes


def test_mixed_substance_produces_no_vote(tmp_path):
    events = [{
        "date": "2026-07-29",
        "dissents_for_hike": 1,
        "dissents_for_cut": 1,
        "market_initial_read": "dovish",
        "yield_10y_reaction_bps": 5,
    }]
    p = write_events(tmp_path, events)
    vote, notes = macro_agent.score_fed_divergence(p, as_of=date(2026, 8, 1))
    assert vote == "neutral"


def test_missing_events_file_returns_neutral(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    vote, notes = macro_agent.score_fed_divergence(missing, as_of=date(2026, 8, 1))
    assert vote == "neutral"
    assert "No Fed events log found" in notes


def test_classify_regime_fed_vote_can_flip_neutral_to_risk_off():
    # DXY/yield/VIX/gold alone are neutral; fed_vote should tip it to risk-off.
    regime = macro_agent.classify_regime(
        dxy_chg=0.1, yield_chg=0.2, oil_chg=0.0, gold_chg=0.0, vix_level=17,
        fed_vote="risk-off",
    )
    assert regime == "risk-off"


def test_classify_regime_without_fed_vote_unchanged():
    regime = macro_agent.classify_regime(
        dxy_chg=0.1, yield_chg=0.2, oil_chg=0.0, gold_chg=0.0, vix_level=17,
    )
    assert regime == "neutral"
