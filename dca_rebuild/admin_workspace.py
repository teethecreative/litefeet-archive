"""Unified private Admin Overview and development workflow for The LiteFeet Vault.

Reuses existing moderation models and routes rather than modifying their records.
All queue views are authenticated; new feedback stays private until reviewed.
"""
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import secrets

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import or_

from dca_rebuild.models import (
    VaultGatheringSubmission, LFAArchiveSubmission, DCANewCategorySuggestion,
    DCANominee, BetaFeedback, VaultArchiveVerification, LockInCardRequest,
    VaultDevelopmentItem, VaultDevelopmentFeedback,
)
from dca_rebuild.phase9e import NomineeQualificationReason9E

AREAS = ("site", "archive", "awards", "events", "music", "lock-in", "other")
DEVELOPMENT_STATES = ("needs_review", "needs_work", "planned", "active", "done", "not_planned")
FEEDBACK_STATES = ("new", "reviewed", "dismissed", "converted")
QUEUE_SECTIONS = ("all", "events", "awards", "archive", "community", "lock-in")
PAGE_SIZE = 10
# Status-specific work expected from the reviewer; these labels do not claim
# a submitted record is invalid or that a historical result is incorrect.
REVIEW_REASONS = {
    "Event submission": "Check event details and decide whether to publish.",
    "DCA category suggestion": "Review the proposed category; approve, merge, or reject.",
    "DCA nominee": "Review the nominee and decide approval or rejection.",
    "LiteFeet Awards submission": "Verify the historical award information before approval.",
    "DCA qualification reason": "Review supporting statements or evidence; eligibility is not automatic.",
    "Beta feedback": "Triage new Beta feedback and decide the next action.",
    "Archive response": "Review a community statement against available sources.",
    "Lock In card request": "Review the card suggestion before adding it to the game.",
    "Website feedback": "Triage the website report and decide whether to create a task.",
}
# Every spec is a real, existing source, not a synthetic task.
SOURCES = (
    ("events", VaultGatheringSubmission, "status", "pending", "created_at",
     "title", "Event submission", "admin_vault_gathering_edit"),
    ("awards", DCANewCategorySuggestion, "moderation_status", "pending", "created_at",
     "category_name", "DCA category suggestion", "admin_round1"),
    ("awards", DCANominee, "moderation_status", "pending", "created_at",
     "name", "DCA nominee", "admin_dca_nominations"),
    ("awards", LFAArchiveSubmission, "status", "pending", "created_at",
     "winner_name", "LiteFeet Awards submission", "admin_lfa_submissions"),
    ("awards", NomineeQualificationReason9E, "moderation_status", "pending", "submitted_at",
     "reason", "DCA qualification reason", "phase9e_admin_qualification_reasons"),
    ("community", BetaFeedback, "status", "new", "created_at",
     "message", "Beta feedback", "admin_beta_feedback"),
    ("archive", VaultArchiveVerification, "moderation_status", "pending", "created_at",
     "record_slug", "Archive response", "admin_vault_auxiliary_review"),
    ("lock-in", LockInCardRequest, "status", "pending", "created_at",
     "card_name", "Lock In card request", "admin_vault_auxiliary_review"),
    ("community", VaultDevelopmentFeedback, "status", "new", "created_at",
     "title", "Website feedback", "admin_vault_development"),
)


def _admin_token():
    if "vault_admin_workspace_csrf" not in session:
        session["vault_admin_workspace_csrf"] = secrets.token_urlsafe(32)
    return session["vault_admin_workspace_csrf"]


def _require_admin_token():
    token = session.get("vault_admin_workspace_csrf")
    submitted = request.form.get("csrf_token", "")
    if not token or not secrets.compare_digest(str(token), submitted):
        abort(400)


def _clamp_page():
    try:
        page = int(request.args.get("page", "1"))
    except (TypeError, ValueError):
        abort(400)
    if page < 1 or page > 10000:
        abort(400)
    return page


