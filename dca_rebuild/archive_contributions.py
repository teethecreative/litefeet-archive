"""General LiteFeet history submissions: a dedicated private archival workflow.

This does NOT create event/calendar records, modify source records or accept
LiteFeet Awards submissions. Every contribution stays private until reviewed.
"""
from datetime import datetime
import json
from urllib.parse import urlsplit
import secrets

from flask import abort, jsonify, redirect, render_template, request, session, url_for
from dca_rebuild.models import VaultArchiveContribution, VaultArchiveContributionReview, VaultArchiveContributionDetail

CONTRIBUTION_TYPES = (
    ("history", "LiteFeet history"),
    ("person", "Dancer / person"),
    ("team", "Crew / team"),
    ("battle", "Battle / result"),
    ("event_history", "Past event / session"),
    ("music", "Music / producer"),
    ("media", "Footage / photograph / flyer"),
    ("correction", "Correction / new evidence"),
    ("other", "Other historical information"),
)
_ALLOWED_TYPES = {value for value, _ in CONTRIBUTION_TYPES}
_REVIEW_STATUSES = ("pending", "approved", "rejected")

# Server-side whitelist: never trust the dynamically hidden browser fields.
DETAIL_FIELDS = {
    "history": ("era", "location", "people_involved", "story_context"),
    "person": ("person_name", "aliases", "teams", "active_years", "contributions"),
    "team": ("team_name", "founding_period", "team_members", "team_location", "team_history"),
    "battle": ("battle_name", "battle_date", "battle_location", "participants",
               "battle_result", "judges", "footage_timestamps"),
    "event_history": ("event_name", "event_date", "event_location", "organizers",
                      "event_participants", "event_outcome"),
    "music": ("track_title", "artist_producer", "release_period", "music_context", "music_credits"),
    "media": ("media_type", "media_subject", "media_date", "media_creator",
              "media_context", "media_permissions"),
    "correction": ("record_reference", "current_claim", "proposed_correction", "correction_evidence"),
    "other": ("other_subject", "other_context"),
}
DETAIL_LABELS = {
    "era": "Era", "location": "Location", "people_involved": "People involved",
    "story_context": "Historical significance", "person_name": "Person / dancer",
    "aliases": "Aliases", "teams": "Crews / affiliations", "active_years": "Active years",
    "contributions": "Notable contributions", "team_name": "Crew / team",
    "founding_period": "Founded / active period", "team_members": "Members",
    "team_location": "Team location", "team_history": "Team history",
    "battle_name": "Battle", "battle_date": "Battle date", "battle_location": "Battle venue",
    "participants": "Participants", "battle_result": "Result (if confirmed)",
    "judges": "Judges / host", "footage_timestamps": "Footage / timestamps",
    "event_name": "Historical event", "event_date": "Event date",
    "event_location": "Event location", "organizers": "Organizers",
    "event_participants": "Participants", "event_outcome": "What happened",
    "track_title": "Track", "artist_producer": "Artist / producer",
    "release_period": "Release period", "music_context": "LiteFeet context",
    "music_credits": "Credits", "media_type": "Media type",
    "media_subject": "Media subject", "media_date": "Media date",
    "media_creator": "Creator", "media_context": "Media context",
    "media_permissions": "Rights / permissions",
    "record_reference": "Archive record", "current_claim": "Current claim",
    "proposed_correction": "Proposed correction", "correction_evidence": "Evidence",
    "other_subject": "Subject", "other_context": "Context",
}


