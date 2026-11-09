"""Dedicated DCA 2026 administrative views.

Current category records and nomination data live separately from the archived
Round 1 category survey. The views never finalize awards or publish results.
"""
from datetime import datetime
import secrets
from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func

from dca_rebuild.models import (
    DCAEdition, DCACategory, DCANominee, DCANominationSubmission,
    DCACategorySuggestionSubmission,
)

SECTIONS = ("overview", "categories", "activity", "results", "history")
PAGE_SIZE = 20


def _page():
    try:
        page = int(request.args.get("page", "1"))
    except (TypeError, ValueError):
        abort(400)
    if page < 1 or page > 10000:
        abort(400)
    return page


def install_dca_admin_workspace(app, ns):
    admin_required = ns["admin_login_required"]

    @app.route("/admin/awards", defaults={"section": "overview"},
               endpoint="admin_dca_workspace")
    @app.route("/admin/awards/<section>", endpoint="admin_dca_workspace_section")
    @admin_required
    def awards_workspace(section="overview"):
        if section not in SECTIONS:
            abort(404)
        page = _page()
        term = (request.args.get("q") or "").strip()[:100]
        with ns["SessionLocal"]() as db:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            if not edition:
                abort(404, "DCA 2026 has not been initialized.")
            categories_query = db.query(DCACategory).filter_by(edition_id=edition.id)
            category_total = categories_query.count()
            official_total = categories_query.filter_by(status="official").count()
            nominee_query = db.query(DCANominee).filter_by(edition_id=edition.id)
            nominee_total = nominee_query.count()
            pending_nominees = nominee_query.filter_by(moderation_status="pending").count()
            nomination_total = db.query(DCANominationSubmission).filter_by(edition_id=edition.id).count()
            survey_total = db.query(DCACategorySuggestionSubmission).filter_by(edition_id=edition.id).count()
            stats = dict(category_total=category_total, official_total=official_total,
                         nominee_total=nominee_total, pending_nominees=pending_nominees,
                         nomination_total=nomination_total, survey_total=survey_total,
                         edition_phase=edition.phase)
            rows, total = [], 0
            if section == "categories":
                query = categories_query
                if term:
                    query = query.filter(DCACategory.name.ilike(
                        "%" + term.replace("%", r"\%").replace("_", r"\_") + "%",
                        escape="\\"))
                total = query.count()
                rows = [dict(id=x.id, name=x.name, description=x.description or "",
                             status=x.status, source=x.source_type)
                        for x in query.order_by(DCACategory.name.asc(),
                                                DCACategory.id.asc()).offset(
                                                    (page-1)*PAGE_SIZE).limit(PAGE_SIZE).all()]
            elif section == "activity":
                query = (db.query(DCANominationSubmission, DCANominee.name, DCACategory.name)
                         .join(DCANominee, DCANominee.id == DCANominationSubmission.nominee_id)
                         .join(DCACategory, DCACategory.id == DCANominee.category_id)
                         .filter(DCANominationSubmission.edition_id == edition.id))
                if term:
                    pattern = "%" + term.replace("%", r"\%").replace("_", r"\_") + "%"
                    query = query.filter(DCANominee.name.ilike(pattern, escape="\\") |
                                         DCACategory.name.ilike(pattern, escape="\\"))
                total = query.count()
                rows = [dict(id=x.id, when=x.submitted_at, nominee=name, category=category,
                             source="Historical import" if x.legacy_submission_id is not None else "Submission")
                        for x, name, category in query.order_by(
                            DCANominationSubmission.submitted_at.desc(),
                            DCANominationSubmission.id.desc()).offset(
                                (page-1)*PAGE_SIZE).limit(PAGE_SIZE).all()]
            elif section == "results":
                query = (db.query(DCACategory.name, DCANominee.name,
                                  DCANominee.moderation_status,
                                  func.count(DCANominationSubmission.id).label("supports"))
                         .join(DCANominee, DCANominee.category_id == DCACategory.id)
                         .outerjoin(DCANominationSubmission,
                                    DCANominationSubmission.nominee_id == DCANominee.id)
                         .filter(DCACategory.edition_id == edition.id,
                                 DCANominee.edition_id == edition.id))
                if term:
                    pattern = "%" + term.replace("%", r"\%").replace("_", r"\_") + "%"
                    query = query.filter(DCACategory.name.ilike(pattern, escape="\\") |
                                         DCANominee.name.ilike(pattern, escape="\\"))
                query = query.group_by(DCACategory.id, DCACategory.name,
                                       DCANominee.id, DCANominee.name,
                                       DCANominee.moderation_status)
                # These are nomination support totals, not votes or final results.
                result_rows = query.order_by(DCACategory.name.asc(),
                                             func.count(DCANominationSubmission.id).desc(),
                                             DCANominee.name.asc()).all()
                total = len(result_rows)
                rows = [dict(category=c, nominee=n, status=status, supports=supports)
                        for c,n,status,supports in result_rows[(page-1)*PAGE_SIZE:page*PAGE_SIZE]]
            else:
                total = 0
        return render_template(
            "admin_dca_workspace.html", section=section, stats=stats,
            rows=rows, total=total, page=page, pages=max(1,(total+PAGE_SIZE-1)//PAGE_SIZE),
            search=term,
        )
