"""
Events Agent — surfaces the coming week's known market-moving catalysts
(earnings, econ data releases, Fed events) in plain, actionable language
with times converted to SGT.

Deliberately NOT a live-fetched earnings/econ calendar API integration:
per the same reasoning as bot_core/agents/fundamental/agent.py's ADR-003
(see that file's docstring), this avoids a paid data subscription. Instead
it reads a small manually-curated JSON file (events_calendar.json, same
pattern as agents/macro/fed_events.json) that gets updated weekly.

This means the calendar is only as current as its last manual update --
notes field on EventsOutput says so explicitly if the file looks stale
(no entries dated today or later), rather than silently returning an
empty week and implying "nothing's happening."
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schemas import EventsOutput, CalendarEvent

EVENTS_PATH = Path(__file__).resolve().parent / "events_calendar.json"

# US Eastern is UTC-4 (EDT) for most of the year including August;
# this is a fixed offset for SGT display purposes only, not a full
# timezone-aware conversion -- fine for daylight-saving-season display,
# would need adjustment for events read outside EDT months.
ET_TO_SGT_HOURS = 12


def _et_to_sgt(time_et: str) -> str:
    """Convert an 'HH:MM' ET string to an approximate 'HH:MM SGT' string.
    Returns '' unchanged if time_et is blank (all-day/TBD events)."""
    if not time_et:
        return ""
    try:
        h, m = map(int, time_et.split(":"))
        sgt_h = (h + ET_TO_SGT_HOURS) % 24
        return f"{sgt_h:02d}:{m:02d} SGT"
    except ValueError:
        return ""


def load_events(events_path: Path = EVENTS_PATH) -> list[dict]:
    if not events_path.exists():
        return []
    with open(events_path) as f:
        return json.load(f).get("events", [])


def upcoming_events(as_of: date | None = None, lookahead_days: int = 7) -> list[dict]:
    """Events from today through lookahead_days out, sorted by date.
    Past events (date < today) are silently excluded -- this file is not
    an archive, just a rolling window; prune old entries during the
    weekly manual update instead of relying on this filter alone."""
    as_of = as_of or date.today()
    horizon = as_of + timedelta(days=lookahead_days)
    events = load_events()
    filtered = [
        e for e in events
        if as_of <= datetime.strptime(e["date"], "%Y-%m-%d").date() <= horizon
    ]
    return sorted(filtered, key=lambda e: (e["date"], e.get("time_et") or "99:99"))


IMPACT_EMOJI = {"high": "\U0001F534", "medium": "\U0001F7E1", "low": "\U000026AA"}


def chewable_summary(events: list[dict]) -> str:
    """Plain-language, time-converted digest -- this is the actual answer
    to 'what's moving the market and when', not a regime label."""
    if not events:
        return ("No events on file for the coming week. This means the "
                "calendar hasn't been updated recently, NOT that nothing "
                "is happening -- verify manually before trusting this as "
                "a quiet week.")

    lines = []
    for e in events:
        emoji = IMPACT_EMOJI.get(e.get("impact", "medium"), "")
        sgt = _et_to_sgt(e.get("time_et", ""))
        time_part = f" ({e['time_et']} ET / {sgt})" if sgt else " (time TBD)"
        lines.append(f"{emoji} {e['date']}{time_part} -- {e['label']}")
        if e.get("notes"):
            lines.append(f"    {e['notes']}")
    return "\n".join(lines)


def run(as_of: date | None = None, lookahead_days: int = 7) -> EventsOutput:
    as_of = as_of or date.today()
    events = upcoming_events(as_of, lookahead_days)
    summary = chewable_summary(events)

    calendar_events = [
        CalendarEvent(
            date=e["date"], time_et=e.get("time_et", ""), label=e["label"],
            category=e.get("category", "other"), impact=e.get("impact", "medium"),
            notes=e.get("notes", ""),
        )
        for e in events
    ]

    notes = (f"{len(events)} event(s) on file for the next {lookahead_days} days "
             f"as of {as_of.isoformat()}. Calendar is manually curated "
             f"(events_calendar.json) -- verify anything time-critical "
             f"closer to the actual release; source conflicts on exact "
             f"dates/times are flagged inline in individual event notes "
             f"where known, not silently resolved.")

    return EventsOutput(
        as_of_date=as_of,
        events_this_week=calendar_events,
        chewable_summary=summary,
        notes=notes,
    )


if __name__ == "__main__":
    out = run()
    print(out.chewable_summary)
    print()
    print(out.notes)
