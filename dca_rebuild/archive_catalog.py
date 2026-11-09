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
    ("awards", "Awards & Recognition"),
)
PAGE_SIZE = 8
MAX_PAGE_SIZE = 16
PEOPLE_CLOUD_LIMIT = 20

# Only explicitly program-oriented details are suitable for the public record.
# Editorial doubts, missing citations and publishing instructions are admin-only.
PUBLIC_EVENT_NOTE_PREFIXES = (
    "All ages welcome", "Out the Hat battles advertised",
    "Class roster advertised", "Flyer says all dancers",
    "Flyer asks attendees", "Flyer mentions Zelle",
    "Event includes tag-team", "Finalists advertised separately",
    "Color-theme picnic", "Color-themed picnic",
    "Advertised music, games", "Halloween theme",
    "Cartoon-character-themed",
)


def partition_event_notes(notes):
    public, editorial = [], []
    for note in notes or []:
        (public if note.startswith(PUBLIC_EVENT_NOTE_PREFIXES) else editorial).append(note)
    return public, editorial


def public_record(item):
    """Exclude raw seed details, source-management notes and editorial annotations."""
    allowed = (
        "slug", "title", "collection", "record_type", "date", "date_label",
        "date_certainty", "source_kind", "editorial_status", "source_url",
        "source_label", "summary", "description", "presenter", "series",
        "information", "battles", "notes", "lineup_participants",
        "related_to", "research_findings", "research_sources",
        "can_verify", "claim",
    )
    return {key: item[key] for key in allowed if key in item}


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
    public_notes, editorial_notes = partition_event_notes(raw.get("notes", []))
    subtitle = raw.get("event_format") or ""
    # The date is already presented in the row: show the venue only once.
    summary = " · ".join(x for x in [raw.get("venue"), subtitle] if x) or "Event announcement"
    if raw.get("date_confidence") == "unconfirmed_year":
        date_label = date_label.split(" (year ")[0] + " · Year unconfirmed"
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
        "notes": public_notes,
        "editorial_notes": editorial_notes,
        "source_details": details,
        "lineup_participants": [
            {"name": battle.get("name", ""), "featuring": battle["featuring"]}
            for battle in details.get("battles", [])
            if isinstance(battle, dict) and battle.get("featuring")
        ],
        "search": " ".join([raw["title"], summary, raw.get("series") or "",
                           raw.get("presenter") or "", " ".join(participants),
                           " ".join(public_notes)]).casefold(),
        "can_verify": True,
        "claim": ("The date, location, and battle lineup presented here "
                  "accurately reflect the surviving event announcements."),
    }


def _research(raw, enrichment=None):
    enrichment = enrichment or {}
    typ = raw["record_type"]
    collection = ("music" if raw["title"] == "Get Lite to LiteFeet Music Evolution"
                  else raw["collection"])
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
        "research_findings": enrichment.get("findings") or [],
        "research_sources": enrichment.get("source_links") or [],
        "editorial_notes": [
            str(detail.get("label") or "NOTE") + ": " + str(detail.get("value") or "")
            for detail in (raw.get("research_details") or [])
            if detail.get("label") not in ("Claim Text", "Move Origin / Context", "Known For")
        ],
        "presenter": "",
        "series": "",
        "information": [],
        "battles": [],
        "notes": [],
        "search": " ".join([raw["title"], description,
                           raw.get("related_to") or ""]).casefold(),
        "can_verify": typ in ("historical_claim", "move_info"),
        "claim": description if typ in ("historical_claim", "move_info") else "",
    }
    return record



def _legacy_public_people(research):
    """Public name-only index from the preserved archive, not verified biographies.

    Consolidate exactly matching normalized legacy names for display, retaining
    every source ID. Existing published research profiles win when an exact
    primary name or slash-separated alias matches: avoid duplicate pages.
    """
    published = _read("archive_recovered_identities.json").get("records") or []
    def identity_key(value):
        return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())

    known = {
        identity_key(part.strip())
        for original in research if original.get("collection") == "people"
        for part in original["title"].split("/")
    }
    records = []
    for row in published:
        if identity_key(row["name"]) in known:
            continue
        aliases = row.get("aliases") or []
        roles = row.get("reported_roles") or []
        summary = ("Name preserved in a 2026 LiteFeet archive export. "
                   "Biographical details and affiliations have not been verified.")
        records.append({
            "slug": row["slug"], "title": row["name"],
            "collection": "people", "record_type": "legacy_identity",
            "date": "", "date_label": "Date not recorded",
            "date_certainty": "unspecified", "source_kind": "legacy_name",
            "editorial_status": "Recovered name · details unverified",
            "source_url": "",
            "source_label": "August 29, 2026 legacy preservation export",
            "summary": summary, "description": summary,
            "presenter": "", "series": "", "related_to": "",
            "information": [
                ("Preserved source IDs", ", ".join(map(str, row["source_ids"]))),
                ("Recorded name variations", ", ".join(aliases) if aliases else "None"),
                ("Original role labels (unverified)", ", ".join(roles) if roles else "Not recorded"),
            ],
            "battles": [], "notes": [],
            "search": " ".join([row["name"], *aliases, *roles, summary]).casefold(),
            "can_verify": False, "claim": "",
        })
    return records


