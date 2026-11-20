"""Read-only historical identity reconciliation hints; never automatic merges.

Reviews reconcile source locators, not mutable display names. The report is
intentionally aggregate by default so recovered identities stay private.
"""
from collections import Counter, defaultdict
import re

from dca_rebuild.archive_foundation import source_records
from dca_rebuild.archive_recovery import identity_key

PERSON_KINDS = frozenset({"person", "person_candidate", "legacy_identity", "dancer_profile"})


def _record_ref(item):
    return {"system": item["system"], "key": item["key"], "title": item["title"]}


def _labels(item):
    """Only source-recorded labels, not narrative free-text affiliations."""
    names = [item["title"]]
    aliases = item["payload"].get("aliases", [])
    if not isinstance(aliases, list):
        raise ValueError("Recorded aliases must be a list")
    names.extend(alias for alias in aliases if isinstance(alias, str))
    # An explicitly delimited public title may contain multiple names.
    # Tokens remain search hints, never asserted aliases or identities.
    if item["system"] == "editorial_catalog" and "/" in item["title"]:
        names.extend(piece.strip() for piece in item["title"].split("/"))
    return sorted({name.strip() for name in names if name and name.strip()})


def reconcile_identity_sources(records=None, include_candidates=False):
    """Group exact normalized-name collision hints, with privacy-safe summaries.

    Does not infer or apply merges, public identities, roles, source claims,
    aliases, redirects, or graph edges. Every full group requires human review.
    """
    records = list(source_records() if records is None else records)
    seen_locators = set()
    indexed = defaultdict(list)
    by_system = Counter()
    missing_title = 0
    for item in records:
        locator = (item["system"], item["key"])
        if locator in seen_locators:
            raise ValueError("Duplicate historical source locator")
        seen_locators.add(locator)
        by_system[item["system"]] += 1
        if item["kind"] not in PERSON_KINDS:
            continue
        if not item["title"].strip():
            missing_title += 1
            continue
        for key in {identity_key(label) for label in _labels(item)}:
            if key:
                indexed[key].append(item)
    groups = []
    for key, group in sorted(indexed.items()):
        unique = {(item["system"], item["key"]): item for item in group}
        # A single person with multiple matching aliases is not a collision.
        if len(unique) < 2:
            continue
        ordered = [unique[locator] for locator in sorted(unique)]
        groups.append({
            "key": key, "sources": len(ordered),
            "systems": sorted({item["system"] for item in ordered}),
            "requires_review": True,
            # Raw names are intentionally absent unless an editor explicitly asks
            # to inspect this output inside a private, access-controlled process.
            **({"candidates": [_record_ref(item) for item in ordered]} if include_candidates else {}),
        })
    return {
        "source_rows": len(records),
        "systems": dict(sorted(by_system.items())),
        "person_source_rows": sum(item["kind"] in PERSON_KINDS for item in records),
        "missing_person_labels": missing_title,
        "collision_groups": len(groups),
        "collision_keys": sum(item["sources"] for item in groups),
        "groups": groups,
        "disclaimer": "Matching strings are review suggestions only; identities remain separate.",
    }


def reconcile_legacy_profile_counts(rows):
    """Aggregate counts only from a separately authorized, private source export.

    Does not return or print individual names, IDs, slugs, contacts or profiles.
    """
    names = Counter()
    slugs = Counter()
    blank_names = blank_slugs = 0
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("Each source row must be a record")
        name = item.get("dance_name")
        slug = item.get("profile_slug")
        n = identity_key(name) if isinstance(name, str) else ""
        s = re.sub(r"[^a-z0-9]", "", slug.casefold()) if isinstance(slug, str) else ""
        if n:
            names[n] += 1
        else:
            blank_names += 1
        if s:
            slugs[s] += 1
        else:
            blank_slugs += 1
    return {
        "rows": len(rows),
        "distinct_normalized_names": len(names),
        "duplicate_name_groups": sum(v > 1 for v in names.values()),
        "duplicate_name_rows": sum(v for v in names.values() if v > 1),
        "distinct_normalized_slugs": len(slugs),
        "duplicate_slug_groups": sum(v > 1 for v in slugs.values()),
        "missing_names": blank_names,
        "missing_slugs": blank_slugs,
        "requires_human_identity_review": True,
    }
