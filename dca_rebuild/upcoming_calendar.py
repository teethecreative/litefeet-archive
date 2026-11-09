"""Public calendar for the next 30 days; never surface historical flyers as upcoming.

Uses event records with ISO dates and confirmed-year metadata, plus an optional
curated JSON file. No speculative events, private admin notes, or test entries.
"""
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from functools import lru_cache
from pathlib import Path
import json
import re

from dca_rebuild.archive_catalog import all_records
from dca_rebuild.models import VaultGatheringSubmission

CURATED_PATH = Path(__file__).parent / "data" / "upcoming_public_events.json"


def event_slug(title):
    """URL-safe identifier for each calendar event on its scheduled day."""
    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or "event"



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


CATEGORY_NAMES = {
    "lab": "Lab Session", "class": "Class", "battle": "Battle",
    "workshop": "Workshop", "link_up": "Link-Up", "press_conference": "Press Conference",
    "awards": "Awards Ceremony", "community": "Community Gathering",
    "other": "Other Event", "event": "Event",
}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _friendly_time(value):
    """Format an ISO 24-hour time without changing already human-readable times."""
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%H:%M").strftime("%I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return value


def _time_range(start, end):
    start_display, end_display = _friendly_time(start), _friendly_time(end)
    return (start_display + "–" + end_display if start_display and end_display
            else start_display or end_display)


def _recurrence_label(rule, weekdays=None, until=None):
    if not rule or rule == "none":
        return ""
    if rule == "weekly":
        try:
            days = sorted({int(x) for x in (weekdays or "").split(",") if x != ""})
            names = [WEEKDAYS[x] for x in days if 0 <= x <= 6]
        except (TypeError, ValueError):
            names = []
        if len(names) == 1:
            label = "Every " + names[0]
        elif len(names) > 1:
            label = "Every " + ", ".join(names[:-1]) + " and " + names[-1]
        else:
            label = "Every week"
    else:
        label = {"daily": "Every day", "monthly": "Every month",
                 "yearly": "Every year"}.get(rule, "")
    if until and label:
        try:
            label += " through " + date.fromisoformat(until).strftime("%B %-d, %Y")
        except (TypeError, ValueError):
            pass
    return label


def _clean_description(description, *duplicates):
    """Do not show details already displayed in venue, timing, or change notices."""
    value = (description or "").strip()
    if not value:
        return ""
    if value in {part for part in duplicates if part}:
        return ""
    # Legacy curated summaries commonly concatenate the exact same fields with middots.
    parts = [p.strip() for p in value.split(" · ")]
    known = {part.strip() for part in duplicates if part}
    parts = [part for part in parts if part and part not in known]
    return " · ".join(parts)

