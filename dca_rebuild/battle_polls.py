"""Permanent community opinion polls for source-confirmed two-sided LiteFeet battles.

The advertised historical lineup remains immutable. Administrators can attach a
sourced occurrence/result to each advertised matchup; only confirmed ties and
YouTube Decides offer a vote. Polls have no end date, and votes never change
the historical outcome.
"""
from datetime import datetime
import hashlib
import re
import secrets

from flask import abort, flash, redirect, request, session, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from dca_rebuild.archive_catalog import find_record
from dca_rebuild.email_verification import verified_nominator_hash
from dca_rebuild.models import VaultBattleOutcome, VaultBattleOutcomeHistory, VaultBattleVote

OCCURRENCE = {"unconfirmed", "scheduled", "happened", "did_not_happen", "postponed"}
RESULTS = {"unknown", "a", "b", "tie", "youtube_decide", "no_contest"}
POLL_RESULTS = {"tie", "youtube_decide"}
RESULT_LABELS = {
    "unknown": "Result unconfirmed",
    "tie": "Official tie",
    "youtube_decide": "YouTube Decide",
    "no_contest": "No contest",
}


def matchups(record):
    """Derive stable matchup keys without mistaking promotional names for results."""
    if not record or record.get("record_type") != "event":
        return []
    groups = []
    for group_index, group in enumerate(record.get("battles") or []):
        items = []
        for item_index, text in enumerate(group.get("items") or []):
            label = str(text)
            fingerprint = f'{record["slug"]}\0{group_index}\0{item_index}\0{label}'
            key = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
            parts = [p.strip() for p in re.split(r"\s+vs\.?\s+", label, flags=re.I)]
            contestants = parts if len(parts) == 2 and all(parts) else []
            items.append(dict(key=key, label=label, contestants=contestants))
        groups.append(dict(section=group.get("section") or "Announced matchups", items=items))
    return groups


def find_matchup(record, key):
    if not re.fullmatch(r"[a-f0-9]{64}", key or ""):
        abort(404)
    for group in matchups(record):
        for item in group["items"]:
            if item["key"] == key:
                return item
    abort(404)


def build_battle_rows(record, factory, voter_hash=None):
    groups = matchups(record)
    keys = [item["key"] for group in groups for item in group["items"]]
    if not keys:
        return groups
    with factory() as db:
        outcomes = {
            r.battle_key: r for r in db.query(VaultBattleOutcome)
            .filter(VaultBattleOutcome.battle_key.in_(keys)).all()
        }
        tally = {
            (key, choice): count for key, choice, count in db.query(
                VaultBattleVote.battle_key, VaultBattleVote.choice,
                func.count(VaultBattleVote.id)
            ).filter(VaultBattleVote.battle_key.in_(keys)).group_by(
                VaultBattleVote.battle_key, VaultBattleVote.choice
            ).all()
        }
        already_voted = set()
        if voter_hash:
            already_voted = {
                r.battle_key for r in db.query(VaultBattleVote)
                .filter(VaultBattleVote.battle_key.in_(keys),
                        VaultBattleVote.voter_hash == voter_hash).all()
            }
    for group in groups:
        for item in group["items"]:
            row = outcomes.get(item["key"])
            item["occurred"] = row.occurred if row else "unconfirmed"
            item["result"] = row.result if row else "unknown"
            item["source_note"] = row.source_note if row else ""
            item["active_poll"] = (
                item["occurred"] == "happened"
                and item["result"] in POLL_RESULTS
                and len(item["contestants"]) == 2
            )
            if item["result"] in ("a", "b") and len(item["contestants"]) == 2:
                item["outcome_label"] = "Winner: " + item["contestants"][item["result"] == "b"]
            else:
                item["outcome_label"] = RESULT_LABELS.get(item["result"], "Result unconfirmed")
            item["votes_a"] = tally.get((item["key"], "a"), 0)
            item["votes_b"] = tally.get((item["key"], "b"), 0)
            item["total_votes"] = item["votes_a"] + item["votes_b"]
            item["percent_a"] = round(item["votes_a"] * 100 / item["total_votes"]) if item["total_votes"] else 0
            item["percent_b"] = 100 - item["percent_a"] if item["total_votes"] else 0
            item["already_voted"] = item["key"] in already_voted
    return groups


