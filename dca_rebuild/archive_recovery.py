"""Staged historical People & Crews identity review — never a public import.

The 2026 preservation source contains auto-generated ghost biographies and
unverified affiliations. This module deliberately reads only sanitized names,
original IDs, legacy slugs and source-reported roles for editorial comparison.
Nothing here is added to the public archive catalog or the word cloud.
"""
from collections import Counter
from functools import lru_cache
from pathlib import Path
import json
import re

REVIEW_PATH = Path(__file__).parent / "data" / "archive_recovery_review.json"


def identity_key(value):
    """Normalize spelling/punctuation for *review hints*, never for ID merges."""
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


@lru_cache(maxsize=1)
def recovery_candidates():
    data = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    if data.get("review_status") != "pending_manual_identity_review":
        raise ValueError("Unexpected legacy recovery review status")
    entries = data["candidates"]
    ids = [entry["source_id"] for entry in entries]
    slugs = [entry["legacy_slug"] for entry in entries]
    if len(ids) != len(set(ids)) or len(slugs) != len(set(slugs)):
        raise ValueError("Historical IDs and slugs must remain unique")
    for entry in entries:
        if set(entry) != {"source_id", "name", "legacy_slug", "reported_roles"}:
            raise ValueError("Only non-sensitive identity fields may be staged")
        if not entry["name"] or not entry["legacy_slug"]:
            raise ValueError("Incomplete recovered identity")
    return tuple(entries)


def recovery_review(public_records):
    """Return advisory review flags without approving, merging or publishing."""
    staged = recovery_candidates()
    counts = Counter(identity_key(item["name"]) for item in staged)
    profiles = [r for r in public_records if r["collection"] == "people"]
    reviewed = []
    for candidate in staged:
        key = identity_key(candidate["name"])
        possible_matches = []
        for profile in profiles:
            names = [profile["title"]] + profile["title"].split("/")
            other_keys = [identity_key(name) for name in names]
            if any(key == other or (
                    len(key) >= 6 and len(other) >= 6
                    and (key in other or other in key))
                   for other in other_keys if other):
                possible_matches.append({
                    "slug": profile["slug"], "name": profile["title"]
                })
        reviewed.append({
            **candidate,
            "duplicate_name_count": counts[key],
            "possible_public_matches": possible_matches,
            "review_status": "Identity review required",
        })
    return sorted(reviewed, key=lambda r: (r["name"].casefold(), r["source_id"]))
