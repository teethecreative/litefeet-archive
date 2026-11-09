"""Resolve old dancer-profile URLs to existing, public historical records.

The preserved 2026 identity export supplies only names and old slugs. Resolve
the names against the *published* archive catalog; never publish unpublished
source rows, assume affiliations, or generate new biographies while redirecting.
"""
import re
from functools import lru_cache

from dca_rebuild.archive_catalog import all_records
from dca_rebuild.archive_recovery import recovery_candidates


def _identity_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


@lru_cache(maxsize=1)
def preserved_profile_redirects():
    """Map a source legacy slug only to one unambiguous public people record."""
    known = {}
    for record in all_records():
        if record["collection"] != "people":
            continue
        for name in record["title"].split("/"):
            key = _identity_key(name)
            if key:
                known.setdefault(key, []).append(record)

    redirects = {}
    for source in recovery_candidates():
        slug = str(source.get("legacy_slug") or "").strip().casefold()
        matches = known.get(_identity_key(source.get("name")), ())
        if slug and re.fullmatch(r"[a-z0-9-]+", slug) and len(matches) == 1:
            redirects[slug] = "/archive/records/" + matches[0]["slug"]
    return redirects


def legacy_dancer_destination(path):
    """Return a 301 target for an exact saved dancer URL, otherwise None."""
    match = re.fullmatch(r"/(?:people/dancers|dancers)/([a-z0-9-]+)", path.casefold())
    if not match:
        return None
    return preserved_profile_redirects().get(match.group(1))
