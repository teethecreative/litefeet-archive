from functools import wraps
from datetime import datetime, timedelta
import hashlib
import os
import secrets

from flask import Flask, flash, redirect, render_template, request, url_for, abort, session
from sqlalchemy import create_engine, func, or_
from sqlalchemy.orm import sessionmaker

from dca_rebuild.config import DATABASE_URL
from dca_rebuild.category_metadata import get_category_meta
from dca_rebuild.models import (
    Base,
    DCACategory,
    DCACategorySuggestionSubmission,
    DCANewCategorySuggestion,
    DCAReturnCategoryVote,
    DCAEdition,
    LFAArchiveSubmission,
    LFARecord,
    NewsletterSubscriber,
)

app = Flask(__name__)
app.secret_key = (
    os.environ.get("DCA_SECRET_KEY")
    or os.environ.get("SECRET_KEY")
    or "local-dev-secret"
)

engine = create_engine(DATABASE_URL)


@app.context_processor
def ledger_template_globals():
    return {
        "current_year": datetime.utcnow().year
    }

Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


def private_hash(value):
    salt = (
        os.environ.get("DCA_HASH_SALT")
        or os.environ.get("SECRET_KEY")
        or "local-dev-salt"
    )
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()


def client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


@app.route("/")
def index():
    return render_template("ledger_home.html")

@app.route("/awards/dancers-choice/category-suggestions", methods=["GET", "POST"])
def round1():
    db = SessionLocal()

    try:
        historical = db.query(DCAEdition).filter_by(year=2023).first()
        current = db.query(DCAEdition).filter_by(year=2026).first()

        categories = (
            db.query(DCACategory)
            .filter(DCACategory.edition_id == historical.id)
            .order_by(DCACategory.name.asc())
            .all()
        )

        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()

            if not email or "@" not in email:
                flash("Enter a valid email address.")
                return redirect(url_for("round1"))

            email_hash = private_hash(email)
            ip_hash = private_hash(client_ip())
            now = datetime.utcnow()

            last = (
                db.query(DCACategorySuggestionSubmission)
                .filter(
                    DCACategorySuggestionSubmission.edition_id == current.id,
                    or_(
                        DCACategorySuggestionSubmission.email_hash == email_hash,
                        DCACategorySuggestionSubmission.ip_hash == ip_hash,
                    ),
                )
                .order_by(DCACategorySuggestionSubmission.submitted_at.desc())
                .first()
            )

            if last and now < last.submitted_at + timedelta(hours=24):
                next_allowed = last.submitted_at + timedelta(hours=24)
                remaining = next_allowed - now
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)

                flash(
                    f"You already submitted this round. "
                    f"Try again in {hours}h {minutes}m."
                )
                return redirect(url_for("round1"))

            method = request.form.get("category_count_preference")

            if method not in {"top_25", "threshold", "all"}:
                flash("Choose how you think the final category list should be decided.")
                return redirect(url_for("round1"))
            votes = {}

            for category in categories:
                answer = request.form.get(f"category_{category.id}")

                # Skipping a category means no vote.
                if answer in {"yes", "no"}:
                    votes[category.id] = answer == "yes"
            submission = DCACategorySuggestionSubmission(
                edition_id=current.id,
                email_hash=email_hash,
                ip_hash=ip_hash,
                visitor_key=secrets.token_hex(16),
                submitted_at=now,
                category_count_preference=method,
            )

            db.add(submission)
            db.flush()

            for category_id, answer in votes.items():
                db.add(
                    DCAReturnCategoryVote(
                        submission_id=submission.id,
                        category_id=category_id,
                        bring_back=answer,
                    )
                )

            seen = set()

            for raw in request.form.getlist("new_category"):
                name = " ".join(raw.strip().split())

                if not name:
                    continue

                normalized = name.lower()

                if normalized in seen:
                    continue

                seen.add(normalized)

                db.add(
                    DCANewCategorySuggestion(
                        submission_id=submission.id,
                        category_name=name,
                        normalized_name=normalized,
                    )
                )

            db.commit()
            return render_template("round1_success.html")

        award_categories = []
        suggested_categories = []

        for category in categories:
            meta = get_category_meta(category.name)

            item = {
                "category": category,
                "meta": meta,
            }

            # A category belongs in the official 2023 section only
            # when an official 2023 winner record exists.
            if meta.get("winners"):
                award_categories.append(item)
            else:
                suggested_categories.append(item)

        return render_template(
            "round1.html",
            categories=categories,
            award_categories=award_categories,
            suggested_categories=suggested_categories,
        )

    finally:
        db.close()



# ============================================================
# DCA ROUND 2 — CATEGORY VOTING
# ============================================================