def _public_csrf():
    token = session.get("vault_archive_contribution_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["vault_archive_contribution_csrf"] = token
    return token


def _admin_csrf():
    token = session.get("vault_archive_contribution_admin_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["vault_archive_contribution_admin_csrf"] = token
    return token


def _check_csrf(key):
    expected = session.get(key)
    supplied = request.form.get("csrf_token", "")
    if not expected or not secrets.compare_digest(str(expected), str(supplied)):
        abort(400, "Invalid submission token. Refresh and try again.")


def _validate():
    if request.content_length is not None and request.content_length > 16000:
        abort(413)
    if request.form.get("website"):
        abort(400)
    kind = (request.form.get("contribution_type") or "").strip()
    title = " ".join((request.form.get("title") or "").split())
    description = (request.form.get("description") or "").strip()
    historical_period = " ".join((request.form.get("historical_period") or "").split())
    source_url = (request.form.get("source_url") or "").strip()
    source_description = (request.form.get("source_description") or "").strip()
    contributor_name = " ".join((request.form.get("contributor_name") or "").split())
    contact_email = (request.form.get("contact_email") or "").strip().lower()
    if kind not in _ALLOWED_TYPES:
        return None, "Choose a historical contribution type."
    if not 3 <= len(title) <= 240:
        return None, "Enter a title between 3 and 240 characters."
    if not 20 <= len(description) <= 4000:
        return None, "Describe what happened or what should be corrected (20–4000 characters)."
    if len(historical_period) > 120 or len(source_description) > 1500:
        return None, "Shorten the date or source context."
    if not source_url and not source_description:
        return None, "Include a source link or describe how the information is known."
    if source_url:
        parsed = urlsplit(source_url)
        if (len(source_url) > 1000 or parsed.scheme not in ("http", "https")
                or not parsed.netloc or parsed.username or parsed.password):
            return None, "Provide a valid http(s) source link."
    if len(contributor_name) > 160:
        return None, "Shorten the contributor name."
    if (len(contact_email) > 320 or not contact_email or
            "@" not in contact_email or "." not in contact_email.rsplit("@", 1)[-1]
            or any(char.isspace() for char in contact_email)):
        return None, "Enter a valid contact email for editorial follow-up."
    details = {}
    for field in DETAIL_FIELDS[kind]:
        value = (request.form.get("detail_" + field) or "").strip()
        limit = 1500 if field in {
            "story_context", "contributions", "team_members", "team_history",
            "participants", "footage_timestamps", "event_participants",
            "event_outcome", "music_context", "music_credits", "media_context",
            "media_permissions", "current_claim", "proposed_correction",
            "correction_evidence", "other_context",
        } else 500
        if len(value) > limit:
            return None, "A type-specific answer is too long."
        if value:
            details[field] = value
    return dict(contribution_type=kind, title=title, description=description,
                historical_period=historical_period or None, source_url=source_url or None,
                source_description=source_description or None,
                contributor_name=contributor_name or None, contact_email=contact_email,
                details=details), None


def install_archive_contributions(app, ns):
    admin_required = ns["admin_login_required"]

    @app.context_processor
    def inject_archive_contribution_token():
        if request.endpoint in ("vault_community", "vault_archive"):
            return {"archive_contribution_csrf": _public_csrf(),
                    "archive_contribution_types": CONTRIBUTION_TYPES}
        return {}

    @app.get("/archive/contribute", endpoint="vault_archive_contribute_form")
    def contribution_form():
        return render_template("archive_contribution_page.html",
                               archive_contribution_csrf=_public_csrf(),
                               archive_contribution_types=CONTRIBUTION_TYPES)

    @app.post("/archive/contribute", endpoint="vault_archive_contribute")
    def contribute():
        _check_csrf("vault_archive_contribution_csrf")
        data, error = _validate()
        last = session.get("vault_archive_contribution_last_at")
        if not error and last:
            try:
                if (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds() < 60:
                    error = "Please wait a minute before submitting another item."
            except (ValueError, TypeError):
                pass
        is_ajax = (request.headers.get("Accept", "").find("application/json") >= 0)
        if error:
            if is_ajax:
                return jsonify(ok=False, error=error), 400
            return render_template("archive_contribution_page.html",
                                   archive_contribution_csrf=_public_csrf(),
                                   archive_contribution_types=CONTRIBUTION_TYPES,
                                   archive_error=error), 400

        details = data.pop("details")
        with ns["SessionLocal"].begin() as db:
            entry = VaultArchiveContribution(**data, status="pending")
            db.add(entry)
            db.flush()
            db.add(VaultArchiveContributionDetail(
                contribution_id=entry.id,
                details_json=json.dumps(details, ensure_ascii=False)))
        session["vault_archive_contribution_last_at"] = datetime.utcnow().isoformat()
        if is_ajax:
            return jsonify(ok=True, message="Historical information received for private archive review."), 201
        return redirect(url_for("vault_community", archive_submitted="1") + "#contribute", code=303)

    @app.get("/admin/archive/contributions", endpoint="admin_archive_contributions")
    @admin_required
    def admin_contributions():
        status = (request.args.get("status") or "pending").strip()
        if status not in ("all",) + _REVIEW_STATUSES:
            abort(400)
        page = request.args.get("page", 1, type=int)
        if page is None or not 1 <= page <= 10000:
            abort(400)
        with ns["SessionLocal"]() as db:
            query = db.query(VaultArchiveContribution)
            if status != "all":
                query = query.filter(VaultArchiveContribution.status == status)
            total = query.count()
            records = query.order_by(
                VaultArchiveContribution.created_at.desc(),
                VaultArchiveContribution.id.desc()
            ).offset((page - 1) * 20).limit(20).all()
            selected_ids = [r.id for r in records]
            details_by_id = {}
            if selected_ids:
                details_by_id = {
                    d.contribution_id: json.loads(d.details_json or "{}")
                    for d in db.query(VaultArchiveContributionDetail)
                    .filter(VaultArchiveContributionDetail.contribution_id.in_(selected_ids)).all()
                }
            rows = [dict(id=r.id, contribution_type=r.contribution_type,
                         details=[(DETAIL_LABELS.get(key, key.replace("_", " ").title()), val)
                                  for key, val in details_by_id.get(r.id, {}).items()
                                  if key in DETAIL_FIELDS.get(r.contribution_type, ())],
                         title=r.title, description=r.description,
                         historical_period=r.historical_period, source_url=r.source_url,
                         source_description=r.source_description,
                         contributor_name=r.contributor_name,
                         contact_email=r.contact_email, created_at=r.created_at,
                         status=r.status) for r in records]
        return render_template("admin_archive_contributions.html",
                               rows=rows, total=total, page=page, status=status,
                               pages=max(1, (total + 19) // 20),
                               csrf_token=_admin_csrf())

    @app.post("/admin/archive/contributions/<int:record_id>/decision",
              endpoint="admin_archive_contribution_decision")
    @admin_required
    def review_contribution(record_id):
        _check_csrf("vault_archive_contribution_admin_csrf")
        decision = (request.form.get("decision") or "").strip()
        note = (request.form.get("note") or "").strip()
        if decision not in ("approved", "rejected") or len(note) > 1000:
            abort(400)
        with ns["SessionLocal"].begin() as db:
            record = db.get(VaultArchiveContribution, record_id)
            if record is None:
                abort(404)
            if record.status != "pending":
                abort(409, "This submission has already been reviewed.")
            record.status = decision
            record.reviewed_at = datetime.utcnow()
            db.add(VaultArchiveContributionReview(
                contribution_id=record.id, decision=decision, note=note or None))
        return redirect(url_for("admin_archive_contributions"), code=303)