def install_battle_polls(app, ns):
    @app.post("/archive/records/<slug>/battles/<battle_key>/vote", endpoint="vault_battle_vote")
    def vote(slug, battle_key):
        record = find_record(slug)
        matchup = find_matchup(record, battle_key)
        expected = session.get("vault_archive_csrf")
        if not expected or not secrets.compare_digest(expected, request.form.get("csrf_token") or ""):
            abort(400, "Invalid voting token")
        identity = verified_nominator_hash()
        if not identity:
            abort(403, "Verify your email before voting")
        choice = (request.form.get("choice") or "").strip()
        if choice not in ("a", "b") or len(matchup["contestants"]) != 2:
            abort(400)
        with ns["SessionLocal"].begin() as db:
            outcome = db.get(VaultBattleOutcome, battle_key)
            if not outcome or outcome.event_slug != slug or outcome.occurred != "happened" or outcome.result not in POLL_RESULTS:
                abort(403, "Voting is only available on confirmed ties and YouTube Decides")
            existing = db.query(VaultBattleVote).filter_by(
                battle_key=battle_key, voter_hash=identity
            ).first()
            if existing:
                abort(409, "You have already voted in this battle")
            db.add(VaultBattleVote(battle_key=battle_key, voter_hash=identity, choice=choice))
            try:
                db.flush()
            except IntegrityError:
                abort(409, "You have already voted in this battle")
        flash("Your community vote was recorded. The official battle result is unchanged.", "battle")
        return redirect(url_for("vault_archive_record", slug=slug) + "#battle-" + battle_key[:12], code=303)

    @app.post("/admin/archive/records/<slug>/battles/<battle_key>/outcome",
              endpoint="vault_battle_outcome")
    @ns["admin_login_required"]
    def update_outcome(slug, battle_key):
        record = find_record(slug)
        matchup = find_matchup(record, battle_key)
        expected = session.get("vault_archive_csrf")
        if not expected or not secrets.compare_digest(expected, request.form.get("csrf_token") or ""):
            abort(400, "Invalid editorial token")
        occurred = (request.form.get("occurred") or "").strip()
        result = (request.form.get("result") or "").strip()
        source_note = (request.form.get("source_note") or "").strip()
        if occurred not in OCCURRENCE or result not in RESULTS or len(source_note) > 500:
            abort(400, "Invalid outcome")
        if occurred != "happened" and result != "unknown":
            abort(400, "A result requires a confirmed occurrence")
        if result in ("a", "b", "tie", "youtube_decide") and len(matchup["contestants"]) != 2:
            abort(400, "This lineup needs two clear sides before recording a result")
        if (occurred not in ("unconfirmed", "scheduled") or result != "unknown") and len(source_note) < 5:
            abort(400, "Record the source for this editorial decision")
        now = datetime.utcnow()
        with ns["SessionLocal"].begin() as db:
            row = db.get(VaultBattleOutcome, battle_key)
            previous = dict(occurred=row.occurred, result=row.result,
                            source_note=row.source_note) if row else None
            if row:
                row.occurred, row.result, row.source_note, row.updated_at = (
                    occurred, result, source_note or None, now
                )
            else:
                db.add(VaultBattleOutcome(
                    battle_key=battle_key, event_slug=slug,
                    lineup_label=matchup["label"][:500], occurred=occurred,
                    result=result, source_note=source_note or None,
                    updated_at=now
                ))
            db.add(VaultBattleOutcomeHistory(
                battle_key=battle_key, event_slug=slug,
                previous_occurrence=previous["occurred"] if previous else None,
                previous_result=previous["result"] if previous else None,
                occurred=occurred, result=result,
                source_note=source_note or None, updated_at=now
            ))
        flash("Battle record updated with a preserved edit history.", "battle")
        return redirect(url_for("vault_archive_record", slug=slug) + "#battle-" + battle_key[:12], code=303)
