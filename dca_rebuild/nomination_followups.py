"""Private, opt-in completion prompts for returning DCA nominators.

Only saved nomination explanations are requested. The original nomination, date,
vote count and cooldown are never modified. New explanations use the existing
human-reviewed qualification-reason workflow.
"""
from __future__ import annotations

import re
import secrets

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from dca_rebuild.models import DCACategory, DCAEdition, DCANominee, DCANominationSubmission
from dca_rebuild.phase9e import NominationDetail9E, NomineeQualificationReason9E


def _recognized_nominator():
    # The signed Flask session contains only a server-derived identity hash.
    # Never place a submitter's email or nomination detail in browser scripts.
    return session.get("lf9e_reminder_hash") or session.get("lf9e_recent_hash")


def _followups(db, edition_id, submitter_hash):
    """Find missing *personal* explanations, not public nominee eligibility."""
    if not submitter_hash:
        return []
    rows = (
        db.query(
            DCANominationSubmission.id, DCANominee.id, DCANominee.name,
            DCACategory.name, NominationDetail9E.justification,
        )
        .join(DCANominee, DCANominee.id == DCANominationSubmission.nominee_id)
        .join(DCACategory, DCACategory.id == DCANominee.category_id)
        .outerjoin(NominationDetail9E,
                   NominationDetail9E.submission_id == DCANominationSubmission.id)
        .filter(DCANominationSubmission.edition_id == edition_id,
                DCANominationSubmission.submitter_hash == submitter_hash)
        .order_by(DCANominationSubmission.submitted_at, DCANominationSubmission.id)
        .all()
    )
    # All previously submitted supplemental reasons are already in the admin
    # review queue. Never ask the user to resubmit while they await a decision.
    covered = {
        row.nominee_id for row in db.query(NomineeQualificationReason9E).filter_by(
            edition_id=edition_id, submitter_hash=submitter_hash).all()
    }
    pending = {}
    for submission_id, nominee_id, nominee, category, explanation in rows:
        if nominee_id in covered or len((explanation or "").strip()) >= 20:
            continue
        # An old nominee may have several nominations. Ask only once per nominee.
        pending.setdefault(nominee_id, {
            "nominee_id": nominee_id, "nominee": nominee,
            "category": category, "submission_id": submission_id,
        })
    return sorted(pending.values(), key=lambda item: (
        item["category"].casefold(), item["nominee"].casefold()
    ))


def install_nomination_followups(app, session_factory):
    """Install after the awards nomination routes are registered."""

    @app.get("/awards/dancers-choice/followup-status")
    def dca_followup_status():
        who = _recognized_nominator()
        count = 0
        if who:
            with session_factory() as db:
                edition = db.query(DCAEdition).filter_by(year=2026).first()
                if edition:
                    count = len(_followups(db, edition.id, who))
        response = jsonify(needs_details=count)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.route("/awards/dancers-choice/my-nomination-followups", methods=["GET", "POST"])
    def dca_my_nomination_followups():
        who = _recognized_nominator()
        if not who:
            flash("Enter your email on the nominations page to continue.")
            return redirect(url_for("dca_nominations_closed"))
        session.setdefault("lf9e_followup_csrf", secrets.token_urlsafe(32))
        with session_factory() as db:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            if not edition:
                abort(404)
            pending = _followups(db, edition.id, who)
            if request.method == "POST":
                token = request.form.get("csrf_token", "")
                if not token or not secrets.compare_digest(
                    token, session["lf9e_followup_csrf"]
                ):
                    abort(400, "This form expired. Refresh and try again.")
                nominee_id = request.form.get("nominee_id", type=int)
                if not any(item["nominee_id"] == nominee_id for item in pending):
                    abort(404)
                reason = (request.form.get("reason") or "").strip()
                evidence = (request.form.get("evidence_url") or "").strip()
                if not 20 <= len(reason) <= 2000:
                    abort(400, "Please describe the nomination in 20–2000 characters.")
                if evidence and (len(evidence) > 500 or
                                 not re.fullmatch(r"https?://[^\\s]+", evidence)):
                    abort(400, "Enter a valid link beginning with https:// or http://.")
                db.add(NomineeQualificationReason9E(
                    edition_id=edition.id, nominee_id=nominee_id,
                    submitter_hash=who, reason=reason, evidence_url=evidence or None,
                    moderation_status="pending"
                ))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    abort(409, "You already submitted information for this nominee.")
                flash("Details received for review. Your original nomination is unchanged.")
                return redirect(url_for("dca_my_nomination_followups"), code=303)
            response = render_template(
                "dca_my_nomination_followups.html",
                pending=pending, csrf_token=session["lf9e_followup_csrf"],
            )
        # Personalized nominations must not be stored in shared or browser caches.
        from flask import make_response
        result = make_response(response)
        result.headers["Cache-Control"] = "private, no-store"
        result.headers["Referrer-Policy"] = "same-origin"
        result.headers["X-Robots-Tag"] = "noindex, nofollow"
        return result

    @app.after_request
    def dca_returning_nominator_prompt(response):
        """Load a small reminder only in recognized, public HTML sessions."""
        if (request.method != "GET" or response.status_code != 200
            or not _recognized_nominator()
            or request.path.startswith(("/admin", "/static", "/account", "/health"))
            or "text/html" not in response.content_type.lower()
            or response.direct_passthrough):
            return response
        html = response.get_data(as_text=True)
        if "</body>" not in html.lower() or "nomination-followups.js" in html:
            return response
        html = re.sub(
            r"</body\\s*>",
            '<script defer src="/static/js/nomination-followups.js"></script></body>',
            html, count=1, flags=re.I,
        )
        response.set_data(html)
        return response
