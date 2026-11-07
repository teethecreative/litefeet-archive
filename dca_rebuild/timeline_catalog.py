"""Unified dated LiteFeet timeline.

Combines editorial research chapters, attributed historical milestones, archived
events, moves, people and music. Unknown dates stay undated; period anchors for
research chapters describe an era, not a claimed date of creation.
"""
from functools import lru_cache
import re

from dca_rebuild.archive_catalog import all_records, PAGE_SIZE, MAX_PAGE_SIZE
from dca_rebuild.archive_history_guide import load_history_guide

# Contextual anchor years place long-running topics alongside dated records.
# They are NOT invented event dates.
TOPIC_PERIODS = {
    "what-is-litefeet": ("2000–2026 / OVERVIEW", 2000),
    "harlem-shake": ("1980S ONWARD / HISTORICAL CONTEXT", 1981),
    "early-get-lite": ("1999–2006 / HISTORICAL CONTEXT", 1999),
    "people-crews": ("2000S ONWARD / HISTORICAL CONTEXT", 2004),
    "movement-vocabulary": ("2000S ONWARD / HISTORICAL CONTEXT", 2004),
    "music-history": ("2006–2015 / HISTORICAL CONTEXT", 2006),
    "battles-spaces": ("2000S ONWARD / HISTORICAL CONTEXT", 2005),
    "showtime": ("2011–2015 / HISTORICAL CONTEXT", 2011),
    "beyond-new-york": ("2013–2026 / HISTORICAL CONTEXT", 2013),
    "documentaries": ("2013–2026 / HISTORICAL CONTEXT", 2013),
    "open-questions": ("ONGOING RESEARCH / NOT DATED", 0),
}


def _sources(guide, refs):
    return [
        {"title": guide["sources"][key]["title"],
         "url": guide["sources"][key]["url"]}
        for key in refs
    ]


def _milestone_year(label):
    years = re.findall(r"(?:19|20)\d{2}", label)
    return int(years[0]) if years else 0


@lru_cache(maxsize=1)
def all_timeline_entries():
    guide = load_history_guide()
    entries = []
    for item in all_records():
        label = item.get("date_label") or "DATE UNDER REVIEW"
        year = int(item["date"][:4]) if item.get("date") else 0
        sources = item.get("research_sources") or []
        if not sources and str(item.get("source_url", "")).startswith("https://"):
            sources = [{"url": item["source_url"], "title": item["source_label"]}]
        entries.append(dict(
            slug=item["slug"], title=item["title"], collection=item["collection"],
            date=item.get("date") or "", date_label=label,
            period=label if item.get("date") else "DATE UNDER REVIEW",
            sort_year=year, sort_date=item.get("date") or "",
            href="/archive/records/" + item["slug"],
            summary=item.get("summary") or "",
            detail=[], sources=sources, kind="record",
            search=" ".join([item["title"], item.get("summary") or "",
                             item.get("collection") or ""]).casefold(),
        ))
    for index, milestone in enumerate(guide["timeline"]):
        year = _milestone_year(milestone["year"])
        sources = _sources(guide, milestone["sources"])
        text = milestone["detail"]
        entries.append(dict(
            slug="milestone-" + str(index), title=text,
            collection="history", date="", date_label=milestone["year"],
            period=milestone["year"], sort_year=year, sort_date=f"{year:04d}-01-01",
            href="", summary="", detail=[],
            sources=sources, kind="milestone",
            search=(" ".join([milestone["year"], text] + [s["title"] for s in sources])).casefold(),
        ))
    for chapter in guide["chapters"]:
        period, year = TOPIC_PERIODS[chapter["id"]]
        detail = []
        source_keys = []
        for paragraph in chapter["paragraphs"]:
            detail.append(dict(text=paragraph["text"],
                               sources=_sources(guide, paragraph["sources"])))
            source_keys.extend(paragraph["sources"])
        for title, description, keys in chapter["items"]:
            detail.append(dict(text=title + ": " + description,
                               sources=_sources(guide, keys)))
            source_keys.extend(keys)
        sources = _sources(guide, dict.fromkeys(source_keys))
        entries.append(dict(
            slug="topic-" + chapter["id"], title=chapter["title"],
            collection="history", date="", date_label=period, period=period,
            sort_year=year, sort_date=f"{year:04d}-01-01" if year else "",
            href="", summary=chapter["subtitle"], detail=detail,
            sources=sources, kind="chapter",
            search=(" ".join([chapter["title"], chapter["subtitle"], period] +
                             [item["text"] for item in detail])).casefold(),
        ))
    entries.sort(key=lambda x: (x["sort_year"], x["sort_date"], x["slug"]), reverse=True)
    if len({x["slug"] for x in entries}) != len(entries):
        raise ValueError("Duplicate timeline entries")
    return tuple(entries)


def timeline_browse(query="", collection="all", page=1, page_size=PAGE_SIZE):
    query = re.sub(r"\s+", " ", (query or "").strip()).casefold()[:120]
    page = max(1, min(int(page), 10000))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    available = {"all", "events", "history", "moves", "music", "people", "awards"}
    if collection not in available:
        collection = "all"
    tokens = query.split()
    records = [item for item in all_timeline_entries()
               if (collection == "all" or item["collection"] == collection)
               and all(token in item["search"] for token in tokens)]
    start = (page - 1) * page_size
    return dict(items=records[start:start + page_size], count=len(records),
                page=page, has_more=start + page_size < len(records),
                next_page=page + 1, query=query, collection=collection)


def timeline_payload(entry):
    """All fields are public, sourced, with no user submissions or admin notes."""
    return {key: entry[key] for key in (
        "slug", "title", "collection", "date", "date_label", "period",
        "href", "summary", "detail", "sources", "kind"
    )}
