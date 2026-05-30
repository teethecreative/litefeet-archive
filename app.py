import json
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

DB_PATH = Path("litefeet_archive.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    conn.commit()
    conn.close()


@app.template_filter("from_json")
def from_json_filter(value):
    try:
        return json.loads(value or "[]")
    except json.JSONDecodeError:
        return []


def get_submission_title(form_data):
    title = (
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

    return title


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

        submission_type = form_data.get("submission_type", "").strip()
        title = get_submission_title(form_data)

        related_to = form_data.get("related_to", "").strip()
        source_url = form_data.get("source_url", "").strip()
        submitter_name = form_data.get("submitter_name", "").strip()
        submitter_role = form_data.get("submitter_role", "").strip()
        contact = form_data.get("contact", "").strip()

        details_json = json.dumps(get_clean_details(form_data), ensure_ascii=False)
        created_at = datetime.now().isoformat(timespec="seconds")

        conn = get_db_connection()
        conn.execute(
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
                details_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                submission_type,
                title,
                related_to,
                source_url,
                submitter_name,
                submitter_role,
                contact,
                1,
                details_json,
                created_at,
            ),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("submit_success"))

    return render_template("submit.html", errors=[])


@app.route("/submit/success")
def submit_success():
    return render_template("submit_success.html")


@app.route("/events")
def events():
    return render_template("events.html")


@app.route("/dancers")
def dancers():
    return render_template("dancers.html")


@app.route("/battles")
def battles():
    return render_template("battles.html")


@app.route("/awards")
def awards():
    return render_template("awards.html")


@app.route("/verify")
def verify_claims():
    return render_template("verify_claims.html")


@app.route("/ask")
def ask_archive():
    return render_template("ask_archive.html")


@app.route("/admin/submissions")
def admin_submissions():
    conn = get_db_connection()
    submissions = conn.execute(
        "SELECT * FROM submissions ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    return render_template("admin_submissions.html", submissions=submissions)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
