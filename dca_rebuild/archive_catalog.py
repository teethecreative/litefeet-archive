"""Public, read-only LiteFeet archive catalog assembled from editorial source files.

Legacy rows and editor-submitted flyers are always marked as research under
review. Files contain source assertions/announcements, not confirmed outcomes.
No private ghost profiles, raw submitted images, emails, or unreviewed votes
are exposed through this catalog.
"""
from functools import lru_cache
from pathlib import Path
import json
import re

DATA_DIR = Path(__file__).parent / "data"
COLLECTIONS = (
    ("all", "All records"),
    ("events", "Battles & Events"),
    ("history", "History & Origins"),
    ("people", "People & Crews"),
    ("moves", "Moves & Technique"),
    ("music", "Music & Media"),
    ("awards", "Awards & Recognition"),
)
PAGE_SIZE = 8
MAX_PAGE_SIZE = 16


def _read(name):
    with (DATA_DIR / name).open(encoding="utf-8") as stream:
        return json.load(stream)


def _event(raw, source_kind):
    date = raw.get("date") or ""
    date_label = raw.get("date_label") or "Date to be confirmed"
    # Older seed records use empty dates for unknown dates.
    if not date:
        date_label = date_label if date_label != "Needs confirmation" else "Date not confirmed"
    participants = []
    for part in raw.get("battles", []):
        participants.extend(part.get("items", []))
    details = raw.get("additional_details") or {}
    historical_notes = raw.get("notes", [])
    subtitle = (raw.get("event_format") or "Historical event announcement")
    summary = " · ".join(x for x in [date_label, raw.get("venue"), subtitle] if x)
    return {
        "slug": raw["slug"],
        "title": raw["title"],
        "collection": "events",
        "record_type": "event",
        "date": date,
        "date_label": date_label,
        "date_certainty": raw.get("date_confidence", "reported"),
        "source_kind": source_kind,
        "editorial_status": "Research under review",
        "source_url": "",
        "source_label": ("Editor-submitted event flyer screenshots" if source_kind == "flyers"
                         else "Existing Body Bag event research file"),
        "summary": summary,
        "description": ("An archival record of the announced event and its promotional information. "
                        "Listed participants are not verified results."),
        "presenter": raw.get("presenter") or "",
        "series": raw.get("series") or "",
        "information": [
            (label, val) for label, val in (
                ("Date", date_label),
                ("Presented by", raw.get("presenter") or ""),
                ("Event series", raw.get("series") or ""),
                ("Venue", raw.get("venue") or ""),
                ("Address", raw.get("address") or ""),
                ("Room", raw.get("room") or ""),
                ("Time", raw.get("time") or ""),
                ("Admission", raw.get("admission") or ""),
                ("Host", raw.get("host") or ""),
                ("Hosts", ", ".join(raw.get("hosts") or [])),
                ("Music by", ", ".join(raw.get("music_by") or [])),
                ("Judges", ", ".join(raw.get("judges") or [])),
            ) if val
        ],
        "battles": raw.get("battles") or [],
        "notes": historical_notes,
        # Full archived source data is retained in the source file, not
        # injected into HTML or treated as a published factual conclusion.
        "source_details": details,
        "search": " ".join([raw["title"], summary, raw.get("series") or "",
                           raw.get("presenter") or "", " ".join(participants),
                           " ".join(historical_notes)]).casefold(),
        "can_verify": True,
        "claim": ("The date, location, and battle lineup presented here "
                  "accurately reflect the surviving event announcements."),
    }


def _research(raw):
    typ = raw["record_type"]
    collection = raw["collection"]
    description = raw["summary"]
    original_label = raw.get("research_status") or "Pending Review"
    record = {
        "slug": raw["slug"],
        "title": raw["title"],
        "collection": collection,
        "record_type": typ,
        "date": "",
        "date_label": "Historical research",
        "date_certainty": "unspecified",
        "source_kind": "research",
        "editorial_status": "Research under review",
        "original_label": original_label,
        "source_url": raw.get("source_url") or "",
        "source_label": "Legacy research citation",
        "summary": description,
        "description": description,
        "related_to": raw.get("related_to") or "",
        "research_details": raw.get("research_details") or [],
        "presenter": "",
        "series": "",
        "information": [],
        "battles": [],
        "notes": [],
        "search": " ".join([raw["title"], description, raw.get("related_to") or "",
                           " ".join(x.get("value", "") for x in raw.get("research_details") or [])]).casefold(),
        "can_verify": typ in ("historical_claim", "move_info"),
        "claim": description if typ in ("historical_claim", "move_info") else "",
    }
    return record


@lru_cache(maxsize=1)
def all_records():
    flyers = _read("archive_editor_flyers.json").get("events") or []
    legacy = _read("archive_legacy_events.json").get("events") or []
    research = _read("archive_core_research.json").get("records") or []
    entries = ([_event(x, "flyers") for x in flyers]
               + [_event(x, "legacy") for x in legacy]
               + [_research(x) for x in research])
    slugs = [e["slug"] for e in entries]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Duplicate LiteFeet archive slug")
    # Dated entries first, newest at the top; research with no precise date last.
    entries.sort(key=lambda r: (bool(r["date"]), r["date"], r["title"].casefold()),
                 reverse=True)
    return tuple(entries)


def find_record(slug):
    return next((record for record in all_records() if record["slug"] == slug), None)


def browse(query="", collection="all", page=1, page_size=PAGE_SIZE, timeline=False):
    query = re.sub(r"\s+", " ", (query or "").strip()).casefold()[:120]
    if collection not in dict(COLLECTIONS):
        collection = "all"
    page = max(1, min(int(page), 10000))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    tokens = query.split()
    filtered = []
    for item in all_records():
        if timeline and (item["collection"] != "events" or not item["date"]):
            continue
        if not timeline and collection != "all" and item["collection"] != collection:
            continue
        if any(t not in item["search"] for t in tokens):
            continue
        filtered.append(item)
    start = (page - 1) * page_size
    return {
        "items": filtered[start:start + page_size],
        "count": len(filtered),
        "page": page,
        "has_more": start + page_size < len(filtered),
        "next_page": page + 1,
        "query": query,
        "collection": collection,
    }


def listing_payload(item):
    """Deliberately small public-safe API representation, no private notes."""
    return {k: item[k] for k in (
        "slug", "title", "collection", "record_type", "date", "date_label",
        "date_certainty", "editorial_status", "summary", "series"
    )}
