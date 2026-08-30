from datetime import datetime, timedelta
import hashlib
import os
import secrets

from flask import Flask, flash, redirect, render_template, request, url_for, abort
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
)

app = Flask(__name__)
app.secret_key = os.environ.get("DCA_SECRET_KEY", "local-dev-secret")

engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


def private_hash(value):
    salt = os.environ.get("DCA_HASH_SALT", "local-dev-salt")
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

                if answer not in {"yes", "no"}:
                    flash("Vote Yes or No on every old category.")
                    return redirect(url_for("round1"))

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

        categories = (
            db.query(DCACategory)
            .filter(
                DCACategory.edition_id == historical.id
            )
            .order_by(DCACategory.name.asc())
            .all()
        )


        category_items = []

        for category in categories:

            category_items.append({
                "category": category,
                "meta": get_category_meta(
                    category.name
                ),
            })


        # Threshold is based on completed Round 1 submissions.
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

        threshold = round1_submission_count


        # Determine preliminary Round 1 method winner.
        method_counts = dict(
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


        labels = {
            "top_25": "Top 25",
            "threshold": f"Threshold: {threshold} Votes",
            "all": "All Categories",
        }


        round1_winner_key = None
        round1_winner = None
        round1_method_tied = False

        if method_counts:

            highest = max(method_counts.values())

            winners = [
                key
                for key, value in method_counts.items()
                if value == highest
            ]

            if len(winners) == 1:
                round1_winner_key = winners[0]
                round1_winner = labels[round1_winner_key]
            else:
                round1_method_tied = True
                round1_winner = "Tied Preliminary Vote"


        # Round 2 final-method ballot:
        #
        # Top 25 wins Round 1:
        #   Top 25 / Threshold / All
        #
        # Threshold wins Round 1:
        #   Threshold / All
        #
        # All wins Round 1:
        #   All / Threshold
        #
        # If Round 1 is tied or has no submissions yet,
        # admin preview shows all three but the result
        # remains unresolved.
        if round1_winner_key == "threshold":
            final_method_options = [
                "threshold",
                "all",
            ]

        elif round1_winner_key == "all":
            final_method_options = [
                "all",
                "threshold",
            ]

        else:
            final_method_options = [
                "top_25",
                "threshold",
                "all",
            ]


        # Round 2 remains preview-only until we deliberately
        # finalize Round 1 and create the official ballot.
        preview = True


        if request.method == "POST":

            flash(
                "Round 2 is not open yet."
            )

            return redirect(
                url_for("round2")
            )


        return render_template(
            "round2.html",
            category_items=category_items,
            threshold=threshold,
            round1_winner=round1_winner,
            round1_method_tied=round1_method_tied,
            final_method_options=final_method_options,
            preview=preview,
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


@app.route("/admin/round1")
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

        try:
            year = int(year_raw)
        except ValueError:
            year = 0

        if year not in {2023, 2024, 2025, 2026}:
            flash("Choose an award year.")
            return redirect(
                url_for("lfa_home") + "#contribute"
            )

        if not category_name:
            flash("Enter the award category.")
            return redirect(
                url_for("lfa_home") + "#contribute"
            )

        if not winner_name:
            flash("Enter the winner.")
            return redirect(
                url_for("lfa_home") + "#contribute"
            )

        submission = LFAArchiveSubmission(
            year=year,
            submission_type="award_information",
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


@app.route("/awards/hypeitup")
def hypeitup_awards():
    return render_template("hypeitup_awards.html")




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
