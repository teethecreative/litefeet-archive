"""Public calendar for the next 30 days; never surface historical flyers as upcoming.

Uses event records with ISO dates and confirmed-year metadata, plus an optional
curated JSON file. No speculative events, private admin notes, or test entries.
"""
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from functools import lru_cache
from pathlib import Path
import json

from dca_rebuild.archive_catalog import all_records
from dca_rebuild.models import VaultGatheringSubmission

CURATED_PATH = Path(__file__).parent / "data" / "upcoming_public_events.json"


@lru_cache(maxsize=1)
def curated_events():
    if not CURATED_PATH.exists():
        return ()
    with CURATED_PATH.open(encoding="utf-8") as handle:
        items = json.load(handle).get("events", [])
    return tuple(item for item in items if item.get("status") == "published")


def curated_weekly_events():
    if not CURATED_PATH.exists():
        return ()
    with CURATED_PATH.open(encoding="utf-8") as handle:
        items = json.load(handle).get("weekly_events", [])
    return tuple(item for item in items if item.get("status") == "published")


def upcoming_calendar(today=None, session_factory=None):
    """Return 30 inclusive local calendar days (NY-local date provided by caller)."""
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    end = today + timedelta(days=29)
    entries = []
    seen = set()
    for record in all_records():
        if record.get("collection") != "events" or not record.get("date"):
            continue
        if record.get("date_certainty") in ("unconfirmed_year", "unknown", "undated"):
            continue
        try:
            event_date = date.fromisoformat(record["date"])
        except (TypeError, ValueError):
            continue
        if not (today <= event_date <= end):
            continue
        identity = (event_date.isoformat(), record["title"].casefold())
        if identity in seen:
            continue
        seen.add(identity)
        entries.append(dict(date=event_date.isoformat(), title=record["title"],
                            href="/archive/records/" + record["slug"],
                            status="ANNOUNCED", description=record.get("summary") or ""))
    # Approved public contributions only; private contact and notes never leave admin.
    if session_factory is not None:
        with session_factory() as db:
            approved = db.query(VaultGatheringSubmission).filter(
                VaultGatheringSubmission.status == "approved",
                VaultGatheringSubmission.start_date <= end.isoformat()
            ).all()
            for item in approved:
                try:
                    first_day = date.fromisoformat(item.start_date)
                    until = date.fromisoformat(item.recurrence_until) if item.recurrence_until else None
                except (TypeError, ValueError):
                    continue
                rule = item.recurrence_rule or "none"
                weekdays = set()
                if rule == "weekly":
                    try:
                        weekdays = {int(d) for d in (item.recurrence_weekdays or "").split(",") if d}
                    except ValueError:
                        continue
                    if not weekdays:
                        weekdays = {first_day.weekday()}
                for offset in range(30):
                    day = today + timedelta(days=offset)
                    if day < first_day or (until and day > until):
                        continue
                    matches = False
                    if rule == "daily":
                        matches = True
                    elif rule == "weekly":
                        matches = day.weekday() in weekdays
                    elif rule == "monthly":
                        # Monthly on the same day number; nonexistent dates are skipped.
                        matches = day.day == first_day.day
                    else:
                        matches = day == first_day
                    if not matches:
                        continue
                    identity = (day.isoformat(), item.title.casefold())
                    if identity in seen:
                        continue
                    seen.add(identity)
                    details = " · ".join(part for part in (
                        "–".join((item.start_time or "", item.end_time or "")) if item.start_time and item.end_time else (item.start_time or ""),
                        item.venue, item.address, item.city
                    ) if part)
                    entries.append(dict(date=day.isoformat(), title=item.title,
                                        href=item.link or "/submit", status="COMMUNITY",
                                        description=details or item.gathering_type))
    for item in curated_events():
        try:
            event_date = date.fromisoformat(item["date"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (today <= event_date <= end):
            continue
        identity = (event_date.isoformat(), item["title"].casefold())
        if identity in seen:
            continue
        seen.add(identity)
        entries.append(dict(date=event_date.isoformat(), title=item["title"],
                            href=item.get("href") or "/archive/timeline",
                            status="UPCOMING", description=item.get("venue") or ""))
    # Recurring public sessions are expanded only within the visible calendar window.
    # Closures and schedule changes remain subject to organizer notifications.
    for item in curated_weekly_events():
        weekdays = item.get("weekdays", [])
        for offset in range(30):
            event_date = today + timedelta(days=offset)
            if event_date.weekday() not in weekdays:
                continue
            identity = (event_date.isoformat(), item["title"].casefold())
            if identity in seen:
                continue
            seen.add(identity)
            details = " · ".join(part for part in (
                item.get("time"), item.get("venue"), item.get("notice")) if part)
            entries.append(dict(date=event_date.isoformat(), title=item["title"],
                                href=item.get("href") or "/archive/timeline",
                                status="WEEKLY", description=details))
    for entry in entries:
        entry["display_date"] = date.fromisoformat(entry["date"]).strftime("%B %-d, %Y")
    entries.sort(key=lambda item: (item["date"], item["title"]))
    by_day = {}
    for item in entries:
        by_day.setdefault(item["date"], []).append(item)
    days = []
    for offset in range(30):
        day = today + timedelta(days=offset)
        days.append(dict(iso=day.isoformat(), number=day.day,
                         weekday=day.strftime("%a").upper(), month=day.strftime("%B").upper(),
                         events=by_day.get(day.isoformat(), []), today=offset == 0))
    return dict(start=today.isoformat(), end=end.isoformat(),
                label=today.strftime("%B %d").upper() + " – " + end.strftime("%B %d, %Y").upper(),
                days=days, events=entries)
