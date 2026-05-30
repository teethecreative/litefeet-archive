import json
import os
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for
from sqlalchemy import create_engine, text

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-this-secret")


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


@app.before_request
def protect_admin_routes():
    if request.path.startswith("/admin") and request.path not in {"/admin/login"}:
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login", next=request.path))


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
                    contact TEXT,
                    source_url TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
        )

        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE verification_votes ADD COLUMN IF NOT EXISTS contact TEXT"))
            conn.execute(text("ALTER TABLE verification_votes ADD COLUMN IF NOT EXISTS source_url TEXT"))
        else:
            existing_vote_columns = {
                row[1] for row in conn.execute(text("PRAGMA table_info(verification_votes)")).fetchall()
            }

            if "contact" not in existing_vote_columns:
                conn.execute(text("ALTER TABLE verification_votes ADD COLUMN contact TEXT"))

            if "source_url" not in existing_vote_columns:
                conn.execute(text("ALTER TABLE verification_votes ADD COLUMN source_url TEXT"))



def fetch_all(query, params=None):
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        return result.mappings().all()


def execute_query(query, params=None):
    with engine.begin() as conn:
        conn.execute(text(query), params or {})


def check_admin_login(username, password):
    expected_username = os.environ.get("ADMIN_USERNAME", "").strip()
    expected_password = os.environ.get("ADMIN_PASSWORD", "").strip()

    if not expected_username or not expected_password:
        return False

    return username == expected_username and password == expected_password


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
        "event_org": "Organization Name",
        "event_name": "Event Name",
        "event_date": "Event Date",
        "event_time": "Event Time",
        "event_location": "Event Location",
        "event_host": "Event Host",
        "event_battle_type": "Battle Type",
        "event_battle_list": "Battle List",
        "event_judges": "Judges",
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


def seed_litefeet_research_records():
    try:
        from litefeet_seed_data import LITEFEET_RESEARCH_RECORDS
    except ImportError:
        return

    execute_query(
        "DELETE FROM submissions WHERE title = :title",
        {"title": "Shoe Tricks / Hat Tricks"},
    )

    for record in LITEFEET_RESEARCH_RECORDS:
        existing = fetch_all(
            "SELECT id FROM submissions WHERE title = :title LIMIT 1",
            {"title": record["title"]},
        )

        if existing:
            continue

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
                "submission_type": record["submission_type"],
                "title": record["title"],
                "related_to": record.get("related_to", ""),
                "source_url": record.get("source_url", ""),
                "submitter_name": "LiteFeet Archive",
                "submitter_role": "Archive Research Seed",
                "contact": "",
                "needs_verification": 1,
                "review_status": record["review_status"],
                "details_json": json.dumps(
                    [
                        {"label": label, "value": value}
                        for label, value in record.get("details", [])
                        if value
                    ],
                    ensure_ascii=False,
                ),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )



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



@app.route("/events/submit", methods=["GET", "POST"])
def submit_event():
    if request.method == "POST":
        form_data = request.form.to_dict()

        errors = []

        event_org = form_data.get("event_org", "").strip()
        event_name = form_data.get("event_name", "").strip()
        event_date = form_data.get("event_date", "").strip()
        event_time = form_data.get("event_time", "").strip()
        event_location = form_data.get("event_location", "").strip()

        if len(event_org) < 2:
            errors.append("Add the organization or host name.")

        if len(event_name) < 2:
            errors.append("Add the event name.")

        if not event_date:
            errors.append("Add the event date.")

        if not event_time:
            errors.append("Add the event time.")

        if len(event_location) < 2:
            errors.append("Add the event location.")

        if errors:
            return render_template("event_submit.html", errors=errors), 400

        details = [
            {"label": "Organization Name", "value": event_org},
            {"label": "Event Name", "value": event_name},
            {"label": "Event Date", "value": event_date},
            {"label": "Event Time", "value": event_time},
            {"label": "Event Location", "value": event_location},
            {"label": "Battle Type", "value": form_data.get("event_battle_type", "").strip()},
            {"label": "Battle List", "value": form_data.get("event_battle_list", "").strip()},
            {"label": "Judges", "value": form_data.get("event_judges", "").strip()},
            {"label": "Event Details", "value": form_data.get("event_details", "").strip()},
        ]

        details = [item for item in details if item["value"]]

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
                "submission_type": "event",
                "title": event_name,
                "related_to": event_org,
                "source_url": form_data.get("source_url", "").strip(),
                "submitter_name": form_data.get("submitter_name", "").strip(),
                "submitter_role": form_data.get("submitter_role", "").strip(),
                "contact": form_data.get("contact", "").strip(),
                "needs_verification": 1,
                "review_status": "Pending Review",
                "details_json": json.dumps(details, ensure_ascii=False),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

        return redirect(url_for("submit_success"))

    return render_template("event_submit.html", errors=[])


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
        WHERE review_status IN ('Needs Verification', 'Disputed')
        ORDER BY created_at DESC
        """
    )

    return render_template(
        "verify_claims.html",
        submissions=submissions,
        vote_counts=get_vote_counts_for_submissions(submissions),
    )


@app.route("/verify/<int:submission_id>")
def verify_claim_detail(submission_id):
    submissions = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE id = :submission_id
        LIMIT 1
        """,
        {"submission_id": submission_id},
    )

    if not submissions:
        return redirect(url_for("verify_claims"))

    submission = submissions[0]
    vote_counts = get_vote_counts_for_submissions([submission])

    return render_template(
        "verify_claim_detail.html",
        submission=submission,
        counts=vote_counts.get(submission_id, {"true": 0, "false": 0, "debatable": 0}),
    )


@app.route("/verify/<int:submission_id>/vote", methods=["POST"])
def vote_on_claim(submission_id):
    vote_type = request.form.get("vote_type", "").strip()
    voter_name = request.form.get("voter_name", "").strip()
    voter_role = request.form.get("voter_role", "").strip()
    contact = request.form.get("contact", "").strip()
    source_url = request.form.get("source_url", "").strip()
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
            contact,
            source_url,
            note,
            created_at
        )
        VALUES (
            :submission_id,
            :vote_type,
            :voter_name,
            :voter_role,
            :contact,
            :source_url,
            :note,
            :created_at
        )
        """,
        {
            "submission_id": submission_id,
            "vote_type": vote_type,
            "voter_name": voter_name,
            "voter_role": voter_role,
            "contact": contact,
            "source_url": source_url,
            "note": note,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
    )

    return redirect(url_for("verify_claim_detail", submission_id=submission_id))


@app.route("/ask")
def ask_archive():
    return render_template("ask_archive.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    next_url = request.args.get("next") or url_for("admin_submissions")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        next_url = request.form.get("next_url") or url_for("admin_submissions")

        if check_admin_login(username, password):
            session["admin_logged_in"] = True
            session["admin_username"] = username
            return redirect(next_url)

        error = "That login did not work. Check the admin username and password."

    return render_template("admin_login.html", error=error, next_url=next_url)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


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
seed_litefeet_research_records()

if __name__ == "__main__":
    app.run(debug=True)
