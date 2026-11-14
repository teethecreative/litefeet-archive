"""Focused editorial review queue for 2026 category suggestions.

This is separate from the historical Round 1 selection draft, public
category ballots, and currently official 2026 categories. No review action
publishes or deletes community submissions.
"""
from datetime import datetime
import secrets

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func

from dca_rebuild.category_merge_suggestions import suggest_merge_targets

from dca_rebuild.models import (
    DCAEdition, DCACategory, DCACategorySuggestionSubmission,
    DCANewCategorySuggestion, DCAReturnCategoryVote,
    DCAReturningCategoryReview,
)

PAGE_SIZE = 10
STATUSES = ("pending", "approved", "rejected", "merged")


def _require_token():
    expected = session.get("dca_moderation_csrf", "")
    provided = request.form.get("csrf_token", "")
    if not expected or not secrets.compare_digest(str(expected), str(provided)):
        abort(400, description="Invalid moderation token")


def _label_key(source, category_id):
    return f"{source}:{category_id}"


def _edition_pair(db):
    current = db.query(DCAEdition).filter_by(year=2026).first()
    historical = db.query(DCAEdition).filter_by(year=2023).first()
    if current is None or historical is None:
        abort(404, description="Awards editions have not been initialized.")
    return current, historical


def _rows(db, current, historical):
    review_map = {
        r.category_id: r
        for r in db.query(DCAReturningCategoryReview).filter_by(
            edition_id=current.id
        ).all()
    }
    votes = (
        db.query(DCAReturnCategoryVote.category_id,
                 DCAReturnCategoryVote.bring_back,
                 func.count(DCAReturnCategoryVote.id))
        .join(DCACategorySuggestionSubmission,
              DCAReturnCategoryVote.submission_id ==
              DCACategorySuggestionSubmission.id)
        .filter(DCACategorySuggestionSubmission.edition_id == current.id)
        .group_by(DCAReturnCategoryVote.category_id,
                  DCAReturnCategoryVote.bring_back).all()
    )
    returning_votes = {}
    for category_id, yes, count in votes:
        returning_votes.setdefault(category_id, {"yes": 0, "no": 0})[
            "yes" if yes else "no"
        ] = count

    rows = []
    for category in db.query(DCACategory).filter_by(
        edition_id=historical.id
    ).all():
        review = review_map.get(category.id)
        name = (review.name_override if review and review.name_override
                else category.name)
        description = (review.description_override
                       if review and review.description_override is not None
                       else category.description) or ""
        totals = returning_votes.get(category.id, {"yes": 0, "no": 0})
        rows.append(dict(
            key=_label_key("returning", category.id),
            id=category.id, source="returning", name=name,
            description=description, status=review.status if review else "pending",
            yes=totals["yes"], no=totals["no"],
            merged_into_key=review.merged_into_key if review else None,
        ))

    suggestions = (
        db.query(DCANewCategorySuggestion)
        .join(DCACategorySuggestionSubmission,
              DCANewCategorySuggestion.submission_id ==
              DCACategorySuggestionSubmission.id)
        .filter(DCACategorySuggestionSubmission.edition_id == current.id)
        .all()
    )
    for item in suggestions:
        rows.append(dict(
            key=_label_key("new", item.id), id=item.id, source="new",
            name=item.category_name, description=item.description or "",
            status=item.moderation_status if item.moderation_status in STATUSES
                   else "pending",
            yes=None, no=None,
            merged_into_key=(_label_key("new", item.merged_into_id)
                             if item.merged_into_id else None),
        ))
    return sorted(rows, key=lambda x: (x["name"].casefold(), x["key"]))


