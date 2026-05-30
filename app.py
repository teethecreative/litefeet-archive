import json
import os
from datetime import datetime

from flask import Flask, Response, redirect, render_template, request, url_for
from sqlalchemy import create_engine, text

app = Flask(__name__)


def get_database_url():
    database_url = os.environ.get("DATABASE_URL", "").strip()

    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+pg8000://", 1)
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+pg8000://", 1)

        return database_url

    return "sqlite:///litefeet_archive.db"


engine = create_engine(get_database_url(), future=True)


def check_admin_auth(username, password):
    expected_username = os.environ.get("ADMIN_USERNAME", "")
    expected_password = os.environ.get("ADMIN_PASSWORD", "")

    if not expected_username or not expected_password:
        return False

    return username == expected_username and password == expected_password


def admin_auth_required():
    return Response(
        "Admin access requires a username and password.",
        401,
        {"WWW-Authenticate": 'Basic realm="LiteFeet Archive Admin"'},
    )


@app.before_request
def protect_admin_routes():
    if request.path.startswith("/admin"):
        auth = request.authorization

        if not auth or not check_admin_auth(auth.username, auth.password):
            return admin_auth_required()


@app.template_filter("from_json")
def from_json_filter(value):
    try:
        return json.loads(value or "[]")
    except json.JSONDecodeError:
        return []


def init_db():
    dialect = engine.dialect.name

    if dialect == "postgresql":
        submission_id = "id SERIAL PRIMARY KEY"
        vote_id = "id SERIAL PRIMARY KEY"
    else:
        submission_id = "id INTEGER PRIMARY KEY AUTOINCREMENT"
        vote_id = "id INTEGER PRIMARY KEY AUTOINCREMENT"

    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS submissions (
                    {submission_id},
                    submission_type TEXT,
                    title TEXT,
                    related_to TEXT,
                    source_url TEXT,
                    submitter_name TEXT,
                    submitter_role TEXT,
                    contact TEXT,
                    needs_verification INTEGER DEFAULT 1,
                    review_status TEXT DEFAULT 'Pending Review',
                    details_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
        )

        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS verification_votes (
                    {vote_id},
                    submission_id INTEGER NOT NULL,
                    vote_type TEXT NOT NULL,
                    voter_name TEXT,
                    voter_role TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
        )


def fetch_all(query, params=None):
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        return result.mappings().all()


def execute_query(query, params=None):
    with engine.begin() as conn:
        conn.execute(text(query), params or {})


def get_submission_title(form_data):
    return (
        form_data.get("event_title")
        or form_data.get("source_title")
        or form_data.get("battle_event")
        or form_data.get("dancer_name")
        or form_data.get("award_category")
        or form_data.get("correction_target")
        or form_data.get("claim_text")
        or form_data.get("move_name")
        or form_data.get("host_name")
        or form_data.get("other_details")
        or ""
    ).strip()


def get_clean_details(form_data):
    labels = {
        "event_title": "Event Name",
        "event_date": "Event Date",
        "event_location": "Event Location",
        "event_host": "Event Host",
        "event_details": "Event Details",
        "battle_event": "Battle Event",
        "battle_date": "Battle Date",
        "dancer_one": "Dancer 1",
        "dancer_two": "Dancer 2",
        "winner": "Winner",
        "battle_context": "Battle Context",
        "dancer_name": "Dancer Name / Alias",
        "crew": "Crew / Affiliation",
        "location": "Location / Scene",
        "known_for": "Known For",
        "award_year": "Award Year",
        "award_category": "Award Category",
        "award_winner": "Award Winner",
        "award_context": "Award Context",
        "source_title": "Source Title",
        "source_context": "Source Context",
        "source_platform": "Source Platform",
        "correction_target": "Correction Target",
        "current_info": "Current Info",
        "corrected_info": "Corrected Info",
        "claim_text": "Claim Text",
        "claim_confidence": "Claim Confidence",
        "move_name": "Move / Style Name",
        "move_origin": "Move Origin / Context",
        "move_example": "Move Example Link",
        "host_name": "Host / Organization Name",
        "host_social": "Host Social / Website",
        "host_request": "Host Request",
        "other_details": "Other Details",
    }

    clean_details = []

    for key, label in labels.items():
        value = form_data.get(key, "").strip()
        if value:
            clean_details.append({"label": label, "value": value})

    return clean_details


def validate_submission(form_data):
    errors = []
    submission_type = form_data.get("submission_type", "").strip()
    title = get_submission_title(form_data)

    if not submission_type:
        errors.append("Choose what kind of archive info you are sharing.")

    if len(title) < 2:
        errors.append("Add at least one clear detail for this submission.")

    return errors


