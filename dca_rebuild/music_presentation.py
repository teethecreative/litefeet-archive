"""Non-destructive presentation and review helpers for Release Radar.

Never modify media_items or source CSVs. A source title can contain pasted
platform description text; separate it for presentation while retaining the
original title in the record and database.
"""
import re
from collections import defaultdict
from urllib.parse import urlsplit


# Conservatively chosen fragments observed in real source-title imports.
# Keep this narrow; generic punctuation and hashtags may be real song titles.
_PASTED_NOTE_STARTS = (
    "legendary lite feet producer & dancer",
    "listen to jellyfish jam by ",
    "#revival coming this year",
    "imported from youtube.",
)


def release_display_fields(item):
    """Return cleaned *display* fields without changing the input or stored title."""
    raw_title = str(item.get("title") or "").strip()
    title = " ".join(raw_title.split())
    original_description = str(item.get("description") or "").strip()
    extracted_note = ""
    lower = title.casefold()

    for marker in _PASTED_NOTE_STARTS:
        index = lower.find(marker)
        if index > 0:
            # A conservative cutoff only for positively identified pasted
            # note signatures, not a generalized title-rewriting heuristic.
            extracted_note = title[index:].strip()
            title = title[:index].rstrip(" \t—-:.,").strip()
            break

    if not title:
        title = raw_title
        extracted_note = ""

    # If the original description already contains the note, don't repeat it.
    if extracted_note and extracted_note.casefold() not in original_description.casefold():
        description = (original_description + " " + extracted_note).strip()
    else:
        description = original_description

    return {
        "display_title": title or "Untitled release",
        "display_description": description,
        "title_has_pasted_notes": bool(extracted_note),
    }


def _safe_external_url(value):
    """Return only absolute HTTP(S) destinations from stored metadata."""
    text = str(value or "").strip()
    parts = urlsplit(text)
    if parts.scheme.casefold() not in ("http", "https") or not parts.hostname:
        return ""
    return text


def _same_destination(left, right):
    """Treat tracking-query variants of one profile URL as the same page."""
    a, b = urlsplit(left), urlsplit(right)
    return (a.hostname.casefold(), a.path.rstrip("/").casefold()) == (
        b.hostname.casefold(), b.path.rstrip("/").casefold())


def release_destinations(item):
    """Distinguish a real source from a stored artist-profile landing page."""
    source = _safe_external_url(item.get("url") or item.get("source_url"))
    artist = _safe_external_url(item.get("source_profile_url")
                                or item.get("artist_profile_url")
                                or item.get("profile_url"))
    if source and artist and _same_destination(source, artist):
        source = ""
    return {"source_destination": source, "artist_profile_destination": artist}


def with_release_display(item):
    """Copy the record, add presentation/choice fields, and preserve raw metadata."""
    output = dict(item)
    output.update(release_display_fields(output))
    output.update(release_destinations(output))
    return output


def _key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def duplicate_release_candidates(records):
    """Flag exact source-and-metadata repeats for human review only.

    A matching title alone is not enough: alternative versions, reposts,
    projects, and tracks can legitimately have the same title. Tracking query
    parameters are not distinct recording sources. This function never hides
    releases, merges IDs, or mutates the database.
    """
    groups = defaultdict(list)
    for item in records:
        source = item.get("url") or ""
        parts = urlsplit(source)
        if not parts.hostname or not parts.path.strip("/"):
            continue
        title = release_display_fields(item)["display_title"]
        artist = (item.get("artist_or_creator") or item.get("artist")
                  or item.get("producer_name") or "")
        date = str(item.get("release_date") or "")
        key = (_key(title), _key(artist),
               parts.hostname.casefold().removeprefix("www."),
               parts.path.rstrip("/").casefold(), date)
        if not key[0] or not key[1]:
            continue
        groups[key].append(item)
    return [
        {
            "title": release_display_fields(group[0])["display_title"],
            "artist": (group[0].get("artist_or_creator") or group[0].get("artist")
                       or group[0].get("producer_name") or ""),
            "release_date": group[0].get("release_date") or "",
            "source_url": group[0].get("url") or "",
            "record_ids": [r.get("id") or r.get("catalog_id") for r in group],
        }
        for group in groups.values() if len(group) > 1
    ]