def install_category_review_queue(app, ns):
    admin_required = ns["admin_login_required"]

    @app.get("/admin/round1", endpoint="admin_round1")
    @admin_required
    def category_review():
        status = (request.args.get("status") or "pending").lower()
        if status not in ("all",) + STATUSES:
            abort(400)
        missing_only = request.args.get("missing") == "1"
        merge_only = request.args.get("merges") == "1"
        term = (request.args.get("q") or "").strip().casefold()[:100]
        try:
            page = int(request.args.get("page", "1"))
        except (TypeError, ValueError):
            abort(400)
        if page < 1 or page > 10000:
            abort(400)

        with ns["SessionLocal"]() as db:
            current, historical = _edition_pair(db)
            all_rows = _rows(db, current, historical)
        for row in all_rows:
            row["suggested_merges"] = suggest_merge_targets(row, all_rows)
        counts = {
            key: sum(row["status"] == key for row in all_rows)
            for key in STATUSES
        }
        selected_rows = [
            row for row in all_rows
            if (status == "all" or row["status"] == status)
            and (not missing_only or not row["description"].strip())
            and (not merge_only or row["suggested_merges"])
            and (not term or term in (
                row["name"] + " " + row["description"] + " " + row["key"]
            ).casefold())
        ]
        total = len(selected_rows)
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages)
        start = (page - 1) * PAGE_SIZE
        return render_template(
            "admin_category_review.html", rows=selected_rows[start:start+PAGE_SIZE],
            all_rows=all_rows, counts=counts, total=total,
            page=page, pages=pages, status=status, missing_only=missing_only,
            merge_only=merge_only,
            merge_suggestion_count=sum(bool(x["suggested_merges"]) for x in all_rows
                                       if x["status"] in ("pending", "approved")),
            query=request.args.get("q", "")[:100], total_categories=len(all_rows),
            missing_count=sum(not x["description"].strip() for x in all_rows
                              if x["status"] == "pending"),
        )

    @app.post("/admin/round1/review/<source>/<int:category_id>",
              endpoint="admin_category_review_decision")
    @admin_required
    def category_decision(source, category_id):
        _require_token()
        if source not in ("new", "returning"):
            abort(404)
        action = (request.form.get("decision") or "").strip().lower()
        if action not in ("save",) + STATUSES:
            abort(400, description="Invalid review decision.")
        if action == "pending":
            action = "pending"  # Reopen an earlier decision.
        name = " ".join((request.form.get("category_name") or "").split())
        description = " ".join((request.form.get("category_description") or "").split())
        if not name or len(name) > 250 or len(description) > 500:
            abort(400, description="Name and description exceed allowed limits.")
        if action == "approved" and not description:
            abort(400, description="Add a description before approving the category.")
        merged_into_key = (request.form.get("merge_target_key") or "").strip()
        if action == "merged" and not merged_into_key:
            abort(400, description="Choose a category to merge into.")

        with ns["SessionLocal"].begin() as db:
            current, historical = _edition_pair(db)
            rows = _rows(db, current, historical)
            current_key = _label_key(source, category_id)
            record = next((row for row in rows if row["key"] == current_key), None)
            if record is None:
                abort(404)
            target = None
            if action == "merged":
                target = next((row for row in rows
                               if row["key"] == merged_into_key), None)
                if (target is None or target["key"] == current_key
                        or target["status"] in ("rejected", "merged")):
                    abort(400, description="Choose an active, different category.")
                # The existing suggestion model stores a foreign key only to
                # another NEW suggestion, not a returning 2023 category.
                if source == "new" and target["source"] != "new":
                    abort(400, description="New suggestions can merge into other new suggestions only.")
            if source == "returning":
                category = db.get(DCACategory, category_id)
                if category is None or category.edition_id != historical.id:
                    abort(404)
                review = db.query(DCAReturningCategoryReview).filter_by(
                    edition_id=current.id, category_id=category.id
                ).first()
                if review is None:
                    review = DCAReturningCategoryReview(
                        edition_id=current.id, category_id=category.id)
                    db.add(review)
                review.name_override = name if name != category.name else None
                review.description_override = description
                if action != "save":
                    review.status = action
                    review.merged_into_key = (
                        merged_into_key if action == "merged" else None
                    )
                review.updated_at = datetime.utcnow()
            else:
                suggestion = db.get(DCANewCategorySuggestion, category_id)
                if (suggestion is None
                        or suggestion.submission.edition_id != current.id):
                    abort(404)
                suggestion.category_name = name
                suggestion.normalized_name = " ".join(name.casefold().split())
                suggestion.description = description or None
                if action != "save":
                    suggestion.moderation_status = action
                    suggestion.merged_into_id = (target["id"]
                        if action == "merged" else None)
        flash(f'"{name}" saved. The historical survey remains unchanged.')
        # All completed decisions disappear from the default pending list.
        return redirect(url_for("admin_round1") + "#category-list", code=303)