def get_vote_counts_for_submissions(submissions):
    vote_rows = fetch_all(
        """
        SELECT submission_id, vote_type, COUNT(*) AS total
        FROM verification_votes
        GROUP BY submission_id, vote_type
        """
    )

    vote_counts = {}

    for submission in submissions:
        vote_counts[submission["id"]] = {
            "true": 0,
            "false": 0,
            "debatable": 0,
        }

    for row in vote_rows:
        submission_id = row["submission_id"]
        vote_type = row["vote_type"]

        if submission_id in vote_counts:
            vote_counts[submission_id][vote_type] = row["total"]

    return vote_counts


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/submit", methods=["GET", "POST"])
def submit_info():
    if request.method == "POST":
        form_data = request.form.to_dict()
        errors = validate_submission(form_data)

        if errors:
            return render_template("submit.html", errors=errors), 400

        execute_query(
            """
            INSERT INTO submissions (
                submission_type,
                title,
                related_to,
                source_url,
                submitter_name,
                submitter_role,
                contact,
                needs_verification,
                review_status,
                details_json,
                created_at
            )
            VALUES (
                :submission_type,
                :title,
                :related_to,
                :source_url,
                :submitter_name,
                :submitter_role,
                :contact,
                :needs_verification,
                :review_status,
                :details_json,
                :created_at
            )
            """,
            {
                "submission_type": form_data.get("submission_type", "").strip(),
                "title": get_submission_title(form_data),
                "related_to": form_data.get("related_to", "").strip(),
                "source_url": form_data.get("source_url", "").strip(),
                "submitter_name": form_data.get("submitter_name", "").strip(),
                "submitter_role": form_data.get("submitter_role", "").strip(),
                "contact": form_data.get("contact", "").strip(),
                "needs_verification": 1,
                "review_status": "Pending Review",
                "details_json": json.dumps(get_clean_details(form_data), ensure_ascii=False),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

        return redirect(url_for("submit_success"))

    return render_template("submit.html", errors=[])


@app.route("/submit/success")
def submit_success():
    return render_template("submit_success.html")


@app.route("/events")
def events():
    approved_events = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE submission_type = 'event'
        AND review_status IN ('Verified', 'Community Supported')
        ORDER BY created_at DESC
        """
    )

    return render_template("events.html", approved_events=approved_events)


@app.route("/dancers")
def dancers():
    approved_dancers = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE submission_type = 'dancer_profile'
        AND review_status IN ('Verified', 'Community Supported')
        ORDER BY created_at DESC
        """
    )

    return render_template("dancers.html", approved_dancers=approved_dancers)


@app.route("/battles")
def battles():
    approved_battles = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE submission_type = 'battle_result'
        AND review_status IN ('Verified', 'Community Supported')
        ORDER BY created_at DESC
        """
    )

    return render_template("battles.html", approved_battles=approved_battles)


@app.route("/awards")
def awards():
    approved_awards = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE submission_type = 'award_info'
        AND review_status IN ('Verified', 'Community Supported')
        ORDER BY created_at DESC
        """
    )

    return render_template("awards.html", approved_awards=approved_awards)


@app.route("/verify")
def verify_claims():
    submissions = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE review_status IN ('Pending Review', 'Needs Verification', 'Community Supported', 'Disputed')
        ORDER BY created_at DESC
        """
    )

    return render_template(
        "verify_claims.html",
        submissions=submissions,
        vote_counts=get_vote_counts_for_submissions(submissions),
    )


@app.route("/verify/<int:submission_id>/vote", methods=["POST"])
def vote_on_claim(submission_id):
    vote_type = request.form.get("vote_type", "").strip()
    voter_name = request.form.get("voter_name", "").strip()
    voter_role = request.form.get("voter_role", "").strip()
    note = request.form.get("note", "").strip()

    if vote_type not in {"true", "false", "debatable"}:
        return redirect(url_for("verify_claims"))

    execute_query(
        """
        INSERT INTO verification_votes (
            submission_id,
            vote_type,
            voter_name,
            voter_role,
            note,
            created_at
        )
        VALUES (
            :submission_id,
            :vote_type,
            :voter_name,
            :voter_role,
            :note,
            :created_at
        )
        """,
        {
            "submission_id": submission_id,
            "vote_type": vote_type,
            "voter_name": voter_name,
            "voter_role": voter_role,
            "note": note,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
    )

    return redirect(url_for("verify_claims"))


@app.route("/ask")
def ask_archive():
    return render_template("ask_archive.html")


@app.route("/admin/submissions")
def admin_submissions():
    submissions = fetch_all(
        """
        SELECT *
        FROM submissions
        ORDER BY created_at DESC
        """
    )

    return render_template("admin_submissions.html", submissions=submissions)


@app.route("/admin/submissions/<int:submission_id>/status", methods=["POST"])
def update_submission_status(submission_id):
    new_status = request.form.get("review_status", "").strip()

    allowed_statuses = {
        "Pending Review",
        "Needs Verification",
        "Community Supported",
        "Verified",
        "Disputed",
        "Rejected",
    }

    if new_status not in allowed_statuses:
        return redirect(url_for("admin_submissions"))

    execute_query(
        """
        UPDATE submissions
        SET review_status = :review_status
        WHERE id = :submission_id
        """,
        {
            "review_status": new_status,
            "submission_id": submission_id,
        },
    )

    return redirect(url_for("admin_submissions"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
