"""Editorial staging for recovered LiteFeet identities.

Historical exports may mention real community participants without confirming
that a public biography, affiliation, or identity link has been approved.
Nothing in this module feeds the public archive without editorial review.
"""
from functools import lru_cache
from pathlib import Path
import json

STAGING_PATH = Path(__file__).parent / "data" / "recovery_profiles_staging.json"
PENDING = "pending_identity_review"


@lru_cache(maxsize=1)
def staged_profiles():
    data = json.loads(STAGING_PATH.read_text(encoding="utf-8"))
    profiles = data["profiles"]
    if data["publication_policy"] != "staging_only_no_auto_publish":
        raise ValueError("Unrecognized historical-profile publication policy")
    if len(profiles) != data["record_count"] or len(profiles) != 138:
        raise ValueError("Historical archive row count changed unexpectedly")
    ids = [p["legacy_id"] for p in profiles]
    if len(ids) != len(set(ids)):
        raise ValueError("Historical archive IDs must be retained uniquely")
    for p in profiles:
        if p["review_status"] != PENDING:
            raise ValueError("Staging data must remain pending identity review")
        if not p["display_name"].strip() or not p["legacy_slug"].strip():
            raise ValueError("Recovered identity is missing required source data")
        if set(p) != {"legacy_id", "display_name", "legacy_slug",
                      "review_status", "normalized_duplicate_ids"}:
            raise ValueError("Staging identity contains an unauthorized field")
        if p["legacy_id"] in p["normalized_duplicate_ids"]:
            raise ValueError("Identity cannot duplicate itself")
        if not set(p["normalized_duplicate_ids"]).issubset(set(ids)):
            raise ValueError("Duplicate candidate points outside staging set")
    return tuple(profiles)


def identity_review_queue():
    """Return editable review candidates, never public profile records."""
    return tuple(dict(p) for p in staged_profiles())
