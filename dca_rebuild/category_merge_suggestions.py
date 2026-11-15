"""Conservative editorial suggestions for merging similar award categories.

All candidates come from the Vault's existing category records. Suggestions
do not approve, reject, merge, publish, or change votes.
"""
from difflib import SequenceMatcher
import re

_AWARD_FILLER = frozenset({
    "a", "an", "and", "at", "by", "for", "from", "in", "of", "on",
    "or", "the", "to", "with", "year", "years", "award", "awards",
    "best", "most", "top", "litefeet", "dca", "2023", "2026",
})
_TERM_ALIASES = {
    "battlers": "battler", "battles": "battle",
    "dancers": "dancer", "dancing": "dancer",
    "hosts": "host", "hosting": "host",
    "judges": "judge", "judging": "judge",
    "producers": "producer", "producing": "producer",
    "production": "producer",
    "supporters": "support", "supporter": "support",
    "supporting": "support", "supported": "support",
    "involved": "support", "involvement": "support",
    "consistency": "consistent",
}
_DESCRIPTION_FILLER = _AWARD_FILLER | frozenset({
    "recognizes", "recognize", "person", "individual", "someone",
    "strong", "outstanding", "demonstrates", "community",
})


def _terms(value, filler=_AWARD_FILLER):
    return frozenset(
        _TERM_ALIASES.get(word, word)
        for word in re.findall(r"[a-z0-9]+", (value or "").casefold())
        if word not in filler
    )


def _merge_match(left, right):
    """Return score/reason for a plausible duplicate, or None."""
    first, second = _terms(left["name"]), _terms(right["name"])
    if not first or not second:
        return None
    common = first & second
    if not common:
        return None
    if first == second:
        return 100, "Same award terms, despite wording differences"
    similarity = SequenceMatcher(
        None, " ".join(sorted(first)), " ".join(sorted(second))
    ).ratio()
    if len(common) >= 2 and len(common) / min(len(first), len(second)) >= .67:
        return 91, "Multiple distinctive award terms overlap"
    if similarity >= .82:
        return 86, "Very similar category names"

    # Different disciplines may warrant separate awards. Flag for human review.
    if ("consistent" in common
            and {"battler", "dancer"} <= (first | second)):
        return 72, "Related consistency awards; check whether disciplines should combine"

    left_desc = _terms(left.get("description"), _DESCRIPTION_FILLER)
    right_desc = _terms(right.get("description"), _DESCRIPTION_FILLER)
    description_common = left_desc & right_desc
    if (len(description_common) >= 3
            and len(description_common) / min(
                max(len(left_desc), 1), max(len(right_desc), 1)
            ) >= .55):
        return 78, "Category names and descriptions describe similar work"
    return None


def suggest_merge_targets(row, all_rows, limit=3):
    """Suggest only targets supported by the existing merge endpoint."""
    if row["status"] in ("merged", "rejected"):
        return []
    suggestions = []
    for candidate in all_rows:
        if (candidate["key"] == row["key"]
                or candidate["status"] in ("merged", "rejected")
                or (row["source"] == "new" and candidate["source"] != "new")):
            continue
        match = _merge_match(row, candidate)
        if match is not None:
            score, reason = match
            suggestions.append(dict(
                key=candidate["key"], name=candidate["name"],
                status=candidate["status"], reason=reason, score=score,
            ))
    suggestions.sort(key=lambda item: (
        -item["score"], item["status"] != "approved", item["name"].casefold()
    ))
    return suggestions[:limit]