@app.route(
    "/awards/dancers-choice/category-voting",
    methods=["GET", "POST"],
)
def round2():
    db = SessionLocal()

    try:
        historical = (
            db.query(DCAEdition)
            .filter_by(year=2023)
            .first()
        )

        current = (
            db.query(DCAEdition)
            .filter_by(year=2026)
            .first()
        )

        if not historical or not current:
            return render_template(
                "round2.html",
                category_items=[],
                approved_suggestions=[],
                method_results=[],
                round1_submission_count=0,
                round1_winner=None,
                round1_method_tied=False,
            )

        categories = (
            db.query(DCACategory)
            .filter(
                DCACategory.edition_id == historical.id
            )
            .order_by(DCACategory.name.asc())
            .all()
        )

        round1_submission_count = (
            db.query(
                DCACategorySuggestionSubmission
            )
            .filter(
                DCACategorySuggestionSubmission.edition_id
                == current.id
            )
            .count()
        )

        # ----------------------------------------------------
        # RETURNING CATEGORY LIVE RESULTS
        # ----------------------------------------------------

        vote_rows = (
            db.query(
                DCAReturnCategoryVote.category_id,
                DCAReturnCategoryVote.bring_back,
                func.count(
                    DCAReturnCategoryVote.id
                ),
            )
            .join(
                DCACategorySuggestionSubmission,
                DCACategorySuggestionSubmission.id
                == DCAReturnCategoryVote.submission_id,
            )
            .filter(
                DCACategorySuggestionSubmission.edition_id
                == current.id
            )
            .group_by(
                DCAReturnCategoryVote.category_id,
                DCAReturnCategoryVote.bring_back,
            )
            .all()
        )

        vote_map = {}

        for category_id, bring_back, count in vote_rows:
            if category_id not in vote_map:
                vote_map[category_id] = {
                    "keep": 0,
                    "remove": 0,
                }

            if bring_back:
                vote_map[category_id]["keep"] = count
            else:
                vote_map[category_id]["remove"] = count

        category_items = []

        for category in categories:
            counts = vote_map.get(
                category.id,
                {
                    "keep": 0,
                    "remove": 0,
                },
            )

            keep_count = counts["keep"]
            remove_count = counts["remove"]
            total = keep_count + remove_count

            if total:
                keep_percent = round(
                    (keep_count / total) * 100
                )
                remove_percent = 100 - keep_percent
            else:
                keep_percent = 0
                remove_percent = 0

            # We deliberately do NOT assign an elimination
            # threshold here. That rule has not been finalized.
            if total == 0:
                status = "Waiting for community votes"
            elif keep_count > remove_count:
                status = "Currently favored to return"
            elif remove_count > keep_count:
                status = "Currently trailing"
            else:
                status = "Currently tied"

            category_items.append({
                "category": category,
                "meta": get_category_meta(
                    category.name
                ),
                "keep_count": keep_count,
                "remove_count": remove_count,
                "total": total,
                "keep_percent": keep_percent,
                "remove_percent": remove_percent,
                "status": status,
            })

        # Most-supported categories first.
        category_items.sort(
            key=lambda item: (
                -item["keep_percent"],
                -item["keep_count"],
                item["category"].name.lower(),
            )
        )

        # ----------------------------------------------------
        # APPROVED / MODERATED NEW CATEGORY SUGGESTIONS
        # ----------------------------------------------------

        suggestions = (
            db.query(DCANewCategorySuggestion)
            .join(
                DCACategorySuggestionSubmission,
                DCACategorySuggestionSubmission.id
                == DCANewCategorySuggestion.submission_id,
            )
            .filter(
                DCACategorySuggestionSubmission.edition_id
                == current.id,
                DCANewCategorySuggestion.moderation_status.in_(
                    ["approved", "merged"]
                ),
            )
            .order_by(
                DCANewCategorySuggestion.created_at.asc()
            )
            .all()
        )

        suggestion_groups = {}

        for suggestion in suggestions:
            if (
                suggestion.moderation_status == "merged"
                and suggestion.merged_into_id
            ):
                canonical_id = suggestion.merged_into_id
            else:
                canonical_id = suggestion.id

            if canonical_id not in suggestion_groups:
                canonical = (
                    db.query(DCANewCategorySuggestion)
                    .filter_by(id=canonical_id)
                    .first()
                )

                if not canonical:
                    canonical = suggestion

                suggestion_groups[canonical_id] = {
                    "name": canonical.category_name,
                    "count": 0,
                }

            suggestion_groups[canonical_id]["count"] += 1

        approved_suggestions = sorted(
            suggestion_groups.values(),
            key=lambda item: (
                -item["count"],
                item["name"].lower(),
            ),
        )

        # ----------------------------------------------------
        # ROUND 1 CATEGORY-COUNT PREFERENCE
        # ----------------------------------------------------

        raw_method_counts = dict(
            db.query(
                DCACategorySuggestionSubmission
                .category_count_preference,
                func.count(
                    DCACategorySuggestionSubmission.id
                ),
            )
            .filter(
                DCACategorySuggestionSubmission.edition_id
                == current.id
            )
            .group_by(
                DCACategorySuggestionSubmission
                .category_count_preference
            )
            .all()
        )

        method_labels = {
            "top_25": "Top 25",
            "threshold": "Threshold",
            "all": "All Categories",
        }

        method_results = []

        for key in [
            "top_25",
            "threshold",
            "all",
        ]:
            count = raw_method_counts.get(key, 0)

            if round1_submission_count:
                percent = round(
                    count
                    / round1_submission_count
                    * 100
                )
            else:
                percent = 0

            method_results.append({
                "key": key,
                "label": method_labels[key],
                "count": count,
                "percent": percent,
            })

        round1_winner = None
        round1_method_tied = False

        if raw_method_counts:
            highest = max(
                raw_method_counts.values()
            )

            winners = [
                key
                for key, count
                in raw_method_counts.items()
                if count == highest
            ]

            if len(winners) == 1:
                round1_winner = (
                    method_labels[winners[0]]
                )
            else:
                round1_method_tied = True
                round1_winner = (
                    "Currently tied"
                )

        return render_template(
            "round2.html",
            category_items=category_items,
            approved_suggestions=approved_suggestions,
            method_results=method_results,
            round1_submission_count=round1_submission_count,
            round1_winner=round1_winner,
            round1_method_tied=round1_method_tied,
        )

    finally:
        db.close()


