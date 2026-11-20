"""Review-only adapter for inspected legacy relational source exports.

This module NEVER connects to a live database. Export rows must be obtained
separately through an approved, read-only process and kept outside version control.
No row is approved, published, linked to another identity, or inferred as a winner.
"""
from collections import Counter

# Every field not listed here is intentionally excluded from archive staging.
# In particular: email, private notes, user IDs, contact details, real names,
# ownership/claim metadata, and credentials must never be copied.
SAFE_FIELDS = {
    "dancer_profiles": (
        "dance_name", "profile_slug", "borough_scene", "era", "status",
        "source_url", "role_tags", "style_notes", "signature_moves",
        "battle_history",
    ),
    "team_records": (
        "team_name", "aka_names", "borough_scene", "era", "status",
        "review_status", "known_for", "source_url",
    ),
    "battle_records": (
        "event_name", "event_date", "battle_type", "competitor_one",
        "competitor_two", "competitor_one_team", "competitor_two_team",
        "winner", "official_winner", "judges_text", "result_text",
        "source_url", "review_status", "community_input_status",
    ),
    "vault_gathering_submissions": (
        "title", "gathering_type", "start_date", "end_date",
        "start_time", "end_time", "timezone", "venue", "city",
        "virtual", "link", "hosts", "status",
    ),
    "music_project_tracks": (
        "title", "track_title", "track_number", "music_project_id",
        "url", "platform",
    ),
    "media_items": (
        "media_type", "title", "event_name", "url", "platform",
        "release_date", "review_status", "status",
    ),
    "music_projects": (
        "title", "project_type", "release_date", "status", "review_status",
    ),
}
KINDS = {
    "dancer_profiles": "person",
    "team_records": "team",
    "battle_records": "battle",
    "vault_gathering_submissions": "event",
    "music_project_tracks": "track",
}
TITLE_FIELDS = {
    "dancer_profiles": ("dance_name",),
    "team_records": ("team_name",),
    "battle_records": ("event_name", "battle_type"),
    "vault_gathering_submissions": ("title",),
    "music_project_tracks": ("track_title", "title"),
    "media_items": ("title",),
}
FOOTAGE_TYPES = {"video", "footage", "battle_video", "battle_footage"}


def _safe_value(value):
    """Retain source text and numeric/date-like values without nested objects."""
    if value is None:
        return None
    if type(value) is str:
        return value.strip() or None
    if type(value) in (int, float, bool):
        return value
    return None


def prepare_legacy_records(export):
    """Return (private staging records, per-locator exclusions).

    Expected input: a JSON object keyed by the exact table names in SAFE_FIELDS;
    values are arrays of read-only exported row objects with positive integer IDs.
    Exclusions are visible to reviewers so no source class quietly disappears.
    This is a complete snapshot; do not treat it as a delta.
    """
    if not isinstance(export, dict) or set(export) - set(SAFE_FIELDS):
        raise ValueError("Legacy export requires a table-name object with only known source tables")
    records, excluded = [], []
    for table, rows in sorted(export.items()):
        if not isinstance(rows, list):
            raise ValueError(f"{table} must be an array")
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] < 1:
                raise ValueError(f"{table} requires positive integer source IDs")
            record_id = row["id"]
            if record_id in seen:
                raise ValueError(f"Duplicate source ID in {table}: {record_id}")
            seen.add(record_id)
            locator = {"table": table, "id": record_id}
            if table == "music_projects":
                excluded.append(dict(locator, reason="Music projects/releases need a dedicated release kind; never relabel an album as a track"))
                continue
            if table == "media_items" and str(row.get("media_type", "")).strip().casefold() not in FOOTAGE_TYPES:
                excluded.append(dict(locator, reason="Media type is not confirmed footage; do not guess a track or a battle"))
                continue
            title = next((v for field in TITLE_FIELDS[table]
                          if isinstance(v := _safe_value(row.get(field)), str)), None)
            if not title:
                excluded.append(dict(locator, reason="Missing source title; editorial review required"))
                continue
            payload = {"source_table": table, "source_id": record_id}
            for field in SAFE_FIELDS[table]:
                value = _safe_value(row.get(field))
                if value is not None:
                    # Bare textual alias lists are *not* verified aliases.
                    payload["alias_source_text" if field == "aka_names" else field] = value
            # Preserve direct recorded dates without claiming they are verified.
            if table == "vault_gathering_submissions" and payload.get("start_date"):
                payload["event_date"] = payload["start_date"]
            # Raw competitor and winner strings remain unverified source claims
            # in immutable revisions; no graph result or person link is added.
            records.append({
                "system": f"legacy_sql:{table}",
                "key": str(record_id),
                "title": title,
                "kind": "footage" if table == "media_items" else KINDS[table],
                "visibility": "private_review",
                "payload": payload,
            })
    return records, excluded


def inventory_summary(records, excluded):
    return {
        "staged": len(records),
        "staged_by_source": dict(sorted(Counter(r["system"] for r in records).items())),
        "excluded": len(excluded),
        "excluded_by_source": dict(sorted(Counter(e["table"] for e in excluded).items())),
    }
