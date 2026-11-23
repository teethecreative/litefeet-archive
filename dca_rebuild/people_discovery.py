"""Searchable People & Teams directory for published and nomination-linked profiles.

Only the shared public profile index is used: awards nominations may create
starter pages, but event lineups alone cannot create unverified identities.
"""
import re
import unicodedata

from dca_rebuild.archive_catalog import PAGE_SIZE, MAX_PAGE_SIZE


def _normalized(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(value.casefold().split())


def profile_rows(index):
    """One record per public profile URL, never one row per nomination."""
    result, seen = [], set()
    for entry in index._profiles.values():
        href = entry.get("href") or ""
        name = entry.get("name") or ""
        if not href.startswith(("/people/", "/archive/records/")) or not name or href in seen:
            continue
        seen.add(href)
        archived = entry.get("archive_record") or {}
        nominations = entry.get("nominations") or []
        wins = entry.get("wins") or []
        current = sum(1 for item in nominations if item.get("year") == 2026)
        label = "Team / crew" if entry.get("is_team") else "Person"
        facts = []
        if wins:
            facts.append("Documented award win" + ("s" if len(wins) != 1 else ""))
        if nominations:
            facts.append("Award nomination" + ("s" if len(nominations) != 1 else ""))
        if archived:
            facts.append("Archive-linked profile")
        if not facts:
            facts.append("Archive-listed name; details may be unverified")
        aliases = str(archived.get("title") or "").split("/")
        result.append({
            "title": name,
            "name": name,
            "href": href,
            "summary": " · ".join(facts),
            "label": label,
            "aliases": [a.strip() for a in aliases if a.strip()],
            "is_team": bool(entry.get("is_team")),
            "nomination_count": len(nominations),
            "current_nomination_count": current,
            "archive_slug": archived.get("slug") or "",
        })
    return sorted(result, key=lambda row: (_normalized(row["name"]), row["href"]))


def find_profiles(index, query="", page=1, page_size=PAGE_SIZE):
    """Exact-name-first, case-insensitive token search over ALL public profiles."""
    query = _normalized(query)[:120]
    tokens = query.split()
    try:
        page = max(1, min(int(page), 10000))
    except (ValueError, TypeError):
        page = 1
    page_size = max(1, min(int(page_size), 500))
    matches = []
    for row in profile_rows(index):
        archived = index.by_name(row["name"])
        # The actual row and archived alias text are trusted public data;
        # award categories are not names and should not create matches.
        haystack = _normalized(" ".join([row["name"], *row["aliases"], row["label"]]))
        if all(token in haystack for token in tokens):
            matches.append(row)
    if query:
        matches.sort(key=lambda row: (
            0 if _normalized(row["name"]) == query else
            1 if _normalized(row["name"]).startswith(query) else 2,
            _normalized(row["name"]), row["href"],
        ))
    start = (page - 1) * page_size
    return {
        "items": matches[start:start + page_size],
        "count": len(matches),
        "page": page,
        "has_more": start + page_size < len(matches),
        "next_page": page + 1 if start + page_size < len(matches) else None,
        "query": query,
        "collection": "people",
    }


def nominee_people_cloud(index, archive_cloud=None, limit=32):
    """Balance recent nominees with longstanding archive-linked names.

    This is a discovery cloud, not an award ranking or verified historical
    outcome; weights are editorial display prominence only.
    """
    rows = profile_rows(index)
    archive_cloud = archive_cloud or []
    by_slug = {item["archive_slug"]: item for item in rows if item["archive_slug"]}
    archive_mentions = {}
    archive_priority = []
    for old in archive_cloud:
        row = by_slug.get(old.get("slug"))
        if row and row["href"] not in archive_mentions:
            archive_mentions[row["href"]] = max(0, int(old.get("mentions") or 0))
            archive_priority.append(row)
    latest = sorted((row for row in rows if row["current_nomination_count"] > 0),
                    key=lambda row: (-row["current_nomination_count"],
                                     _normalized(row["name"]), row["href"]))
    others = sorted((row for row in rows if row["nomination_count"] > 0),
                    key=lambda row: (-row["nomination_count"],
                                     _normalized(row["name"]), row["href"]))
    selected, seen = [], set()
    def add(row):
        if row["href"] not in seen and len(selected) < limit:
            seen.add(row["href"])
            selected.append(row)

    # Recent publicly listed nominees should stay visible even when the
    # older archive names have many document mentions.
    for row in latest[:min(20, limit)]:
        add(row)
    for row in archive_priority:
        add(row)
    for row in latest:
        add(row)
    for row in others:
        add(row)
    for row in rows:
        add(row)
    result = [{
        "title": row["title"],
        "full_name": row["title"],
        "href": row["href"],
        "mentions": archive_mentions.get(row["href"], 0),
        "weight": min(8, 1 + archive_mentions.get(row["href"], 0)
                      + 2 * row["current_nomination_count"]),
        "is_nominee": row["nomination_count"] > 0,
    } for row in selected]
    result.sort(key=lambda row: (-row["weight"], _normalized(row["title"])))
    return result