# ============================================================
# DCA ROUND 1 ADMIN MODERATION
# ============================================================

@app.route(
    "/admin/dca/round1/suggestion/<int:suggestion_id>",
    methods=["POST"],
)
def moderate_round1_suggestion(suggestion_id):

    db = SessionLocal()

    try:

        suggestion = (
            db.query(DCANewCategorySuggestion)
            .filter_by(id=suggestion_id)
            .first()
        )

        if not suggestion:
            flash("Suggestion not found.")
            return redirect(url_for("admin_round1"))


        decision = request.form.get(
            "decision",
            ""
        ).strip()

        category_name = request.form.get(
            "category_name",
            ""
        ).strip()

        merge_target_id = request.form.get(
            "merge_target_id",
            ""
        ).strip()


        if decision not in {
            "approved",
            "rejected",
            "merged",
        }:
            flash("Choose a moderation decision.")
            return redirect(url_for("admin_round1"))


        if not category_name:
            flash("Category name cannot be empty.")
            return redirect(url_for("admin_round1"))


        suggestion.category_name = category_name

        suggestion.normalized_name = (
            " ".join(
                category_name
                .lower()
                .strip()
                .split()
            )
        )

        suggestion.status = decision


        if decision == "merged":

            if not merge_target_id:
                flash(
                    "Choose the category this suggestion "
                    "should merge into."
                )

                return redirect(
                    url_for("admin_round1")
                )

            suggestion.merge_target_category_id = int(
                merge_target_id
            )

        else:
            suggestion.merge_target_category_id = None


        db.commit()

        flash(
            f'"{category_name}" updated.'
        )

        return redirect(
            url_for("admin_round1")
        )

    finally:
        db.close()


# ============================================================
# DCA ROUND 1 — CURRENT ADMIN DASHBOARD
# ============================================================

def admin_round1_old():

    db = SessionLocal()

    try:
        edition = (
            db.query(DCAEdition)
            .filter_by(year=2026)
            .first()
        )

        historical = (
            db.query(DCAEdition)
            .filter_by(year=2023)
            .first()
        )

        submission_count = (
            db.query(DCACategorySuggestionSubmission)
            .filter(
                DCACategorySuggestionSubmission.edition_id
                == edition.id
            )
            .count()
        )

        threshold = submission_count

        suggestions = (
            db.query(DCANewCategorySuggestion)
            .join(
                DCACategorySuggestionSubmission,
                DCANewCategorySuggestion.submission_id
                == DCACategorySuggestionSubmission.id,
            )
            .filter(
                DCACategorySuggestionSubmission.edition_id
                == edition.id
            )
            .order_by(
                DCANewCategorySuggestion.category_name.asc()
            )
            .all()
        )

        suggestion_count = len(suggestions)

        categories = (
            db.query(DCACategory)
            .filter(
                DCACategory.edition_id == historical.id
            )
            .order_by(DCACategory.name.asc())
            .all()
        )

        return_results = []

        for category in categories:

            yes_count = (
                db.query(DCAReturnCategoryVote)
                .join(
                    DCACategorySuggestionSubmission,
                    DCAReturnCategoryVote.submission_id
                    == DCACategorySuggestionSubmission.id,
                )
                .filter(
                    DCACategorySuggestionSubmission.edition_id
                    == edition.id,
                    DCAReturnCategoryVote.category_id
                    == category.id,
                    DCAReturnCategoryVote.bring_back.is_(True),
                )
                .count()
            )

            no_count = (
                db.query(DCAReturnCategoryVote)
                .join(
                    DCACategorySuggestionSubmission,
                    DCAReturnCategoryVote.submission_id
                    == DCACategorySuggestionSubmission.id,
                )
                .filter(
                    DCACategorySuggestionSubmission.edition_id
                    == edition.id,
                    DCAReturnCategoryVote.category_id
                    == category.id,
                    DCAReturnCategoryVote.bring_back.is_(False),
                )
                .count()
            )

            return_results.append({
                "name": category.name,
                "yes": yes_count,
                "no": no_count,
            })


        method_counts = dict(
            db.query(
                DCACategorySuggestionSubmission.category_count_preference,
                func.count(
                    DCACategorySuggestionSubmission.id
                ),
            )
            .filter(
                DCACategorySuggestionSubmission.edition_id
                == edition.id
            )
            .group_by(
                DCACategorySuggestionSubmission.category_count_preference
            )
            .all()
        )

        method_labels = {
            "top_25": "Top 25",
            "threshold": f"Threshold: {threshold} Votes",
            "all": "All Categories",
        }

        merge_targets = categories

        return render_template(
            "admin_round1.html",
            submission_count=submission_count,
            suggestion_count=suggestion_count,
            threshold=threshold,
            return_results=return_results,
            suggestions=suggestions,
            method_counts=method_counts,
            method_labels=method_labels,
            merge_targets=merge_targets,
        )

    finally:
        db.close()

