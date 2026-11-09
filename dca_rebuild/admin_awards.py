"""Private DCA 2026 administration separated from the earlier category survey.

No mutation of nomination submissions, historical survey votes or published results.
"""
from datetime import datetime
import secrets

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func

from dca_rebuild.models import (
    DCAEdition, DCACategory, DCANominee, DCANominationSubmission,
)

PAGE_SIZE = 20


def _moderation_token():
    if "awards_workspace_csrf" not in session:
        session["awards_workspace_csrf"] = secrets.token_urlsafe(32)
    return session["awards_workspace_csrf"]


def _check_moderation_token():
    expected = session.get("awards_workspace_csrf")
    posted = request.form.get("csrf_token", "")
    if not expected or not secrets.compare_digest(str(expected), str(posted)):
        abort(400, "Invalid administration token")


def _page():
    try:
        number = int(request.args.get("page", "1"))
    except (TypeError, ValueError):
        abort(400)
    if number < 1 or number > 100000:
        abort(400)
    return number


def _edition(db):
    item = db.query(DCAEdition).filter_by(year=2026).first()
    if item is None:
        abort(404, "DCA 2026 edition not found")
    return item


def _stats(db, edition_id):
    return {
        "categories": db.query(DCACategory).filter_by(edition_id=edition_id).count(),
        "official_categories": db.query(DCACategory).filter_by(
            edition_id=edition_id, status="official").count(),
        "nominees": db.query(DCANominee).filter_by(edition_id=edition_id).count(),
        "pending_nominees": db.query(DCANominee).filter_by(
            edition_id=edition_id, moderation_status="pending").count(),
        "nominations": db.query(DCANominationSubmission).filter_by(edition_id=edition_id).count(),
    }


def install_awards_admin(app, ns):
    admin_required = ns["admin_login_required"]

    @app.get("/admin/awards", endpoint="admin_awards_overview")
    @admin_required
    def awards_overview():
        with ns["SessionLocal"]() as db:
            edition = _edition(db)
            stats = _stats(db, edition.id)
            phase = edition.phase
        return render_template("admin_awards_overview.html", stats=stats, phase=phase)

    @app.route("/admin/awards/categories", methods=["GET", "POST"],
               endpoint="admin_awards_categories")
    @admin_required
    def awards_categories():
        if request.method == "POST":
            _check_moderation_token()
            try:
                category_id = int(request.form.get("category_id", ""))
            except (TypeError, ValueError):
                abort(400)
            description = (request.form.get("description") or "").strip()
            if len(description) > 4000:
                abort(400, "Description exceeds the allowed length")
            with ns["SessionLocal"].begin() as db:
                edition = _edition(db)
                category = db.query(DCACategory).filter_by(
                    id=category_id, edition_id=edition.id).first()
                if category is None:
                    abort(404)
                category.description = description or None
            flash("2026 category description saved. Nomination and survey records were not changed.")
            return redirect(url_for("admin_awards_categories"), code=303)

        with ns["SessionLocal"]() as db:
            edition = _edition(db)
            categories = db.query(DCACategory).filter_by(
                edition_id=edition.id).order_by(DCACategory.name.asc()).all()
            ids = [c.id for c in categories]
            totals = dict(db.query(
                DCANominee.category_id, func.count(DCANominee.id)
            ).filter(DCANominee.category_id.in_(ids),
                     DCANominee.edition_id == edition.id).group_by(
                DCANominee.category_id).all()) if ids else {}
            rows = [dict(id=c.id, name=c.name, description=c.description or "",
                         status=c.status, origin=c.source_type,
                         nominee_count=totals.get(c.id, 0)) for c in categories]
        return render_template("admin_awards_categories.html", rows=rows,
                               csrf_token=_moderation_token())

    @app.get("/admin/awards/activity", endpoint="admin_awards_activity")
    @admin_required
    def awards_activity():
        page = _page()
        with ns["SessionLocal"]() as db:
            edition = _edition(db)
            query = (db.query(DCANominationSubmission, DCANominee.name,
                              DCACategory.name, DCANominee.moderation_status)
                     .join(DCANominee, DCANominationSubmission.nominee_id == DCANominee.id)
                     .join(DCACategory, DCANominee.category_id == DCACategory.id)
                     .filter(DCANominationSubmission.edition_id == edition.id,
                             DCANominee.edition_id == edition.id,
                             DCACategory.edition_id == edition.id))
            total = query.count()
            rows = query.order_by(
                DCANominationSubmission.submitted_at.desc(),
                DCANominationSubmission.id.desc()
            ).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
            activity = [dict(id=n.id, at=n.submitted_at, nominee=nominee,
                             category=category, status=status,
                             has_contact=bool(n.submitter_email))
                        for n, nominee, category, status in rows]
        return render_template("admin_awards_activity.html", rows=activity,
                               total=total, page=page,
                               pages=max(1, (total + PAGE_SIZE - 1)//PAGE_SIZE))

    @app.get("/admin/awards/results", endpoint="admin_awards_results")
    @admin_required
    def awards_results():
        with ns["SessionLocal"]() as db:
            edition = _edition(db)
            categories = db.query(DCACategory).filter_by(
                edition_id=edition.id).order_by(DCACategory.name.asc()).all()
            # These are nomination support totals, not votes or official winners.
            counts = (db.query(DCANominee.id, func.count(DCANominationSubmission.id))
                      .outerjoin(DCANominationSubmission,
                                 DCANominationSubmission.nominee_id == DCANominee.id)
                      .filter(DCANominee.edition_id == edition.id)
                      .group_by(DCANominee.id).all())
            by_nominee = dict(counts)
            nominees = db.query(DCANominee).filter_by(edition_id=edition.id).all()
            grouped = {}
            for nominee in nominees:
                if nominee.moderation_status != "approved":
                    continue
                grouped.setdefault(nominee.category_id, []).append(dict(
                    name=nominee.name, count=by_nominee.get(nominee.id, 0)))
            summaries = []
            for category in categories:
                eligible = sorted(grouped.get(category.id, []),
                                  key=lambda n: (-n["count"], n["name"].casefold()))
                summaries.append(dict(category=category.name,
                                      status=category.status,
                                      approved_count=len(eligible),
                                      top_five=eligible[:5]))
            phase = edition.phase
        return render_template("admin_awards_results.html",
                               summaries=summaries, phase=phase)

    @app.get("/admin/awards/category-survey", endpoint="admin_awards_category_survey")
    @admin_required
    def category_survey():
        # The original Round 1 review remains intact; this is a navigation
        # alias, not a rewrite of its voting, draft or moderation controls.
        return redirect(url_for("admin_round1"), code=302)
