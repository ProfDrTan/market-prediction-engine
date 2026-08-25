"""Shared data structures for all agents and the synthesis layer."""
from dataclasses import dataclass, field
from datetime import date


@dataclass
class TechnicalOutput:
    ticker: str
    trend: str            # "uptrend" | "downtrend" | "sideways"
    rsi: float
    pct_from_50dma: float
    pct_from_200dma: float
    momentum_20d: float
    notes: str = ""


@dataclass
class MacroOutput:
    regime: str            # "risk-on" | "risk-off" | "neutral"
    dxy_change_1w: float
    yield_10y_change_1w: float
    oil_change_1w: float
    gold_change_1w: float
    vix_level: float
    notes: str = ""


@dataclass
class AlmanacOutput:
    month: int
    seasonal_bias: str     # "bullish" | "bearish" | "neutral"
    avg_return_this_month: float
    win_rate_this_month: float
    years_of_history: int
    notes: str = ""


@dataclass
class ModelCall:
    model_name: str
    direction: str          # "up" | "down" | "flat"
    range_low: float
    range_high: float
    confidence: str          # "low" | "medium" | "high"
    reasoning: str = ""


@dataclass
class SynthesisOutput:
    ticker: str
    prediction_date: date
    model_calls: list[ModelCall] = field(default_factory=list)
    weighted_direction: str = ""
    weighted_range_low: float = 0.0
    weighted_range_high: float = 0.0
    weighted_confidence: str = ""
    weights_used: dict = field(default_factory=dict)


@dataclass
class ActualResult:
    ticker: str
    week_start: date
    pct_change: float
    direction: str


@dataclass
class CalendarEvent:
    date: str              # ISO date, e.g. "2026-08-26"
    time_et: str            # e.g. "17:00" (24h, US Eastern) or "" if all-day/TBD
    label: str              # e.g. "NVIDIA Q2 FY27 earnings (after close)"
    category: str           # "earnings" | "econ_data" | "fed" | "other"
    impact: str = "medium"  # "high" | "medium" | "low" — subjective, human-set
    notes: str = ""


@dataclass
class EventsOutput:
    as_of_date: date
    events_this_week: list = field(default_factory=list)  # list[CalendarEvent]
    chewable_summary: str = ""
    notes: str = ""