# ============================================================
# DCA ROUND 1 ADMIN DASHBOARD
# ============================================================



# ============================================================
# LITEFEET LEDGER — ADMIN AUTHENTICATION
# ============================================================

def admin_login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("ledger_admin_authenticated"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped_view


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("ledger_admin_authenticated"):
        return redirect(url_for("admin_round1"))

    error = None

    if request.method == "POST":
        username = (
            request.form.get("username", "")
            .strip()
        )

        password = request.form.get("password", "")

        expected_username = os.environ.get(
            "ADMIN_USERNAME",
            ""
        )

        expected_password = os.environ.get(
            "ADMIN_PASSWORD",
            ""
        )

        username_ok = (
            expected_username
            and secrets.compare_digest(
                username,
                expected_username,
            )
        )

        password_ok = (
            expected_password
            and secrets.compare_digest(
                password,
                expected_password,
            )
        )

        if username_ok and password_ok:
            session.clear()
            session["ledger_admin_authenticated"] = True

            return redirect(
                url_for("admin_round1")
            )

        error = "Invalid username or password."

    return render_template(
        "admin_login.html",
        error=error,
    )


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/round1")
@admin_login_required
def admin_round1():

    db = SessionLocal()

    try:
        edition = (
            db.query(DCAEdition)
            .filter_by(year=2026)
            .first()
        )

        historical = (
            db.query(DCAEdition)
            .filter_by(year=2023)
            .first()
        )

        submission_count = (
            db.query(DCACategorySuggestionSubmission)
            .filter(
                DCACategorySuggestionSubmission.edition_id
                == edition.id
            )
            .count()
        )

        threshold = submission_count

        suggestions = (
            db.query(DCANewCategorySuggestion)
            .join(
                DCACategorySuggestionSubmission,
                DCANewCategorySuggestion.submission_id
                == DCACategorySuggestionSubmission.id,
            )
            .filter(
                DCACategorySuggestionSubmission.edition_id
                == edition.id
            )
            .order_by(
                DCANewCategorySuggestion.category_name.asc()
            )
            .all()
        )

        suggestion_count = len(suggestions)

        categories = (
            db.query(DCACategory)
            .filter(
                DCACategory.edition_id == historical.id
            )
            .order_by(DCACategory.name.asc())
            .all()
        )

        return_results = []

        for category in categories:

            yes_count = (
                db.query(DCAReturnCategoryVote)
                .join(
                    DCACategorySuggestionSubmission,
                    DCAReturnCategoryVote.submission_id
                    == DCACategorySuggestionSubmission.id,
                )
                .filter(
                    DCACategorySuggestionSubmission.edition_id
                    == edition.id,
                    DCAReturnCategoryVote.category_id
                    == category.id,
                    DCAReturnCategoryVote.bring_back.is_(True),
                )
                .count()
            )

            no_count = (
                db.query(DCAReturnCategoryVote)
                .join(
                    DCACategorySuggestionSubmission,
                    DCAReturnCategoryVote.submission_id
                    == DCACategorySuggestionSubmission.id,
                )
                .filter(
                    DCACategorySuggestionSubmission.edition_id
                    == edition.id,
                    DCAReturnCategoryVote.category_id
                    == category.id,
                    DCAReturnCategoryVote.bring_back.is_(False),
                )
                .count()
            )

            return_results.append({
                "name": category.name,
                "yes": yes_count,
                "no": no_count,
            })


        method_counts = dict(
            db.query(
                DCACategorySuggestionSubmission.category_count_preference,
                func.count(
                    DCACategorySuggestionSubmission.id
                ),
            )
            .filter(
                DCACategorySuggestionSubmission.edition_id
                == edition.id
            )
            .group_by(
                DCACategorySuggestionSubmission.category_count_preference
            )
            .all()
        )

        method_labels = {
            "top_25": "Top 25",
            "threshold": f"Threshold: {threshold} Votes",
            "all": "All Categories",
        }

        merge_targets = categories

        return render_template(
            "admin_round1.html",
            submission_count=submission_count,
            suggestion_count=suggestion_count,
            threshold=threshold,
            return_results=return_results,
            suggestions=suggestions,
            method_counts=method_counts,
            method_labels=method_labels,
            merge_targets=merge_targets,
        )

    finally:
        db.close()

# ============================================================
# DCA ROUND 1 — BUILD ROUND 2 BALLOT
# ============================================================

@app.route("/admin/round1/build-round2", methods=["POST"])
@admin_login_required
def build_round2_ballot():

    db = SessionLocal()

    try:
        current = db.query(DCAEdition).filter_by(year=2026).first()
        historical = db.query(DCAEdition).filter_by(year=2023).first()

        if not current or not historical:
            flash("DCA editions are missing.")
            return redirect(url_for("admin_round1"))

        # ----------------------------------------------------
        # Get or create the 2026 Round 2 ballot
        # ----------------------------------------------------

        ballot = (
            db.query(DCACategoryBallot)
            .filter(
                DCACategoryBallot.edition_id == current.id
            )
            .first()
        )

        if not ballot:
            ballot = DCACategoryBallot(
                edition_id=current.id,
                is_open=False,
            )
            db.add(ballot)
            db.flush()

        # ----------------------------------------------------
        # Determine Round 1 preliminary method winner
        # ----------------------------------------------------

        method_counts = dict(
            db.query(
                DCACategorySuggestionSubmission.category_count_preference,
                func.count(DCACategorySuggestionSubmission.id),
            )
            .filter(
                DCACategorySuggestionSubmission.edition_id == current.id
            )
            .group_by(
                DCACategorySuggestionSubmission.category_count_preference
            )
            .all()
        )

        ballot.round_one_winning_method = None

        if method_counts:
            highest = max(method_counts.values())

            winners = [
                method
                for method, count in method_counts.items()
                if count == highest
            ]

            if len(winners) == 1:
                ballot.round_one_winning_method = winners[0]

        # Threshold = completed Round 1 submissions.
        ballot.threshold_number = (
            db.query(DCACategorySuggestionSubmission)
            .filter(
                DCACategorySuggestionSubmission.edition_id == current.id
            )
            .count()
        )

        # ----------------------------------------------------
        # Create 2026 category copies for the Round 2 ballot
        # ----------------------------------------------------

        historical_categories = (
            db.query(DCACategory)
            .filter(
                DCACategory.edition_id == historical.id
            )
            .order_by(DCACategory.name.asc())
            .all()
        )

        added = 0

        for source in historical_categories:

            existing = (
                db.query(DCACategory)
                .filter(
                    DCACategory.edition_id == current.id,
                    DCACategory.normalized_name == source.normalized_name,
                )
                .first()
            )

            if not existing:
                existing = DCACategory(
                    edition_id=current.id,
                    name=source.name,
                    normalized_name=source.normalized_name,
                    description=source.description,
                    source_type="returning",
                    source_category_id=source.id,
                    status="round2_ballot",
                )

                db.add(existing)
                added += 1
            else:
                existing.status = "round2_ballot"

        # ----------------------------------------------------
        # Add APPROVED new Round 1 suggestions
        # ----------------------------------------------------

        approved = (
            db.query(DCANewCategorySuggestion)
            .join(
                DCACategorySuggestionSubmission,
                DCANewCategorySuggestion.submission_id
                == DCACategorySuggestionSubmission.id,
            )
            .filter(
                DCACategorySuggestionSubmission.edition_id == current.id,
                DCANewCategorySuggestion.status == "approved",
            )
            .all()
        )

        for suggestion in approved:

            existing = (
                db.query(DCACategory)
                .filter(
                    DCACategory.edition_id == current.id,
                    DCACategory.normalized_name
                    == suggestion.normalized_name,
                )
                .first()
            )

            if not existing:
                db.add(
                    DCACategory(
                        edition_id=current.id,
                        name=suggestion.category_name,
                        normalized_name=suggestion.normalized_name,
                        source_type="new",
                        status="round2_ballot",
                    )
                )
                added += 1
            else:
                existing.status = "round2_ballot"

        db.commit()

        flash(
            f"Round 2 ballot built. "
            f"{added} new ballot records created."
        )

        return redirect(url_for("admin_round1"))

    finally:
        db.close()

# ============================================================
# AWARDS LANDING PAGES
# ============================================================

@app.route("/awards")
def awards_home():
    return redirect(url_for("dca_2026_home"))


@app.route("/awards/dancers-choice/2026")
def dca_2026_home():
    return render_template(
        "award_landing.html",
        page_title="Dancer's Choice Awards 2026",
        eyebrow="DANCER'S CHOICE AWARDS",
        title="2026",
        subtitle="The current Dancer's Choice Awards cycle.",
        page_type="dca-2026",
    )


@app.route("/awards/dancers-choice/2023")
def dca_2023_home():
    return render_template(
        "award_landing.html",
        page_title="Dancer's Choice Awards 2023",
        eyebrow="DANCER'S CHOICE AWARDS",
        title="2023",
        subtitle="Historical awards archive.",
        page_type="dca-2023",
    )


@app.route("/awards/litefeet-awards/<int:year>")
def lfa_year(year):

    allowed_years = {2023, 2024, 2025, 2026}

    if year not in allowed_years:
        abort(404)

    return render_template(
        "award_landing.html",
        page_title=f"Litefeet Awards {year}",
        eyebrow="LITEFEET AWARDS",
        title=str(year),
        subtitle="Litefeet Awards winner archive.",
        page_type="lfa",
        year=year,
    )

# ============================================================
# LITEFEET AWARDS
# ============================================================

@app.route("/awards/litefeet-awards")
def lfa_home():
    return render_template("lfa_home.html")


@app.route(
    "/awards/litefeet-awards/submit",
    methods=["POST"]
)
def lfa_submit():
    db = SessionLocal()

    try:
        allowed_types = {
            "nomination",
            "award_winner",
            "hall_of_fame",
            "litefeet_achievement",
            "litefeet_humanitarian",
        }

        submission_type = (
            request.form.get("submission_type") or ""
        ).strip()

        year_raw = (
            request.form.get("year") or ""
        ).strip()

        category_name = (
            request.form.get("category_name") or ""
        ).strip()

        winner_name = (
            request.form.get("winner_name") or ""
        ).strip()

        team_name = (
            request.form.get("team_name") or ""
        ).strip()

        submitter_email = (
            request.form.get("submitter_email") or ""
        ).strip().lower()

        if submission_type not in allowed_types:
            flash("Choose what type of LiteFeet Awards information you're submitting.")
            return redirect(
                url_for("lfa_home") + "#contribute"
            )

        try:
            year = int(year_raw)
        except ValueError:
            year = 0

        if year not in {2023, 2024, 2025, 2026}:
            flash("Choose a year.")
            return redirect(
                url_for("lfa_home") + "#contribute"
            )

        if not category_name:
            flash("Enter the category or honor.")
            return redirect(
                url_for("lfa_home") + "#contribute"
            )

        if not winner_name:
            flash("Enter the person, winner, or honoree.")
            return redirect(
                url_for("lfa_home") + "#contribute"
            )

        submission = LFAArchiveSubmission(
            year=year,
            submission_type=submission_type,
            category_name=category_name,
            winner_name=winner_name,
            team_name=team_name or None,
            additional_details=None,
            source_information=None,
            submitter_email=submitter_email or None,
            status="pending",
        )

        db.add(submission)
        db.commit()

        return render_template(
            "lfa_submission_success.html"
        )

    finally:
        db.close()



# ============================================================
# LITEFEET AWARDS — ADMIN
# ============================================================

@app.route("/admin/lfa/submissions")
@admin_login_required
def admin_lfa_submissions():
    db = SessionLocal()

    try:
        submissions = (
            db.query(LFAArchiveSubmission)
            .order_by(
                LFAArchiveSubmission.created_at.desc()
            )
            .all()
        )

        return render_template(
            "admin_lfa_submissions.html",
            submissions=submissions,
        )

    finally:
        db.close()


@app.route(
    "/admin/lfa/submissions/<int:submission_id>/approve",
    methods=["POST"]
)
@admin_login_required
def admin_lfa_approve(submission_id):
    db = SessionLocal()

    try:
        submission = db.get(
            LFAArchiveSubmission,
            submission_id
        )

        if not submission:
            abort(404)

        if submission.status == "approved":
            flash("This submission is already approved.")
            return redirect(
                url_for("admin_lfa_submissions")
            )

        record = LFARecord(
            year=submission.year,
            record_type=submission.submission_type,
            category_name=submission.category_name,
            person_name=submission.winner_name,
            team_name=submission.team_name,
            additional_details=submission.additional_details,
            source_information=submission.source_information,
            source_submission_id=submission.id,
        )

        db.add(record)

        submission.status = "approved"

        db.commit()

        flash("LFA submission approved.")

        return redirect(
            url_for("admin_lfa_submissions")
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@app.route(
    "/admin/lfa/submissions/<int:submission_id>/reject",
    methods=["POST"]
)
@admin_login_required
def admin_lfa_reject(submission_id):
    db = SessionLocal()

    try:
        submission = db.get(
            LFAArchiveSubmission,
            submission_id
        )

        if not submission:
            abort(404)

        if submission.status == "approved":
            flash(
                "Approved records cannot be rejected "
                "from the submission queue."
            )

            return redirect(
                url_for("admin_lfa_submissions")
            )

        submission.status = "rejected"

        db.commit()

        flash("LFA submission rejected.")

        return redirect(
            url_for("admin_lfa_submissions")
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@app.route(
    "/admin/lfa/submissions/<int:submission_id>/edit-approve",
    methods=["GET", "POST"]
)
@admin_login_required
def admin_lfa_edit_approve(submission_id):
    db = SessionLocal()

    try:
        submission = db.get(
            LFAArchiveSubmission,
            submission_id
        )

        if not submission:
            abort(404)

        if request.method == "POST":
            year_raw = (
                request.form.get("year") or ""
            ).strip()

            record_type = (
                request.form.get("record_type") or ""
            ).strip()

            category_name = (
                request.form.get("category_name") or ""
            ).strip()

            person_name = (
                request.form.get("person_name") or ""
            ).strip()

            team_name = (
                request.form.get("team_name") or ""
            ).strip()

            additional_details = (
                request.form.get("additional_details") or ""
            ).strip()

            source_information = (
                request.form.get("source_information") or ""
            ).strip()

            allowed_types = {
                "nomination",
                "award_winner",
                "hall_of_fame",
                "litefeet_achievement",
                "litefeet_humanitarian",
            }

            try:
                year = int(year_raw)
            except ValueError:
                year = 0

            if year not in {2023, 2024, 2025, 2026}:
                flash("Choose a valid year.")

                return redirect(
                    url_for(
                        "admin_lfa_edit_approve",
                        submission_id=submission.id,
                    )
                )

            if record_type not in allowed_types:
                flash("Choose a valid record type.")

                return redirect(
                    url_for(
                        "admin_lfa_edit_approve",
                        submission_id=submission.id,
                    )
                )

            if not category_name or not person_name:
                flash(
                    "Category/Honor and Person are required."
                )

                return redirect(
                    url_for(
                        "admin_lfa_edit_approve",
                        submission_id=submission.id,
                    )
                )

            record = LFARecord(
                year=year,
                record_type=record_type,
                category_name=category_name,
                person_name=person_name,
                team_name=team_name or None,
                additional_details=(
                    additional_details or None
                ),
                source_information=(
                    source_information or None
                ),
                source_submission_id=submission.id,
            )

            db.add(record)

            submission.status = "approved"

            db.commit()

            flash(
                "LFA submission edited and approved."
            )

            return redirect(
                url_for("admin_lfa_submissions")
            )

        return render_template(
            "admin_lfa_edit_submission.html",
            submission=submission,
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()



@app.route(
    "/admin/lfa/records/new",
    methods=["GET", "POST"]
)
@admin_login_required
def admin_lfa_new_record():
    db = SessionLocal()

    try:
        if request.method == "POST":
            year_raw = (
                request.form.get("year") or ""
            ).strip()

            record_type = (
                request.form.get("record_type") or ""
            ).strip()

            category_name = (
                request.form.get("category_name") or ""
            ).strip()

            person_name = (
                request.form.get("person_name") or ""
            ).strip()

            team_name = (
                request.form.get("team_name") or ""
            ).strip()

            additional_details = (
                request.form.get("additional_details") or ""
            ).strip()

            source_information = (
                request.form.get("source_information") or ""
            ).strip()

            allowed_types = {
                "nomination",
                "award_winner",
                "hall_of_fame",
                "litefeet_achievement",
                "litefeet_humanitarian",
            }

            try:
                year = int(year_raw)
            except ValueError:
                year = 0

            if year not in {2023, 2024, 2025, 2026}:
                flash("Choose a valid year.")
                return redirect(
                    url_for("admin_lfa_new_record")
                )

            if record_type not in allowed_types:
                flash("Choose a valid record type.")
                return redirect(
                    url_for("admin_lfa_new_record")
                )

            if not category_name or not person_name:
                flash(
                    "Category/Honor and Person are required."
                )
                return redirect(
                    url_for("admin_lfa_new_record")
                )

            record = LFARecord(
                year=year,
                record_type=record_type,
                category_name=category_name,
                person_name=person_name,
                team_name=team_name or None,
                additional_details=additional_details or None,
                source_information=source_information or None,
                source_submission_id=None,
            )

            db.add(record)
            db.commit()

            flash("Verified LFA record created.")

            return redirect(
                url_for("admin_lfa_records")
            )

        return render_template(
            "admin_lfa_record_form.html",
            record=None,
            form_title="ADD VERIFIED RECORD",
            submit_label="CREATE RECORD →",
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@app.route(
    "/admin/lfa/records/<int:record_id>/edit",
    methods=["GET", "POST"]
)
@admin_login_required
def admin_lfa_edit_record(record_id):
    db = SessionLocal()

    try:
        record = db.get(
            LFARecord,
            record_id
        )

        if not record:
            abort(404)

        if request.method == "POST":
            year_raw = (
                request.form.get("year") or ""
            ).strip()

            record_type = (
                request.form.get("record_type") or ""
            ).strip()

            category_name = (
                request.form.get("category_name") or ""
            ).strip()

            person_name = (
                request.form.get("person_name") or ""
            ).strip()

            team_name = (
                request.form.get("team_name") or ""
            ).strip()

            additional_details = (
                request.form.get("additional_details") or ""
            ).strip()

            source_information = (
                request.form.get("source_information") or ""
            ).strip()

            allowed_types = {
                "nomination",
                "award_winner",
                "hall_of_fame",
                "litefeet_achievement",
                "litefeet_humanitarian",
            }

            try:
                year = int(year_raw)
            except ValueError:
                year = 0

            if year not in {2023, 2024, 2025, 2026}:
                flash("Choose a valid year.")
                return redirect(
                    url_for(
                        "admin_lfa_edit_record",
                        record_id=record.id
                    )
                )

            if record_type not in allowed_types:
                flash("Choose a valid record type.")
                return redirect(
                    url_for(
                        "admin_lfa_edit_record",
                        record_id=record.id
                    )
                )

            if not category_name or not person_name:
                flash(
                    "Category/Honor and Person are required."
                )
                return redirect(
                    url_for(
                        "admin_lfa_edit_record",
                        record_id=record.id
                    )
                )

            record.year = year
            record.record_type = record_type
            record.category_name = category_name
            record.person_name = person_name
            record.team_name = team_name or None
            record.additional_details = (
                additional_details or None
            )
            record.source_information = (
                source_information or None
            )

            db.commit()

            flash("Verified LFA record updated.")

            return redirect(
                url_for("admin_lfa_records")
            )

        return render_template(
            "admin_lfa_record_form.html",
            record=record,
            form_title="EDIT VERIFIED RECORD",
            submit_label="SAVE CHANGES →",
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@app.route("/admin/lfa/records")
@admin_login_required
def admin_lfa_records():
    db = SessionLocal()

    try:
        records = (
            db.query(LFARecord)
            .order_by(
                LFARecord.year.desc(),
                LFARecord.created_at.desc(),
            )
            .all()
        )

        return render_template(
            "admin_lfa_records.html",
            records=records,
        )

    finally:
        db.close()


@app.route("/awards/hypeitup")
def hypeitup_awards():
    return render_template("hypeitup_awards.html")






# ============================================================
# LITEFEET LEDGER — NEWSLETTER SIGNUP
# ============================================================

@app.route("/newsletter/subscribe", methods=["POST"])
def newsletter_subscribe():
    email = (
        request.form.get("email", "")
        .strip()
        .lower()
    )

    if (
        not email
        or "@" not in email
        or "." not in email.rsplit("@", 1)[-1]
        or len(email) > 255
    ):
        return {
            "ok": False,
            "message": "Enter a valid email address."
        }, 400

    db = SessionLocal()

    try:
        subscriber = (
            db.query(NewsletterSubscriber)
            .filter(
                func.lower(
                    NewsletterSubscriber.email
                ) == email
            )
            .first()
        )

        if subscriber:
            if subscriber.is_active:
                return {
                    "ok": True,
                    "message": "You're already subscribed."
                }

            subscriber.is_active = True
            subscriber.unsubscribed_at = None
            subscriber.subscribed_at = datetime.utcnow()

            db.commit()

            return {
                "ok": True,
                "message": "You're subscribed again."
            }

        subscriber = NewsletterSubscriber(
            email=email,
            is_active=True
        )

        db.add(subscriber)
        db.commit()

        return {
            "ok": True,
            "message": "You're on the list."
        }

    except Exception:
        db.rollback()

        return {
            "ok": False,
            "message": (
                "We couldn't save that email right now. "
                "Please try again."
            )
        }, 500

    finally:
        db.close()

# ============================================================
# LITEFEET LEDGER — SHORT PUBLIC URLS
# ============================================================

@app.route("/dca")
@app.route("/dca/2026")
def short_dca_home():
    return redirect(
        url_for("dca_2026_home"),
        code=302,
    )


@app.route("/dca/2026/categories")
def short_dca_categories():
    return redirect(
        url_for("round1"),
        code=302,
    )


@app.route("/dca/2023")
def short_dca_2023():
    return redirect(
        url_for("dca_2023_home"),
        code=302,
    )


@app.route("/litefeet-awards")
def short_litefeet_awards():
    return redirect(
        url_for("lfa_home"),
        code=302,
    )


@app.route("/hypeitup-awards")
def short_hypeitup_awards():
    return redirect(
        url_for("hypeitup_awards"),
        code=302,
    )


# ============================================================
# LITEFEET LEDGER — LEGACY ARCHIVE URL COMPATIBILITY
# ============================================================

LEGACY_HOME_ROUTES = [
    "/about",
    "/contributor",
    "/event-affiliates",
    "/submit",
    "/submit/success",
    "/submit/start",
    "/calendar",
    "/events",
    "/dancers",
    "/people",
    "/people/dancers",
    "/people/dancers/create",
    "/people-teams",
    "/people-and-teams",
    "/people/producers",
    "/people/teams",
    "/producers",
    "/teams",
    "/battles",
    "/ledger-review",
    "/verify",
    "/ask",
    "/community-perspectives",
    "/litefeet-music",
    "/releases/submit",
]


def legacy_archive_redirect():
    return redirect(url_for("index"), code=302)


for legacy_route in LEGACY_HOME_ROUTES:

    # Do not overwrite a route that the rebuild
    # already owns.
    existing = {
        rule.rule
        for rule in app.url_map.iter_rules()
    }

    if legacy_route not in existing:
        endpoint = (
            "legacy_"
            + legacy_route
                .strip("/")
                .replace("/", "_")
                .replace("-", "_")
        )

        app.add_url_rule(
            legacy_route,
            endpoint,
            legacy_archive_redirect,
            methods=["GET"],
        )


@app.route("/dancers/<path:legacy_path>")
@app.route("/people/<path:legacy_path>")
@app.route("/events/<path:legacy_path>")
@app.route("/teams/<path:legacy_path>")
@app.route("/battles/<path:legacy_path>")
@app.route("/litefeet-music/<path:legacy_path>")
@app.route("/music/<path:legacy_path>")
@app.route("/verify/<path:legacy_path>")
@app.route("/ask/<path:legacy_path>")
def legacy_archive_detail_redirect(legacy_path):
    return redirect(url_for("index"), code=302)


if __name__ == "__main__":
    app.run(debug=True, port=5001)



# ============================================================
# DCA ROUND 1 — CURRENT ADMIN DASHBOARD
# ============================================================