@lru_cache(maxsize=1)
def all_records():
    flyers = _read("archive_editor_flyers.json").get("events") or []
    legacy = _read("archive_legacy_events.json").get("events") or []
    research = _read("archive_core_research.json").get("records") or []
    enrichments = _read("archive_research_enrichment.json").get("records") or {}
    awards_archive = {
        "slug": "dancers-choice-awards-august-2023",
        "title": "Dancer’s Choice Awards — August 2023",
        "collection": "awards", "record_type": "award_archive",
        "date": "", "date_label": "August 2023",
        "date_certainty": "month",
        "source_kind": "awards", "editorial_status": "Archived results",
        "source_url": "/awards/dancers-choice/2023",
        "source_label": "Original Dancer’s Choice Awards historical import",
        "summary": "31 historical categories, 152 nominee entries and 32 recorded winning entries.",
        "description": "The original August 2023 Dancer’s Choice Awards archive "
                       "preserves nominee entries and recorded winning entries. "
                       "It is independent of current award nominations.",
        "related_to": "", "research_details": [], "series": "Dancer’s Choice Awards",
        "information": [
            ("Edition", "August 2023"), ("Categories", "31"),
            ("Nominee entries", "152"), ("Winning entries", "32")],
        "battles": [], "notes": [], "presenter": "",
        "search": "dancers choice awards august 2023 historic winners nominees results",
        "can_verify": False, "claim": "",
    }
    entries = ([_event(x, "flyers") for x in flyers]
               + [_event(x, "legacy") for x in legacy]
               + [_research(x, enrichments.get(x["slug"])) for x in research]
               + _legacy_public_people(research)
               + [awards_archive])
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
        if item.get("collection") == "music":
            continue
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


def people_crew_cloud():
    """Weighted index of known public people/crew profiles.

    Names and aliases are derived exclusively from published archive profiles;
    do not create public ghost profiles from unverified event lineups.
    A record contributes at most one mention for each matched profile.
    """
    profiles = [r for r in all_records() if r['collection'] == 'people']
    documents = [r for r in all_records() if r['collection'] != 'people']
    result = []
    for profile in profiles:
        aliases = [v.strip() for v in profile['title'].split('/') if v.strip()]
        # Short aliases risk matching unrelated words; require at least 4 letters.
        patterns = [re.compile(r'(?<!\\w)' + re.escape(alias) + r'(?!\\w)', re.I)
                    for alias in aliases if len(alias) >= 4]
        mentions = 0
        for doc in documents:
            fragments = [doc.get('title', ''), doc.get('description', ''),
                         doc.get('related_to', '')]
            if doc.get('collection') == 'events':
                for group in doc.get('battles', []):
                    fragments.extend(str(i) for i in group.get('items', []))
                for pair in doc.get('lineup_participants', []):
                    fragments.extend(pair.get('featuring', []))
            if any(pattern.search(' '.join(fragments)) for pattern in patterns):
                mentions += 1
        result.append(dict(
            title=profile['title'].split('/')[0].strip(),
            full_name=profile['title'],
            slug=profile['slug'],
            mentions=mentions,
            # Baseline weight of one, growing with documented cross-references.
            weight=1 + mentions,
        ))
    result.sort(key=lambda item: (-item['weight'], item['title'].casefold()))
    return result[:PEOPLE_CLOUD_LIMIT]



def reconcile_historical_profile_rows(rows):
    """Prepare legacy dancer rows for editorial review, never for public rendering.

    The August 2026 preservation CSV contains ghost/placeholder biographies.
    Historical 'Active' status is NOT publication approval. Retain source IDs
    and slugs, and separate uncertain affiliations from possible aliases.
    No identities are merged automatically.
    """
    def identity_key(name):
        return re.sub(r"[^a-z0-9]", "", str(name or "").casefold())

    prepared = []
    by_identity = {}
    for row in rows:
        source_id = str(row.get("id") or "").strip()
        name = str(row.get("dance_name") or "").strip()
        if not source_id or not name:
            continue
        candidate = {
            "source_id": source_id,
            "source_slug": str(row.get("profile_slug") or "").strip(),
            "display_name": name,
            "role_tags": str(row.get("role_tags") or "").strip(),
            "original_affiliation": str(row.get("team_affiliation") or "").strip(),
            "source_status": str(row.get("status") or "").strip(),
            "review_status": "identity_review_required",
            "publishable": False,
            "duplicate_source_ids": [],
        }
        prepared.append(candidate)
        by_identity.setdefault(identity_key(name), []).append(candidate)

    for group in by_identity.values():
        if len(group) > 1:
            for candidate in group:
                candidate["duplicate_source_ids"] = [
                    other["source_id"] for other in group
                    if other["source_id"] != candidate["source_id"]
                ]
                candidate["review_status"] = "possible_duplicate_review_required"
    return prepared