def _queue(db, section="all", page=1, sort="oldest"):
    if section not in QUEUE_SECTIONS or sort not in ("oldest", "newest"):
        abort(400)
    count, candidates = 0, []
    # Fetch enough candidates from each source to produce correct global page
    # ordering, rather than independently paginating each source's rows.
    sample_size = page * PAGE_SIZE
    for category, model, status_attr, pending_value, time_attr, title_attr, label, endpoint in SOURCES:
        if section != "all" and section != category:
            continue
        q = db.query(model).filter(getattr(model, status_attr) == pending_value)
        count += q.count()
        date_col = getattr(model, time_attr)
        rows = q.order_by(date_col.desc() if sort == "newest" else date_col.asc(),
                          model.id.desc() if sort == "newest" else model.id.asc()).limit(sample_size).all()
        for entry in rows:
            received = getattr(entry, time_attr)
            candidates.append(dict(
                id=entry.id, section=category, label=label,
                title=str(getattr(entry, title_attr) or "Untitled")[:180],
                received=received, endpoint=endpoint,
                reason=REVIEW_REASONS.get(label, "Pending moderation decision."),
            ))
    candidates.sort(
        key=lambda x: (x["received"] or datetime.min, x["section"], x["id"]),
        reverse=(sort == "newest"),
    )
    return count, candidates[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]


