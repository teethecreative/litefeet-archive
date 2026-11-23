"""Rolling seven-day activity for the public People & Teams word cloud.

Only dated public signals count. Nomination and battle history are NOT evidence
of current activity. Search hits store a matched profile URL and timestamp,
never a visitor identifier or the raw search phrase.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
import re

from flask import request, session
from sqlalchemy import Column, DateTime, Integer, String, func

from dca_rebuild.models import (
    Base, DCAEdition, DCANominee, DCANominationSubmission, LedgerPageView,
    VaultAddedBattle, VaultBattleOutcome,
)
from dca_rebuild.people_discovery import profile_rows, find_profiles, _normalized
from dca_rebuild.archive_catalog import all_records
from dca_rebuild.public_profiles import matchup_participants


class VaultPeopleSearchHit(Base):
    __tablename__ = "vault_people_search_hits"
    id = Column(Integer, primary_key=True)
    profile_href = Column(String(280), nullable=False, index=True)
    searched_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


def _match_search_profile(index, query):
    """Credit a searched identity, not a vague query that matched dozens."""
    q = _normalized(query)
    if len(q) < 3:
        return None
    rows = profile_rows(index)
    exact = [r for r in rows if q in {_normalized(r["name"]), *(
        _normalized(alias) for alias in r["aliases"]
    )}]
    if len(exact) == 1:
        return exact[0]["href"]
    if exact:
        return None
    result = find_profiles(index, query=query, page=1, page_size=500)
    if result["count"] == 1:
        return result["items"][0]["href"]
    return None


def record_people_search(index, query, session_factory, now=None):
    """Log only real-looking explicit searches, at most once per 2 minutes.

    No query text, IP, email, cookies or visitor ID is written to the table.
    Broad searches are never falsely attributed to every matching profile.
    """
    from dca_rebuild.traffic_classification import classify_traffic
    traffic, _ = classify_traffic(
        request.headers.get("User-Agent"),
        is_admin=bool(session.get("ledger_admin_authenticated")),
    )
    if traffic != "human":
        return
    path = _match_search_profile(index, query)
    if not path:
        return
    now = now or datetime.utcnow()
    last = session.get("vault_people_recent_search")
    if isinstance(last, dict) and last.get("href") == path:
        try:
            if (now - datetime.fromisoformat(last.get("at", ""))).total_seconds() < 120:
                return
        except (ValueError, TypeError):
            pass
    with session_factory.begin() as db:
        db.add(VaultPeopleSearchHit(profile_href=path, searched_at=now))
    session["vault_people_recent_search"] = {"href": path, "at": now.isoformat()}


def active_people_cloud(index, session_factory, *, now=None, limit=32):
    """Show only profiles with public activity inside the previous 168 hours.

    Nominations: dated 2026 DCA submissions for already-public nominee entries.
    Searches: recent, uniquely attributed directory searches (from this feature).
    Battles: confirmed 'happened' matchups at events dated within this window.
    Visits: likely-human profile page visits, deduplicated by visitor.
    Wall: newly approved public posts.
    Never infer a completed battle from an announced flyer alone.
    """
    from dca_rebuild.profile_wall import VaultProfileWallPost
    from dca_rebuild.battle_polls import matchups

    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=7)
    today = now.date()
    valid = {row["href"]: row for row in profile_rows(index)}
    counts = defaultdict(lambda: defaultdict(int))

    def credit(href, kind, n=1):
        if href in valid and n > 0:
            counts[href][kind] += n

    with session_factory() as db:
        # Privacy-preserving searches are logged only once a user actually
        # submits a search that uniquely identifies a public profile.
        for href, n in (db.query(
            VaultPeopleSearchHit.profile_href, func.count(VaultPeopleSearchHit.id)
        ).filter(
            VaultPeopleSearchHit.searched_at >= cutoff,
            VaultPeopleSearchHit.searched_at <= now,
        ).group_by(VaultPeopleSearchHit.profile_href).all()):
            credit(href, "search", n)

        # Public nominees only: never expose names that exist merely in
        # unpublished or rejected category intake.
        for name, n in (db.query(
            DCANominee.name, func.count(DCANominationSubmission.id)
        ).join(DCANominationSubmission, DCANominationSubmission.nominee_id == DCANominee.id)
         .join(DCAEdition, DCAEdition.id == DCANominationSubmission.edition_id)
         .filter(
            DCAEdition.year == 2026,
            DCANominee.moderation_status != "rejected",
            DCANominationSubmission.submitted_at >= cutoff,
            DCANominationSubmission.submitted_at <= now,
         ).group_by(DCANominee.name).all()):
            entry = index.by_name(name)
            if entry and any(
                item.get("program") == "Dancer's Choice Awards"
                and item.get("year") == 2026
                for item in entry.get("nominations", [])
            ):
                credit(entry["href"], "nomination", n)

        # Human browser visits to existing public profile URLs.
        for href, n in (db.query(
            LedgerPageView.path, func.count(func.distinct(LedgerPageView.visitor_id))
        ).filter(
            LedgerPageView.path.in_(tuple(valid)),
            LedgerPageView.traffic_type == "human",
            LedgerPageView.viewed_at >= cutoff,
            LedgerPageView.viewed_at <= now,
        ).group_by(LedgerPageView.path).all()):
            credit(href, "visit", n)

        # Moderated public community posts, not pending submissions.
        for href, n in (db.query(
            VaultProfileWallPost.profile_href, func.count(VaultProfileWallPost.id)
        ).filter(
            VaultProfileWallPost.status == "approved",
            VaultProfileWallPost.resolved_at >= cutoff,
            VaultProfileWallPost.resolved_at <= now,
        ).group_by(VaultProfileWallPost.profile_href).all()):
            credit(href, "wall", n)

        # The event must actually fall in the last seven days; recording
        # an old battle outcome today does not imply a recent performance.
        recent_events = {}
        for event in all_records():
            if event.get("collection") != "events" or event.get("record_type") != "event":
                continue
            if event.get("date_certainty") == "unconfirmed_year":
                continue
            try:
                event_date = date.fromisoformat(event.get("date") or "")
            except (TypeError, ValueError):
                continue
            if cutoff.date() <= event_date <= today:
                recent_events[event["slug"]] = event
        if recent_events:
            slugs = tuple(recent_events)
            outcomes = db.query(VaultBattleOutcome).filter(
                VaultBattleOutcome.event_slug.in_(slugs),
                VaultBattleOutcome.occurred == "happened",
            ).all()
            added = db.query(VaultAddedBattle).filter(
                VaultAddedBattle.event_slug.in_(slugs),
            ).all()
            by_event = defaultdict(list)
            for row in added:
                by_event[row.event_slug].append(row)
            confirmed = defaultdict(set)
            for outcome in outcomes:
                confirmed[outcome.event_slug].add(outcome.battle_key)
            for slug, event in recent_events.items():
                if not confirmed.get(slug):
                    continue
                for group in matchups(event, by_event.get(slug, [])):
                    for battle in group["items"]:
                        if battle["key"] not in confirmed[slug]:
                            continue
                        participants = matchup_participants(battle["label"])
                        unique = set()
                        for name in participants:
                            profile = index.by_name(name)
                            if profile:
                                unique.add(profile["href"])
                        for href in unique:
                            credit(href, "battle")

    # No historic fallback and no evergreen famous-name list.
    output = []
    for href, kinds in counts.items():
        if not any(kinds.values()):
            continue
        row = valid[href]
        weight = (
            2 * kinds["nomination"] + kinds["search"]
            + 4 * kinds["battle"] + min(7, kinds["visit"])
            + 2 * kinds["wall"]
        )
        labels = []
        for kind, label in (
            ("nomination", "recent nominations"),
            ("search", "recent searches"),
            ("battle", "confirmed recent battles"),
            ("visit", "profile visits"),
            ("wall", "approved Wall posts"),
        ):
            if kinds[kind]:
                labels.append(label)
        output.append({
            "title": row["title"],
            "full_name": row["title"],
            "href": href,
            "weight": min(8, max(1, 1 + weight // 3)),
            "activity_weight": weight,
            "reasons": ", ".join(labels),
        })
    output.sort(key=lambda item: (-item["activity_weight"], _normalized(item["title"])))
    return output[:limit]
