"""Source-linked public cultural history guide.

These static research paragraphs attribute their evidence to original sources.
No backend editorial notes, contributor PII or unreviewed nominations are read.
"""
from functools import lru_cache
from pathlib import Path
import json


@lru_cache(maxsize=1)
def load_history_guide():
    path = Path(__file__).parent / "data" / "archive_history_guide.json"
    with path.open(encoding="utf-8") as file:
        guide = json.load(file)
    sources = guide["sources"]
    if not guide["chapters"] or not sources:
        raise ValueError("History guide must include chapters and sources")
    ids = [chapter["id"] for chapter in guide["chapters"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate historical chapter anchor")
    for chapter in guide["chapters"]:
        for entry in chapter["paragraphs"]:
            if not entry["sources"] or any(key not in sources for key in entry["sources"]):
                raise ValueError("Unattributed history paragraph")
        for title, detail, refs in chapter["items"]:
            if not refs or any(key not in sources for key in refs):
                raise ValueError("Unattributed reference item")
    for event in guide["timeline"]:
        if not event["sources"] or any(key not in sources for key in event["sources"]):
            raise ValueError("Unattributed timeline entry")
    for source in sources.values():
        if not source["url"].startswith("https://"):
            raise ValueError("Non-secure historical source")
    return guide