def install_admin_workspace(app, ns):
    # Read the active session factory at request time for isolated test databases.
    admin_required = ns["admin_login_required"]

    @app.get("/admin/review-queue", endpoint="admin_vault_review_queue")
    @admin_required
    def admin_review_queue():
        section = request.args.get("section", "all")
        sort = request.args.get("sort", "oldest")
        page = _clamp_page()
        with ns["SessionLocal"]() as db:
            total, rows = _queue(db, section, page, sort)
        return render_template("admin_workspace_queue.html", rows=rows,
                               section=section, sort=sort, page=page,
                               total=total, pages=(total + PAGE_SIZE - 1) // PAGE_SIZE,
                               sections=QUEUE_SECTIONS)

    @app.get("/admin/review-records", endpoint="admin_vault_auxiliary_review")
    @admin_required
    def auxiliary_review():
        source = request.args.get("source") or "all"
        if source not in ("all", "archive", "lock-in"):
            abort(400)
        with ns["SessionLocal"]() as db:
            archive = db.query(VaultArchiveVerification).filter_by(
                moderation_status="pending").order_by(
                VaultArchiveVerification.created_at.asc()).limit(100).all() if source != "lock-in" else []
            cards = db.query(LockInCardRequest).filter_by(
                status="pending").order_by(
                LockInCardRequest.created_at.asc()).limit(100).all() if source != "archive" else []
            archive_rows = [dict(id=x.id, slug=x.record_slug, vote=x.vote,
                                 explanation=x.explanation, at=x.created_at) for x in archive]
            card_rows = [dict(id=x.id, name=x.card_name, kind=x.card_type,
                              details=x.details_json, source=x.source_url,
                              at=x.created_at) for x in cards]
        return render_template("admin_workspace_auxiliary.html", archive=archive_rows,
                               cards=card_rows, source=source, csrf_token=_admin_token())

    @app.post("/admin/review-records/<source>/<int:record_id>", endpoint="admin_vault_auxiliary_decision")
    @admin_required
    def auxiliary_decision(source, record_id):
        _require_admin_token()
        decision = request.form.get("decision")
        if source not in ("archive", "lock-in") or decision not in ("approved", "rejected"):
            abort(400)
        model = VaultArchiveVerification if source == "archive" else LockInCardRequest
        status_field = "moderation_status" if source == "archive" else "status"
        with ns["SessionLocal"].begin() as db:
            entry = db.get(model, record_id)
            if entry is None:
                abort(404)
            if getattr(entry, status_field) != "pending":
                abort(400)
            setattr(entry, status_field, decision)
            if source == "lock-in":
                entry.reviewed_at = datetime.utcnow()
            else:
                entry.updated_at = datetime.utcnow()
        flash("Record review saved.", "admin")
        return redirect(url_for("admin_vault_auxiliary_review", source=source), code=303)

    @app.get("/admin/development", endpoint="admin_vault_development")
    @admin_required
    def admin_development():
        state = request.args.get("status", "all")
        area = request.args.get("area", "all")
        if state not in ("all",) + DEVELOPMENT_STATES or area not in ("all",) + AREAS:
            abort(400)
        page = _clamp_page()
        with ns["SessionLocal"]() as db:
            q = db.query(VaultDevelopmentItem)
            if state != "all":
                q = q.filter(VaultDevelopmentItem.status == state)
            if area != "all":
                q = q.filter(VaultDevelopmentItem.area == area)
            total = q.count()
            items = q.order_by(VaultDevelopmentItem.updated_at.desc(),
                               VaultDevelopmentItem.id.desc()).offset(
                                   (page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
            feedback = db.query(VaultDevelopmentFeedback).filter(
                VaultDevelopmentFeedback.status == "new").order_by(
                VaultDevelopmentFeedback.created_at.asc(),
                VaultDevelopmentFeedback.id.asc()).limit(25).all()
            counts = {s: db.query(VaultDevelopmentItem).filter_by(status=s).count()
                      for s in DEVELOPMENT_STATES}
        return render_template("admin_workspace_development.html", items=items,
                               feedback=feedback, counts=counts, total=total,
                               state=state, area=area, page=page,
                               pages=(total + PAGE_SIZE - 1) // PAGE_SIZE,
                               states=DEVELOPMENT_STATES, areas=AREAS,
                               csrf_token=_admin_token())

    @app.post("/admin/development/create", endpoint="admin_vault_development_create")
    @admin_required
    def development_create():
        _require_admin_token()
        title = (request.form.get("title") or "").strip()[:240]
        details = (request.form.get("description") or "").strip()[:3000]
        area = request.form.get("area") or "site"
        if len(title) < 3 or area not in AREAS:
            abort(400)
        with ns["SessionLocal"].begin() as db:
            db.add(VaultDevelopmentItem(title=title, description=details or None,
                                        area=area, status="needs_review"))
        flash("Development item created.", "admin")
        return redirect(url_for("admin_vault_development"), code=303)

    @app.post("/admin/development/<int:item_id>/status", endpoint="admin_vault_development_status")
    @admin_required
    def development_status(item_id):
        _require_admin_token()
        state = request.form.get("status")
        if state not in DEVELOPMENT_STATES:
            abort(400)
        with ns["SessionLocal"].begin() as db:
            item = db.get(VaultDevelopmentItem, item_id)
            if item is None:
                abort(404)
            item.status = state
            item.updated_at = datetime.utcnow()
        flash("Development status saved.", "admin")
        return redirect(url_for("admin_vault_development"), code=303)

    @app.post("/admin/development/feedback/<int:feedback_id>/decision",
              endpoint="admin_vault_feedback_decision")
    @admin_required
    def feedback_decision(feedback_id):
        _require_admin_token()
        decision = request.form.get("decision")
        if decision not in ("reviewed", "dismissed", "converted"):
            abort(400)
        with ns["SessionLocal"].begin() as db:
            entry = db.get(VaultDevelopmentFeedback, feedback_id)
            if entry is None:
                abort(404)
            if entry.status != "new":
                abort(400)
            if decision == "converted":
                db.add(VaultDevelopmentItem(
                    title=entry.title, description=entry.details, area=entry.area,
                    status="needs_review", source_feedback_id=entry.id))
            entry.status = decision
            entry.reviewed_at = datetime.utcnow()
        flash("Feedback reviewed.", "admin")
        return redirect(url_for("admin_vault_development"), code=303)

    @app.route("/feedback/development", methods=["GET", "POST"],
               endpoint="vault_development_feedback_public")
    def public_feedback():
        if request.method == "GET":
            token = secrets.token_urlsafe(32)
            session["vault_development_feedback_csrf"] = token
            return render_template("vault_development_feedback.html", csrf_token=token)
        if request.content_length and request.content_length > 12000:
            abort(413)
        token = session.get("vault_development_feedback_csrf")
        if not token or not secrets.compare_digest(str(token), str(request.form.get("csrf_token") or "")):
            abort(400)
        if request.form.get("website"):
            abort(400)
        last = session.get("vault_development_feedback_at")
        now = datetime.now(ZoneInfo("America/New_York"))
        if last:
            try:
                if (now - datetime.fromisoformat(last)).total_seconds() < 120:
                    abort(429)
            except (TypeError, ValueError):
                pass
        title = (request.form.get("title") or "").strip()[:240]
        details = (request.form.get("details") or "").strip()[:3000]
        area = request.form.get("area") or "site"
        email = (request.form.get("email") or "").strip().lower()[:255]
        if len(title) < 3 or len(details) < 10 or area not in AREAS:
            abort(400)
        if email and ("@" not in email or "." not in email.split("@")[-1]):
            abort(400)
        with ns["SessionLocal"].begin() as db:
            db.add(VaultDevelopmentFeedback(title=title, details=details,
                                            area=area, contact_email=email or None))
        session["vault_development_feedback_at"] = now.isoformat()
        session.pop("vault_development_feedback_csrf", None)
        return render_template("vault_development_feedback.html", submitted=True), 200