def upcoming_calendar(today=None, session_factory=None, window_days=30):
    """Return an inclusive NY-local calendar window (30 days by default)."""
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    if not isinstance(window_days, int) or not 1 <= window_days <= 366:
        raise ValueError("calendar window must be between 1 and 366 days")
    end = today + timedelta(days=window_days - 1)
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
                            category=record.get("gathering_type") or "event",
                            href="/archive/records/" + record["slug"],
                            status="ANNOUNCED", description=record.get("summary") or "",
                            venue=record.get("venue") or "", event_time=record.get("time") or "",
                            organizer=record.get("host") or "", virtual=False))

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
                last_day = date.fromisoformat(item.end_date) if item.end_date else first_day
                for offset in range(window_days):
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
                    elif rule == "yearly":
                        matches = (day.month, day.day) == (first_day.month, first_day.day)
                    else:
                        # Multi-day, nonrepeating events appear on every scheduled date.
                        matches = first_day <= day <= last_day
                    if not matches:
                        continue
                    identity = (day.isoformat(), item.title.casefold())
                    if identity in seen:
                        continue
                    seen.add(identity)
                    entries.append(dict(
                        date=day.isoformat(), title=item.title,
                        category=item.gathering_type or "event",
                        href=item.link or "", status="COMMUNITY",
                        description=item.description or "",
                        venue=item.venue or "", address=item.address or "",
                        city=item.city or "", virtual=bool(item.virtual),
                        event_time=_time_range(item.start_time, item.end_time),
                        start_time=item.start_time or "", end_time=item.end_time or "",
                        timezone=item.timezone or "America/New_York",
                        organizer=item.hosts or "", admission=item.admission or "",
                        recurrence=_recurrence_label(rule, item.recurrence_weekdays, item.recurrence_until),
                        series_start=item.start_date, series_end=item.end_date or "",
                        recurrence_rule=rule,
                    ))
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
                            category=item.get("category") or "event",
                            href=item.get("href") or "",
                            status="UPCOMING",
                            description=item.get("description") or "",
                            venue=item.get("venue_name") or item.get("venue") or "",
                            address=item.get("address") or "",
                            location_note=item.get("location_note") or "",
                            event_time=_time_range(item.get("start_time"), item.get("end_time")) or item.get("time") or "",
                            start_time=item.get("start_time") or "",
                            end_time=item.get("end_time") or "",
                            timezone="America/New_York",
                            organizer=item.get("host") or "", admission=item.get("admission") or "",
                            notice=item.get("notice") or "", virtual=False,
                            recurrence="", series_start=item["date"], series_end=""))

    # Recurring public sessions are expanded only within the visible calendar window.
    # Closures and schedule changes remain subject to organizer notifications.
    for item in curated_weekly_events():
        weekdays = item.get("weekdays", [])
        for offset in range(window_days):
            event_date = today + timedelta(days=offset)
            if event_date.weekday() not in weekdays:
                continue
            identity = (event_date.isoformat(), item["title"].casefold())
            if identity in seen:
                continue
            seen.add(identity)
            recurrence_days = ",".join(str(i) for i in weekdays)
            entries.append(dict(date=event_date.isoformat(), title=item["title"],
                                category=item.get("category") or "event",
                                href=item.get("href") or "",
                                status="WEEKLY", description=item.get("description") or "",
                                venue=item.get("venue_name") or item.get("venue") or "",
                                address=item.get("address") or "",
                                event_time=_time_range(item.get("start_time"), item.get("end_time")) or item.get("time") or "",
                                start_time=item.get("start_time") or "",
                                end_time=item.get("end_time") or "",
                                timezone="America/New_York",
                                organizer=item.get("host") or "", notice=item.get("notice") or "",
                                virtual=False,
                                recurrence=_recurrence_label("weekly", recurrence_days),
                                series_start="", series_end=""))
    for entry in entries:
        entry["display_date"] = date.fromisoformat(entry["date"]).strftime("%B %-d, %Y")
        entry["category_label"] = CATEGORY_NAMES.get(entry.get("category"), "Event")
        if entry.get("series_end") and entry.get("recurrence_rule") == "none":
            try:
                entry["date_range"] = (
                    date.fromisoformat(entry["series_start"]).strftime("%B %-d, %Y")
                    + " – " + date.fromisoformat(entry["series_end"]).strftime("%B %-d, %Y")
                )
            except (TypeError, ValueError):
                entry["date_range"] = ""
        else:
            entry["date_range"] = ""
        entry["description"] = _clean_description(
            entry.get("description"), entry.get("venue"),
            entry.get("address"), entry.get("event_time"), entry.get("notice"),
        )
        source = entry.pop("href", "")
        entry["source_href"] = source if source and source != "/submit" else ""
        entry["href"] = "/calendar/events/" + entry["date"] + "/" + event_slug(entry["title"])
    entries.sort(key=lambda item: (item["date"], item["title"]))
    by_day = {}
    for item in entries:
        by_day.setdefault(item["date"], []).append(item)
    category_names = {
        "lab": ("Lab Session", "Lab Sessions"),
        "class": ("Class", "Classes"),
        "battle": ("Battle", "Battles"),
        "workshop": ("Workshop", "Workshops"),
        "link_up": ("Link-Up", "Link-Ups"),
        "press_conference": ("Press Conference", "Press Conferences"),
        "awards": ("Awards Ceremony", "Awards Ceremonies"),
        "community": ("Community Gathering", "Community Gatherings"),
        "other": ("Other Event", "Other Events"),
        "event": ("Event", "Events"),
    }
    days = []
    for offset in range(window_days):
        day = today + timedelta(days=offset)
        day_events = by_day.get(day.isoformat(), [])
        counts = {}
        for event in day_events:
            category = event.get("category") or "event"
            if category not in category_names:
                category = "event"
            counts[category] = counts.get(category, 0) + 1
        count_labels = [
            {"count": count, "label": category_names[category][0 if count == 1 else 1]}
            for category, count in counts.items()
        ]
        days.append(dict(iso=day.isoformat(), number=day.day,
                         weekday=day.strftime("%a").upper(), month=day.strftime("%B").upper(),
                         events=day_events, category_counts=count_labels,
                         today=day == datetime.now(ZoneInfo("America/New_York")).date()))
    return dict(start=today.isoformat(), end=end.isoformat(),
                label=today.strftime("%B %d").upper() + " – " + end.strftime("%B %d, %Y").upper(),
                days=days, events=entries)
