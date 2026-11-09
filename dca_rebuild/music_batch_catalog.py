"""Read-only, additive November 9 music batch. Original CSVs are preserved intact.

These entries are published as sourced community submissions, with gaps in
release date, individual-track URLs, and credits explicitly retained. They
are not inserted into, or used to rewrite, the production media_items table.
"""
import csv
import re
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).parent / "data"


def _read(name):
    with (_DATA / name).open(encoding="utf-8-sig", newline="") as file:
        return tuple(dict(row) for row in csv.DictReader(file))


def _key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


@lru_cache(maxsize=1)
def batch_catalog():
    projects = _read("music_batch1_projects.csv")
    tracks = _read("music_batch1_tracks.csv")
    project_by_title = {_key(p["title"]): p for p in projects}
    items = []
    seen_ids = set()
    for row in tracks:
        entry_id = row["id"]
        if entry_id in seen_ids:
            raise ValueError("Repeated batch track ID: " + entry_id)
        seen_ids.add(entry_id)
        project = project_by_title.get(_key(row.get("project_title")))
        date = row.get("release_date") or ""
        # Keep year-only dates as year only, not fabricated January 1 dates.
        year = (project or {}).get("release_year") or ""
        items.append(dict(
            catalog_id=entry_id, kind="track", title=row["title"],
            artist_or_creator=row.get("artist_credit") or row.get("source_profile") or "",
            producer_credit=row.get("producer_credit") or "",
            release_date=date, release_year=date[:4] or (year if project else ""),
            duration=row.get("duration") or "",
            description="",
            project_title=row.get("project_title") or "",
            project_id=(project or {}).get("id") or "",
            track_number=row.get("track_number") or "",
            platform=row.get("platform") or "",
            url=row.get("source_url") or "", source_profile_url=row.get("source_profile_url") or "",
            # Never label a profile or album link as a direct playable track.
            playable_url=row.get("audio_url") or "",
            date_verification=row.get("date_verification") or "Unverified",
            metadata_notes=row.get("metadata_notes") or "",
            needs_exact_track_url=row.get("needs_exact_track_url") == "True",
            source_screenshot="November 9, 2026 upload",
        ))
    for row in projects:
        entry_id = row["id"]
        if entry_id in seen_ids:
            raise ValueError("Repeated catalog ID: " + entry_id)
        seen_ids.add(entry_id)
        items.append(dict(
            catalog_id=entry_id, kind="project", title=row["title"],
            artist_or_creator=row.get("artist") or "",
            producer_credit="", release_date=row.get("release_date") or "",
            release_year=row.get("release_year") or "", duration="",
            description="", project_title="", project_id="",
            record_type=row.get("record_type") or "Project",
            expected_track_count=row.get("expected_track_count") or "",
            platform=row.get("platform") or "",
            url=row.get("source_url") or "", source_profile_url=row.get("source_profile_url") or "",
            playable_url=row.get("playback_url") or "",
            date_verification=row.get("date_verification") or "Unverified",
            metadata_notes=row.get("notes") or "",
            source_screenshot=row.get("source_screenshot") or "",
        ))
    return tuple(items)


def yaffi_catalog():
    """Sourced 2026 Yaffi Tune releases; separate from the immutable upload batch."""
    rows = _read("music_yaffi_2026.csv")
    records = []
    for row in rows:
        kind = row["kind"]
        records.append(dict(
            catalog_id=row["id"], kind=kind,
            title=row["title"], artist_or_creator=row["artist"],
            producer_credit="", release_date=row["release_date"],
            release_year=row["release_date"][:4], duration=row["duration"],
            description="", project_title=row["project_title"],
            project_id=row["project_id"], track_number=row["track_number"].strip(),
            record_type="Project" if kind == "project" else "Track",
            platform=row["platform"], url=row["source_url"],
            source_profile_url="", playable_url="",
            date_verification=row["date_verification"],
            metadata_notes=row["metadata_notes"],
            needs_exact_track_url=row["needs_exact_track_url"] == "True",
            source_screenshot="Research verified November 9, 2026",
        ))
    return tuple(records)


def all_music_catalog():
    return batch_catalog() + yaffi_catalog()


def batch_record(kind, catalog_id):
    return next((row for row in all_music_catalog()
                 if row["kind"] == kind and row["catalog_id"] == catalog_id), None)


def combined_releases(existing, format_date, format_duration):
    """Preserve existing rows; append only unmatched catalog source entries."""
    output = []
    existing_keys = set()
    for row in existing:
        row = dict(row)
        artist = row.get("artist_or_creator") or row.get("artist") or row.get("producer_name") or ""
        existing_keys.add((_key(row.get("title")), _key(artist)))
        row["date_label"] = format_date(row.get("release_date"))
        row["duration_label"] = format_duration(row)
        row["record_href"] = "/litefeet-music/release/" + str(row["id"])
        row["row_type"] = "Existing"
        output.append(row)
    for record in all_music_catalog():
        artist = record.get("artist_or_creator") or ""
        if (_key(record["title"]), _key(artist)) in existing_keys:
            continue
        row = dict(record)
        # Only build canonical labels from date precision supplied in source.
        row["date_label"] = (format_date(row.get("release_date"))
                             if row.get("release_date") else
                             row.get("release_year") or "Date unknown")
        row["duration_label"] = format_duration(row)
        row["record_href"] = ("/litefeet-music/catalog/" + row["kind"] + "/" + row["catalog_id"])
        row["row_type"] = row.get("record_type") if row["kind"] == "project" else "Track"
        output.append(row)
    output.sort(key=lambda r: (r.get("release_date") or "", r.get("release_year") or ""),
                reverse=True)
    return output
