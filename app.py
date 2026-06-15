import json
import os
import re
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for
from sqlalchemy import create_engine, text
from werkzeug.security import check_password_hash, generate_password_hash
from markupsafe import Markup, escape

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



@app.template_filter("detail_value")
def detail_value_filter(details_json, label):
    details = from_json_filter(details_json or "[]")

    for item in details:
        if item.get("label") == label:
            return item.get("value", "")

    return ""


def ensure_person_role_columns():
    dialect = engine.dialect.name

    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN IF NOT EXISTS role_tags TEXT"))
        else:
            existing_columns = {
                row[1] for row in conn.execute(text("PRAGMA table_info(dancer_profiles)")).fetchall()
            }

            if "role_tags" not in existing_columns:
                conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN role_tags TEXT"))

        conn.execute(
            text(
                """
                UPDATE dancer_profiles
                SET role_tags = 'Dancer'
                WHERE role_tags IS NULL OR TRIM(role_tags) = ''
                """
            )
        )

    ensure_profile_slug_column()




def make_profile_slug(name):
    slug = re.sub(r"[^a-z0-9]+", "", (name or "").lower())

    if not slug:
        slug = "profile"

    return slug


def unique_profile_slug(name, current_profile_id=None):
    base_slug = make_profile_slug(name)
    slug = base_slug
    counter = 2

    while True:
        params = {"slug": slug}

        if current_profile_id:
            params["current_profile_id"] = current_profile_id
            existing = fetch_all(
                """
                SELECT id
                FROM dancer_profiles
                WHERE profile_slug = :slug
                AND id != :current_profile_id
                LIMIT 1
                """,
                params,
            )
        else:
            existing = fetch_all(
                """
                SELECT id
                FROM dancer_profiles
                WHERE profile_slug = :slug
                LIMIT 1
                """,
                params,
            )

        if not existing:
            return slug

        slug = f"{base_slug}{counter}"
        counter += 1


def ensure_profile_slug_column():
    dialect = engine.dialect.name

    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN IF NOT EXISTS profile_slug TEXT"))
        else:
            existing_columns = {
                row[1] for row in conn.execute(text("PRAGMA table_info(dancer_profiles)")).fetchall()
            }

            if "profile_slug" not in existing_columns:
                conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN profile_slug TEXT"))

    profiles = fetch_all(
        """
        SELECT id, dance_name, profile_slug
        FROM dancer_profiles
        ORDER BY id ASC
        """
    )

    for profile in profiles:
        expected_slug = make_profile_slug(profile["dance_name"])

        if not profile["profile_slug"]:
            expected_slug = unique_profile_slug(profile["dance_name"], profile["id"])

            execute_query(
                """
                UPDATE dancer_profiles
                SET profile_slug = :profile_slug
                WHERE id = :profile_id
                """,
                {
                    "profile_slug": expected_slug,
                    "profile_id": profile["id"],
                },
            )


def profile_url(profile):
    slug = profile.get("profile_slug") if hasattr(profile, "get") else profile["profile_slug"]

    if not slug:
        slug = make_profile_slug(profile.get("dance_name", "") if hasattr(profile, "get") else profile["dance_name"])

    return f"/dancers/{slug}"




def make_public_slug(value):
    slug = re.sub(r"[^A-Za-z0-9]+", "", value or "")
    return slug or "Record"


def normalize_public_slug(value):
    return make_public_slug(value).lower()


def get_detail_value(details_json, label):
    details = from_json_filter(details_json or "[]")

    for item in details:
        if item.get("label") == label:
            return item.get("value", "")

    return ""


def event_organizer_name(event):
    return (
        get_detail_value(event["details_json"], "Organizer")
        or get_detail_value(event["details_json"], "Event Host")
        or get_detail_value(event["details_json"], "Organization Name")
        or "Organizer"
    )


def event_public_url(event):
    organizer_slug = make_public_slug(event_organizer_name(event))
    event_slug = make_public_slug(event["title"])
    return f"/{organizer_slug}/{event_slug}"


@app.template_filter("event_public_url")
def event_public_url_filter(event):
    return event_public_url(event)


@app.template_filter("public_slug")
def public_slug_filter(value):
    return make_public_slug(value)


@app.template_filter("profile_url")
def profile_url_filter(profile):
    return profile_url(profile)


def role_tags_to_list(role_tags):
    return [
        role.strip()
        for role in (role_tags or "").split(",")
        if role.strip()
    ]


@app.template_filter("role_list")
def role_list_filter(role_tags):
    return role_tags_to_list(role_tags)


@app.template_filter("people_links")
def people_links_filter(value):
    text_value = str(value or "").strip()

    if not text_value:
        return ""

    ensure_person_role_columns()

    profiles = fetch_all(
        """
        SELECT id, dance_name, profile_slug
        FROM dancer_profiles
        WHERE dance_name IS NOT NULL
        AND TRIM(dance_name) != ''
        AND status IN (
            'Approved',
            'Verified',
            'Community Supported',
            'Needs Verification',
            'Ghost Profile'
        )
        ORDER BY LENGTH(dance_name) DESC
        """
    )

    rendered = str(escape(text_value))

    for profile in profiles:
        name = profile["dance_name"]

        if not name:
            continue

        escaped_name = str(escape(name))
        href = profile_url(profile)
        replacement = f'<a class="person-link" href="{href}">{escaped_name}</a>'

        rendered = re.sub(
            rf"(?<![\w@]){re.escape(escaped_name)}(?![\w@])",
            replacement,
            rendered,
            flags=re.IGNORECASE,
        )

    return Markup(rendered)


def ensure_portal_tables():
    dialect = engine.dialect.name

    if dialect == "postgresql":
        request_id = "id SERIAL PRIMARY KEY"
    else:
        request_id = "id INTEGER PRIMARY KEY AUTOINCREMENT"

    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS role_requests (
                    {request_id},
                    user_id INTEGER NOT NULL,
                    requested_role TEXT NOT NULL,
                    reason TEXT,
                    status TEXT DEFAULT 'Pending Review',
                    created_at TEXT NOT NULL
                )
                """
            )
        )

        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS contributor_user_id INTEGER"))
            conn.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS anonymous_submission INTEGER DEFAULT 0"))
        else:
            existing_columns = {
                row[1] for row in conn.execute(text("PRAGMA table_info(submissions)")).fetchall()
            }

            if "contributor_user_id" not in existing_columns:
                conn.execute(text("ALTER TABLE submissions ADD COLUMN contributor_user_id INTEGER"))

            if "anonymous_submission" not in existing_columns:
                conn.execute(text("ALTER TABLE submissions ADD COLUMN anonymous_submission INTEGER DEFAULT 0"))


@app.context_processor
def inject_logged_in_user():
    return {"logged_in_user": current_user()}


def get_contribution_points(user_id):
    submission_count = fetch_all(
        """
        SELECT COUNT(*) AS total
        FROM submissions
        WHERE contributor_user_id = :user_id
        """,
        {"user_id": user_id},
    )[0]["total"]

    profile_count = fetch_all(
        """
        SELECT COUNT(*) AS total
        FROM dancer_profiles
        WHERE user_id = :user_id
        """,
        {"user_id": user_id},
    )[0]["total"]

    return {
        "submission_count": submission_count,
        "profile_count": profile_count,
        "points": (submission_count * 5) + (profile_count * 10),
    }


def create_role_request(user_id, requested_role, reason):
    existing = fetch_all(
        """
        SELECT id
        FROM role_requests
        WHERE user_id = :user_id
        AND requested_role = :requested_role
        AND status = 'Pending Review'
        LIMIT 1
        """,
        {
            "user_id": user_id,
            "requested_role": requested_role,
        },
    )

    if existing:
        return

    execute_query(
        """
        INSERT INTO role_requests (
            user_id,
            requested_role,
            reason,
            status,
            created_at
        )
        VALUES (
            :user_id,
            :requested_role,
            :reason,
            :status,
            :created_at
        )
        """,
        {
            "user_id": user_id,
            "requested_role": requested_role,
            "reason": reason,
            "status": "Pending Review",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
    )


@app.route("/contributor")
def contributor_portal():
    user = current_user()

    if not user:
        return render_template(
            "portal_gate.html",
            portal_title="Contributor Portal",
            portal_body="Log in or create an account to track your submissions, contribution points, role requests, and Ledger activity.",
        )

    contribution_summary = get_contribution_points(user["id"])

    requests = fetch_all(
        """
        SELECT *
        FROM role_requests
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        """,
        {"user_id": user["id"]},
    )

    contributions = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE contributor_user_id = :user_id
        ORDER BY created_at DESC
        """,
        {"user_id": user["id"]},
    )

    return render_template(
        "contributor_portal.html",
        user=user,
        contribution_summary=contribution_summary,
        requests=requests,
        contributions=contributions,
    )


@app.route("/contributor/request-role", methods=["POST"])
def contributor_request_role():
    user = current_user()

    if not user:
        return redirect(url_for("account_login"))

    requested_role = request.form.get("requested_role", "").strip()
    reason = request.form.get("reason", "").strip()

    allowed_roles = {"affiliate_host", "admin"}

    if requested_role in allowed_roles:
        create_role_request(user["id"], requested_role, reason)

    return redirect(url_for("contributor_portal"))


@app.route("/event-affiliates")
def event_affiliates_portal():
    user = current_user()

    if not user:
        return render_template(
            "portal_gate.html",
            portal_title="Event Affiliates",
            portal_body="Log in or create an account to request Event Affiliate access. Approved affiliates will be able to submit and manage their own events.",
        )

    if user["role"] not in {"affiliate_host", "admin"}:
        requests = fetch_all(
            """
            SELECT *
            FROM role_requests
            WHERE user_id = :user_id
            AND requested_role = 'affiliate_host'
            ORDER BY created_at DESC
            """,
            {"user_id": user["id"]},
        )

        return render_template(
            "event_affiliate_request.html",
            user=user,
            requests=requests,
        )

    events = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE submission_type = 'event'
        AND contributor_user_id = :user_id
        ORDER BY created_at DESC
        """,
        {"user_id": user["id"]},
    )

    return render_template(
        "event_affiliate_portal.html",
        user=user,
        events=events,
    )


@app.route("/admin/role-requests")
def admin_role_requests():
    requests = fetch_all(
        """
        SELECT role_requests.*, archive_users.display_name, archive_users.email, archive_users.role
        FROM role_requests
        JOIN archive_users ON role_requests.user_id = archive_users.id
        ORDER BY role_requests.created_at DESC
        """
    )

    return render_template("admin_role_requests.html", requests=requests)


@app.route("/admin/role-requests/<int:request_id>/status", methods=["POST"])
def update_role_request_status(request_id):
    new_status = request.form.get("status", "").strip()

    allowed_statuses = {"Pending Review", "Approved", "Rejected"}

    if new_status not in allowed_statuses:
        return redirect(url_for("admin_role_requests"))

    role_requests = fetch_all(
        """
        SELECT *
        FROM role_requests
        WHERE id = :request_id
        LIMIT 1
        """,
        {"request_id": request_id},
    )

    if not role_requests:
        return redirect(url_for("admin_role_requests"))

    role_request = role_requests[0]

    execute_query(
        """
        UPDATE role_requests
        SET status = :status
        WHERE id = :request_id
        """,
        {
            "status": new_status,
            "request_id": request_id,
        },
    )

    if new_status == "Approved":
        execute_query(
            """
            UPDATE archive_users
            SET role = :role
            WHERE id = :user_id
            """,
            {
                "role": role_request["requested_role"],
                "user_id": role_request["user_id"],
            },
        )

    return redirect(url_for("admin_role_requests"))


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



        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS archive_users (
                    {vote_id},
                    display_name TEXT,
                    email TEXT UNIQUE,
                    password_hash TEXT,
                    role TEXT DEFAULT 'contributor',
                    organization_name TEXT,
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


def check_admin_login(username, password):
    expected_username = os.environ.get("ADMIN_USERNAME", "").strip()
    expected_password = os.environ.get("ADMIN_PASSWORD", "").strip()

    if not expected_username or not expected_password:
        return False

    return username == expected_username and password == expected_password



def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    users = fetch_all(
        "SELECT * FROM archive_users WHERE id = :user_id LIMIT 1",
        {"user_id": user_id},
    )

    return users[0] if users else None


def current_user_is_affiliate_host():
    user = current_user()
    return bool(user and user["role"] in {"affiliate_host", "admin"})


def current_user_is_admin():
    user = current_user()
    return bool(user and user["role"] == "admin")

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
        errors.append("Choose what kind of ledger info you are sharing.")

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
                "submitter_name": "LiteFeet Ledger",
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




def get_detail_value(record_or_details_json, label):
    if isinstance(record_or_details_json, str):
        details = from_json_filter(record_or_details_json or "[]")
    elif hasattr(record_or_details_json, "get"):
        details = from_json_filter(record_or_details_json.get("details_json", "[]"))
    else:
        details = []

    for item in details:
        if item.get("label") == label:
            return item.get("value", "")

    return ""


def event_sort_date(record):
    date_value = get_detail_value(record, "Event Date")

    try:
        return datetime.fromisoformat(date_value).date()
    except ValueError:
        return None


def split_event_records(records):
    today = datetime.now().date()
    two_weeks_from_now = today.replace() + __import__("datetime").timedelta(days=14)

    upcoming_soon = []
    upcoming_later = []
    past_events = []
    undated_events = []

    for record in records:
        event_date = event_sort_date(record)

        if not event_date:
            undated_events.append(record)
        elif today <= event_date <= two_weeks_from_now:
            upcoming_soon.append(record)
        elif event_date > two_weeks_from_now:
            upcoming_later.append(record)
        else:
            past_events.append(record)

    upcoming_soon.sort(key=lambda record: event_sort_date(record) or today)
    upcoming_later.sort(key=lambda record: event_sort_date(record) or today)
    past_events.sort(key=lambda record: event_sort_date(record) or today, reverse=True)

    return upcoming_soon, upcoming_later, past_events, undated_events


def ensure_dancer_tables():
    dialect = engine.dialect.name

    if dialect == "postgresql":
        profile_id = "id SERIAL PRIMARY KEY"
        suggestion_id = "id SERIAL PRIMARY KEY"
        flower_id = "id SERIAL PRIMARY KEY"
    else:
        profile_id = "id INTEGER PRIMARY KEY AUTOINCREMENT"
        suggestion_id = "id INTEGER PRIMARY KEY AUTOINCREMENT"
        flower_id = "id INTEGER PRIMARY KEY AUTOINCREMENT"

    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS dancer_profiles (
                    {profile_id},
                    user_id INTEGER,
                    dance_name TEXT NOT NULL,
                    real_name TEXT,
                    team_affiliation TEXT,
                    borough_scene TEXT,
                    bio TEXT,
                    source_url TEXT,
                    status TEXT DEFAULT 'Pending Review',
                    created_at TEXT NOT NULL
                )
                """
            )
        )

        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS dancer_suggestions (
                    {suggestion_id},
                    dancer_profile_id INTEGER NOT NULL,
                    suggestion_text TEXT NOT NULL,
                    source_url TEXT,
                    submitter_name TEXT,
                    submitter_role TEXT,
                    contact TEXT,
                    status TEXT DEFAULT 'Pending Review',
                    created_at TEXT NOT NULL
                )
                """
            )
        )

        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS dancer_flowers (
                    {flower_id},
                    dancer_profile_id INTEGER NOT NULL,
                    flower_text TEXT NOT NULL,
                    submitter_name TEXT,
                    submitter_role TEXT,
                    contact TEXT,
                    status TEXT DEFAULT 'Pending Review',
                    created_at TEXT NOT NULL
                )
                """
            )
        )



@app.route("/admin")
def admin_home():
    return redirect(url_for("admin_submissions"))


@app.route("/admin/submissions/new", methods=["GET", "POST"])
def admin_submission_new():
    allowed_statuses = [
        "Pending Review",
        "Needs Verification",
        "Community Supported",
        "Verified",
        "Disputed",
        "Rejected",
    ]

    allowed_types = [
        "event",
        "battle_result",
        "historical_claim",
        "award_info",
        "dancer_profile",
        "move_info",
        "source_link",
        "host_affiliation",
    ]

    if request.method == "POST":
        submission_type = request.form.get("submission_type", "").strip()
        title = request.form.get("title", "").strip()
        related_to = request.form.get("related_to", "").strip()
        source_url = request.form.get("source_url", "").strip()
        review_status = request.form.get("review_status", "").strip()
        submitter_name = request.form.get("submitter_name", "").strip() or "LiteFeet Ledger Admin"
        submitter_role = request.form.get("submitter_role", "").strip() or "Admin"
        contact = request.form.get("contact", "").strip()

        if submission_type not in allowed_types:
            submission_type = "historical_claim"

        if review_status not in allowed_statuses:
            review_status = "Pending Review"

        labels = request.form.getlist("detail_label")
        values = request.form.getlist("detail_value")

        details = []

        for label, value in zip(labels, values):
            label = label.strip()
            value = value.strip()

            if label or value:
                details.append({"label": label, "value": value})

        if title:
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
                    "submission_type": submission_type,
                    "title": title,
                    "related_to": related_to,
                    "source_url": source_url,
                    "submitter_name": submitter_name,
                    "submitter_role": submitter_role,
                    "contact": contact,
                    "needs_verification": 1,
                    "review_status": review_status,
                    "details_json": json.dumps(details, ensure_ascii=False),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            )

        return redirect(url_for("admin_submissions"))

    return render_template(
        "admin_submission_edit.html",
        submission=None,
        details=[],
        allowed_statuses=allowed_statuses,
        allowed_types=allowed_types,
        mode="new",
    )


@app.route("/admin/submissions/<int:submission_id>/edit", methods=["GET", "POST"])
def admin_submission_edit(submission_id):
    allowed_statuses = [
        "Pending Review",
        "Needs Verification",
        "Community Supported",
        "Verified",
        "Disputed",
        "Rejected",
    ]

    allowed_types = [
        "event",
        "battle_result",
        "historical_claim",
        "award_info",
        "dancer_profile",
        "move_info",
        "source_link",
        "host_affiliation",
    ]

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
        return redirect(url_for("admin_submissions"))

    submission = submissions[0]

    if request.method == "POST":
        submission_type = request.form.get("submission_type", "").strip()
        title = request.form.get("title", "").strip()
        related_to = request.form.get("related_to", "").strip()
        source_url = request.form.get("source_url", "").strip()
        review_status = request.form.get("review_status", "").strip()
        submitter_name = request.form.get("submitter_name", "").strip()
        submitter_role = request.form.get("submitter_role", "").strip()
        contact = request.form.get("contact", "").strip()

        if submission_type not in allowed_types:
            submission_type = submission["submission_type"]

        if review_status not in allowed_statuses:
            review_status = submission["review_status"]

        labels = request.form.getlist("detail_label")
        values = request.form.getlist("detail_value")

        details = []

        for label, value in zip(labels, values):
            label = label.strip()
            value = value.strip()

            if label or value:
                details.append({"label": label, "value": value})

        execute_query(
            """
            UPDATE submissions
            SET submission_type = :submission_type,
                title = :title,
                related_to = :related_to,
                source_url = :source_url,
                submitter_name = :submitter_name,
                submitter_role = :submitter_role,
                contact = :contact,
                review_status = :review_status,
                details_json = :details_json
            WHERE id = :submission_id
            """,
            {
                "submission_type": submission_type,
                "title": title or submission["title"],
                "related_to": related_to,
                "source_url": source_url,
                "submitter_name": submitter_name,
                "submitter_role": submitter_role,
                "contact": contact,
                "review_status": review_status,
                "details_json": json.dumps(details, ensure_ascii=False),
                "submission_id": submission_id,
            },
        )

        updated = fetch_all(
            """
            SELECT *
            FROM submissions
            WHERE id = :submission_id
            LIMIT 1
            """,
            {"submission_id": submission_id},
        )[0]

        if updated["submission_type"] == "event":
            return redirect(event_public_url(updated))

        return redirect(url_for("admin_submissions"))

    return render_template(
        "admin_submission_edit.html",
        submission=submission,
        details=from_json_filter(submission["details_json"]),
        allowed_statuses=allowed_statuses,
        allowed_types=allowed_types,
        mode="edit",
    )


@app.route("/admin/people/<int:dancer_id>/edit", methods=["GET", "POST"])
def admin_person_edit(dancer_id):
    ensure_person_role_columns()
    ensure_profile_slug_column()

    allowed_statuses = [
        "Pending Review",
        "Approved",
        "Verified",
        "Community Supported",
        "Needs Verification",
        "Rejected",
        "Ghost Profile",
    ]

    profiles = fetch_all(
        """
        SELECT *
        FROM dancer_profiles
        WHERE id = :dancer_id
        LIMIT 1
        """,
        {"dancer_id": dancer_id},
    )

    if not profiles:
        return redirect(url_for("dancers"))

    profile = profiles[0]

    if request.method == "POST":
        dance_name = request.form.get("dance_name", "").strip()
        role_tags = request.form.get("role_tags", "").strip()
        team_affiliation = request.form.get("team_affiliation", "").strip()
        borough_scene = request.form.get("borough_scene", "").strip()
        bio = request.form.get("bio", "").strip()
        source_url = request.form.get("source_url", "").strip()
        status = request.form.get("status", "").strip()

        if status not in allowed_statuses:
            status = profile["status"]

        if not dance_name:
            dance_name = profile["dance_name"]

        profile_slug = unique_profile_slug(dance_name, dancer_id)

        execute_query(
            """
            UPDATE dancer_profiles
            SET dance_name = :dance_name,
                profile_slug = :profile_slug,
                role_tags = :role_tags,
                team_affiliation = :team_affiliation,
                borough_scene = :borough_scene,
                bio = :bio,
                source_url = :source_url,
                status = :status
            WHERE id = :dancer_id
            """,
            {
                "dance_name": dance_name,
                "profile_slug": profile_slug,
                "role_tags": role_tags,
                "team_affiliation": team_affiliation,
                "borough_scene": borough_scene,
                "bio": bio,
                "source_url": source_url,
                "status": status,
                "dancer_id": dancer_id,
            },
        )

        updated_profile = fetch_all(
            """
            SELECT *
            FROM dancer_profiles
            WHERE id = :dancer_id
            LIMIT 1
            """,
            {"dancer_id": dancer_id},
        )[0]

        return redirect(profile_url(updated_profile))

    return render_template(
        "admin_person_edit.html",
        profile=profile,
        allowed_statuses=allowed_statuses,
    )


def seed_ghost_dancer_profiles():
    try:
        from ghost_dancer_seed_data import GHOST_DANCER_PROFILES
    except ImportError:
        return

    for ghost in GHOST_DANCER_PROFILES:
        existing = fetch_all(
            """
            SELECT id
            FROM dancer_profiles
            WHERE LOWER(dance_name) = LOWER(:dance_name)
            LIMIT 1
            """,
            {"dance_name": ghost["dance_name"]},
        )

        if existing:
            continue

        bio_parts = [
            "This is a ghost profile created from community form responses.",
            ghost.get("source_note", ""),
            "The dancer can claim this profile and submit full profile details for review."
        ]

        bio = " ".join(part for part in bio_parts if part)

        execute_query(
            """
            INSERT INTO dancer_profiles (
                user_id,
                dance_name,
                real_name,
                team_affiliation,
                borough_scene,
                bio,
                source_url,
                status,
                created_at
            )
            VALUES (
                :user_id,
                :dance_name,
                :real_name,
                :team_affiliation,
                :borough_scene,
                :bio,
                :source_url,
                :status,
                :created_at
            )
            """,
            {
                "user_id": None,
                "dance_name": ghost["dance_name"],
                "real_name": "",
                "team_affiliation": ghost.get("aliases", ""),
                "borough_scene": "",
                "bio": bio,
                "source_url": "",
                "status": "Ghost Profile",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )


@app.context_processor
def inject_user_context():
    return {
        "current_user": current_user()
    }



def ensure_verification_flag_column():
    dialect = engine.dialect.name

    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS needs_verification INTEGER DEFAULT 0"))
            conn.execute(text("UPDATE submissions SET needs_verification = 0 WHERE needs_verification IS NULL"))
        else:
            existing_columns = {
                row[1] for row in conn.execute(text("PRAGMA table_info(submissions)")).fetchall()
            }

            if "needs_verification" not in existing_columns:
                conn.execute(text("ALTER TABLE submissions ADD COLUMN needs_verification INTEGER DEFAULT 0"))

            conn.execute(text("UPDATE submissions SET needs_verification = 0 WHERE needs_verification IS NULL"))



def hide_seeded_records_from_verify_queue():
    execute_query(
        """
        UPDATE submissions
        SET needs_verification = 0
        WHERE needs_verification IS NULL
        OR needs_verification != 1
        """
    )


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/about")
def about():
    return render_template("about.html")



@app.route("/account/signup", methods=["GET", "POST"])
def account_signup():
    error = ""

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        organization_name = request.form.get("organization_name", "").strip()

        if len(display_name) < 2:
            error = "Add your name or alias."
        elif "@" not in email:
            error = "Add a valid email."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        else:
            existing = fetch_all(
                "SELECT id FROM archive_users WHERE email = :email LIMIT 1",
                {"email": email},
            )

            if existing:
                error = "An account with that email already exists."
            else:
                execute_query(
                    """
                    INSERT INTO archive_users (
                        display_name,
                        email,
                        password_hash,
                        role,
                        organization_name,
                        created_at
                    )
                    VALUES (
                        :display_name,
                        :email,
                        :password_hash,
                        :role,
                        :organization_name,
                        :created_at
                    )
                    """,
                    {
                        "display_name": display_name,
                        "email": email,
                        "password_hash": generate_password_hash(password),
                        "role": "contributor",
                        "organization_name": organization_name,
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )

                user = fetch_all(
                    "SELECT * FROM archive_users WHERE email = :email LIMIT 1",
                    {"email": email},
                )[0]

                session["user_id"] = user["id"]
                session["user_role"] = user["role"]
                return redirect(url_for("home"))

    return render_template("account_signup.html", error=error)


@app.route("/account/login", methods=["GET", "POST"])
def account_login():
    error = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        users = fetch_all(
            "SELECT * FROM archive_users WHERE email = :email LIMIT 1",
            {"email": email},
        )

        if not users or not check_password_hash(users[0]["password_hash"], password):
            error = "That login did not work. Check your email and password."
        else:
            user = users[0]
            session["user_id"] = user["id"]
            session["user_role"] = user["role"]
            return redirect(url_for("home"))

    return render_template("account_login.html", error=error)


@app.route("/account/logout")
def account_logout():
    session.pop("user_id", None)
    session.pop("user_role", None)
    return redirect(url_for("home"))


@app.route("/admin/users")
def admin_users():
    users = fetch_all(
        """
        SELECT *
        FROM archive_users
        ORDER BY created_at DESC
        """
    )

    return render_template("admin_users.html", users=users)


@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
def update_user_role(user_id):
    new_role = request.form.get("role", "").strip()

    allowed_roles = {
        "contributor",
        "affiliate_host",
        "admin",
        "suspended",
    }

    if new_role not in allowed_roles:
        return redirect(url_for("admin_users"))

    execute_query(
        """
        UPDATE archive_users
        SET role = :role
        WHERE id = :user_id
        """,
        {
            "role": new_role,
            "user_id": user_id,
        },
    )

    return redirect(url_for("admin_users"))

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

        is_affiliate = current_user_is_affiliate_host()
        user = current_user()
        review_status = "Community Supported" if is_affiliate else "Pending Review"

        details = [
            {"label": "Event Timing", "value": form_data.get("event_timing", "").strip()},
            {"label": "Organization Name", "value": event_org},
            {"label": "Event Name", "value": event_name},
            {"label": "Event Date", "value": event_date},
            {"label": "Event Time", "value": event_time},
            {"label": "Event Location", "value": event_location},
            {"label": "Battle Type", "value": form_data.get("event_battle_type", "").strip()},
            {"label": "Planned Battle List", "value": form_data.get("event_battle_list", "").strip()},
            {"label": "Judges", "value": form_data.get("event_judges", "").strip()},
            {"label": "Event Details", "value": form_data.get("event_details", "").strip()},
            {"label": "Event Results", "value": form_data.get("event_results", "").strip()},
            {"label": "Planned Battles Status", "value": form_data.get("planned_battles_status", "").strip()},
            {"label": "Battle Rescheduled", "value": "Yes" if form_data.get("battle_issue_rescheduled") == "yes" else ""},
            {"label": "Battle Cancelled", "value": "Yes" if form_data.get("battle_issue_cancelled") == "yes" else ""},
            {"label": "One Dancer on Milk Carton", "value": "Yes" if form_data.get("battle_issue_one_milk_carton") == "yes" else ""},
            {"label": "Both Dancers on Milk Carton", "value": "Yes" if form_data.get("battle_issue_both_milk_carton") == "yes" else ""},
            {"label": "Battle Issue Details", "value": form_data.get("battle_issue_details", "").strip()},
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

    upcoming_soon, upcoming_later, past_events, undated_events = split_event_records(approved_events)

    return render_template(
        "events.html",
        approved_events=approved_events,
        upcoming_soon=upcoming_soon,
        upcoming_later=upcoming_later,
        past_events=past_events,
        undated_events=undated_events,
    )


@app.route("/people")
def people_hub():
    return redirect(url_for("dancers"))



@app.route("/events/<int:event_id>")
def event_detail(event_id):
    public_status_filter = ""
    params = {"event_id": event_id}

    if not session.get("admin_logged_in"):
        public_status_filter = "AND review_status IN ('Verified', 'Community Supported')"

    events = fetch_all(
        f"""
        SELECT *
        FROM submissions
        WHERE id = :event_id
        AND submission_type = 'event'
        {public_status_filter}
        LIMIT 1
        """,
        params,
    )

    if not events:
        return redirect(url_for("events"))

    return render_template("event_detail.html", event=events[0])


@app.route("/admin/events/<int:event_id>/edit", methods=["GET", "POST"])
def admin_event_edit(event_id):
    allowed_statuses = [
        "Pending Review",
        "Needs Verification",
        "Community Supported",
        "Verified",
        "Disputed",
        "Rejected",
    ]

    events = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE id = :event_id
        AND submission_type = 'event'
        LIMIT 1
        """,
        {"event_id": event_id},
    )

    if not events:
        return redirect(url_for("admin_submissions"))

    event = events[0]

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        related_to = request.form.get("related_to", "").strip()
        source_url = request.form.get("source_url", "").strip()
        review_status = request.form.get("review_status", "").strip()

        if review_status not in allowed_statuses:
            review_status = event["review_status"]

        labels = request.form.getlist("detail_label")
        values = request.form.getlist("detail_value")

        details = []
        for label, value in zip(labels, values):
            label = label.strip()
            value = value.strip()

            if label or value:
                details.append({"label": label, "value": value})

        execute_query(
            """
            UPDATE submissions
            SET title = :title,
                related_to = :related_to,
                source_url = :source_url,
                review_status = :review_status,
                details_json = :details_json
            WHERE id = :event_id
            """,
            {
                "title": title or event["title"],
                "related_to": related_to,
                "source_url": source_url,
                "review_status": review_status,
                "details_json": json.dumps(details, ensure_ascii=False),
                "event_id": event_id,
            },
        )

        return redirect(url_for("event_detail", event_id=event_id))

    details = from_json_filter(event["details_json"])

    return render_template(
        "admin_event_edit.html",
        event=event,
        details=details,
        allowed_statuses=allowed_statuses,
    )

@app.route("/dancers")
@app.route("/people/dancers")
def dancers():
    dancer_profiles = fetch_all(
        """
        SELECT *
        FROM dancer_profiles
        WHERE status IN ('Approved', 'Verified', 'Community Supported', 'Ghost Profile')
        ORDER BY created_at DESC
        """
    )

    approved_flowers = fetch_all(
        """
        SELECT *
        FROM dancer_flowers
        WHERE status = 'Approved'
        ORDER BY created_at DESC
        """
    )

    flowers_by_profile = {}

    for flower in approved_flowers:
        profile_id = flower["dancer_profile_id"]

        if profile_id not in flowers_by_profile:
            flowers_by_profile[profile_id] = []

        flowers_by_profile[profile_id].append(flower)

    return render_template(
        "dancers.html",
        dancer_profiles=dancer_profiles,
        flowers_by_profile=flowers_by_profile,
    )




@app.route("/producers")
@app.route("/people/producers")
def producers():
    ensure_person_role_columns()

    producer_profiles = fetch_all(
        """
        SELECT *
        FROM dancer_profiles
        WHERE status IN (
            'Approved',
            'Verified',
            'Community Supported',
            'Needs Verification',
            'Ghost Profile'
        )
        AND role_tags LIKE '%Producer%'
        ORDER BY lower(dance_name) ASC
        """
    )

    return render_template(
        "producers.html",
        producer_profiles=producer_profiles,
    )


@app.route("/dancers/create", methods=["GET", "POST"])
def create_dancer_profile():
    user = current_user()

    if not user:
        return redirect(url_for("account_login"))

    error = ""

    if request.method == "POST":
        dance_name = request.form.get("dance_name", "").strip()
        real_name = request.form.get("real_name", "").strip()
        team_affiliation = request.form.get("team_affiliation", "").strip()
        borough_scene = request.form.get("borough_scene", "").strip()
        bio = request.form.get("bio", "").strip()
        source_url = request.form.get("source_url", "").strip()

        if len(dance_name) < 2:
            error = "Add your dancer name or alias."
        else:
            execute_query(
                """
                INSERT INTO dancer_profiles (
                    user_id,
                    dance_name,
                    real_name,
                    team_affiliation,
                    borough_scene,
                    bio,
                    source_url,
                    status,
                    created_at
                )
                VALUES (
                    :user_id,
                    :dance_name,
                    :real_name,
                    :team_affiliation,
                    :borough_scene,
                    :bio,
                    :source_url,
                    :status,
                    :created_at
                )
                """,
                {
                    "user_id": user["id"],
                    "dance_name": dance_name,
                    "real_name": real_name,
                    "team_affiliation": team_affiliation,
                    "borough_scene": borough_scene,
                    "bio": bio,
                    "source_url": source_url,
                    "status": "Pending Review",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            )

            return redirect(url_for("dancers"))

    return render_template("dancer_create.html", error=error)




@app.route("/dancers/<int:dancer_id>")
def dancer_profile_detail_by_id(dancer_id):
    ensure_person_role_columns()
    ensure_profile_slug_column()

    profiles = fetch_all(
        """
        SELECT *
        FROM dancer_profiles
        WHERE id = :dancer_id
        LIMIT 1
        """,
        {"dancer_id": dancer_id},
    )

    if not profiles:
        return redirect(url_for("dancers"))

    return redirect(profile_url(profiles[0]))


@app.route("/dancers/<profile_slug>")
def dancer_profile_detail(profile_slug):
    ensure_profile_enrichment_columns()
    ensure_person_role_columns()
    ensure_profile_slug_column()

    profiles = fetch_all(
        """
        SELECT *
        FROM dancer_profiles
        WHERE profile_slug = :profile_slug
        AND status IN (
            'Approved',
            'Verified',
            'Community Supported',
            'Needs Verification',
            'Ghost Profile'
        )
        LIMIT 1
        """,
        {"profile_slug": profile_slug},
    )

    if not profiles:
        return redirect(url_for("dancers"))

    profile = profiles[0]
    dancer_id = profile["id"]
    profile_name = profile["dance_name"]
    search_term = f"%{profile_name.lower()}%"

    flowers = fetch_all(
        """
        SELECT *
        FROM dancer_flowers
        WHERE dancer_profile_id = :dancer_id
        AND status = 'Approved'
        ORDER BY created_at DESC
        """,
        {"dancer_id": dancer_id},
    )

    suggestions = fetch_all(
        """
        SELECT *
        FROM dancer_suggestions
        WHERE dancer_profile_id = :dancer_id
        AND status = 'Approved'
        ORDER BY created_at DESC
        """,
        {"dancer_id": dancer_id},
    )

    mention_rows = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE LOWER(COALESCE(title, '')) LIKE :search_term
           OR LOWER(COALESCE(related_to, '')) LIKE :search_term
           OR LOWER(COALESCE(details_json, '')) LIKE :search_term
        ORDER BY created_at DESC
        LIMIT 75
        """,
        {"search_term": search_term},
    )

    ledger_mentions = []
    lower_name = profile_name.lower()

    for row in mention_rows:
        mention = dict(row)
        labels = []

        if lower_name in (row["title"] or "").lower():
            labels.append("Title")

        if lower_name in (row["related_to"] or "").lower():
            labels.append("Related To")

        for item in from_json_filter(row["details_json"]):
            label = item.get("label", "")
            value = item.get("value", "")

            if lower_name in value.lower():
                labels.append(label)

        if not labels:
            continue

        mention["mention_labels"] = ", ".join(sorted(set(labels)))

        if row["submission_type"] == "event":
            mention["public_url"] = event_public_url(row)
        elif row["submission_type"] == "historical_claim":
            mention["public_url"] = f"/verify/{row['id']}"
        else:
            mention["public_url"] = ""

        ledger_mentions.append(mention)

    similar_profiles = find_similar_profiles(profile)
    has_enrichment = profile_has_enrichment(profile)

    return render_template(
        "dancer_profile_detail.html",
        profile=profile,
        flowers=flowers,
        suggestions=suggestions,
        ledger_mentions=ledger_mentions,
        similar_profiles=similar_profiles,
        has_enrichment=has_enrichment,
    )


@app.route("/dancers/<int:dancer_id>/flowers", methods=["POST"])
def give_dancer_flowers(dancer_id):
    flower_text = request.form.get("flower_text", "").strip()
    submitter_name = request.form.get("submitter_name", "").strip()
    submitter_role = request.form.get("submitter_role", "").strip()
    contact = request.form.get("contact", "").strip()
    anonymous_submission = request.form.get("anonymous_submission") == "1"
    user = current_user()

    if anonymous_submission:
        submitter_name = "Anonymous"
    elif user and not submitter_name:
        submitter_name = user["display_name"]

    if flower_text:
        execute_query(
            """
            INSERT INTO dancer_flowers (
                dancer_profile_id,
                flower_text,
                submitter_name,
                submitter_role,
                contact,
                status,
                created_at
            )
            VALUES (
                :dancer_profile_id,
                :flower_text,
                :submitter_name,
                :submitter_role,
                :contact,
                :status,
                :created_at
            )
            """,
            {
                "dancer_profile_id": dancer_id,
                "flower_text": flower_text,
                "submitter_name": submitter_name,
                "submitter_role": submitter_role,
                "contact": contact,
                "status": "Pending Review",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    return redirect(url_for("dancer_profile_detail", dancer_id=dancer_id))


@app.route("/dancers/<int:dancer_id>/suggest", methods=["POST"])
def suggest_dancer_update(dancer_id):
    suggestion_text = request.form.get("suggestion_text", "").strip()
    source_url = request.form.get("source_url", "").strip()
    submitter_name = request.form.get("submitter_name", "").strip()
    submitter_role = request.form.get("submitter_role", "").strip()
    contact = request.form.get("contact", "").strip()
    anonymous_submission = request.form.get("anonymous_submission") == "1"
    user = current_user()

    if anonymous_submission:
        submitter_name = "Anonymous"
    elif user and not submitter_name:
        submitter_name = user["display_name"]

    if suggestion_text:
        execute_query(
            """
            INSERT INTO dancer_suggestions (
                dancer_profile_id,
                suggestion_text,
                source_url,
                submitter_name,
                submitter_role,
                contact,
                status,
                created_at
            )
            VALUES (
                :dancer_profile_id,
                :suggestion_text,
                :source_url,
                :submitter_name,
                :submitter_role,
                :contact,
                :status,
                :created_at
            )
            """,
            {
                "dancer_profile_id": dancer_id,
                "suggestion_text": suggestion_text,
                "source_url": source_url,
                "submitter_name": submitter_name,
                "submitter_role": submitter_role,
                "contact": contact,
                "status": "Pending Review",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    return redirect(url_for("dancer_profile_detail", dancer_id=dancer_id))


@app.route("/admin/dancer-profiles")
def admin_dancer_profiles():
    profiles = fetch_all(
        """
        SELECT *
        FROM dancer_profiles
        ORDER BY created_at DESC
        """
    )

    return render_template("admin_dancer_profiles.html", profiles=profiles)


@app.route("/admin/dancer-profiles/<int:dancer_id>/status", methods=["POST"])
def update_dancer_profile_status(dancer_id):
    new_status = request.form.get("status", "").strip()

    allowed_statuses = {
        "Pending Review",
        "Approved",
        "Verified",
        "Community Supported",
        "Needs Verification",
        "Rejected",
        "Ghost Profile",
    }

    if new_status not in allowed_statuses:
        return redirect(url_for("admin_dancer_profiles"))

    execute_query(
        """
        UPDATE dancer_profiles
        SET status = :status
        WHERE id = :dancer_id
        """,
        {
            "status": new_status,
            "dancer_id": dancer_id,
        },
    )

    return redirect(url_for("admin_dancer_profiles"))


@app.route("/admin/dancer-feedback")
def admin_dancer_feedback():
    suggestions = fetch_all(
        """
        SELECT dancer_suggestions.*, dancer_profiles.dance_name
        FROM dancer_suggestions
        JOIN dancer_profiles ON dancer_suggestions.dancer_profile_id = dancer_profiles.id
        ORDER BY dancer_suggestions.created_at DESC
        """
    )

    flowers = fetch_all(
        """
        SELECT dancer_flowers.*, dancer_profiles.dance_name
        FROM dancer_flowers
        JOIN dancer_profiles ON dancer_flowers.dancer_profile_id = dancer_profiles.id
        ORDER BY dancer_flowers.created_at DESC
        """
    )

    return render_template(
        "admin_dancer_feedback.html",
        suggestions=suggestions,
        flowers=flowers,
    )


@app.route("/admin/dancer-suggestions/<int:suggestion_id>/status", methods=["POST"])
def update_dancer_suggestion_status(suggestion_id):
    new_status = request.form.get("status", "").strip()

    if new_status not in {"Pending Review", "Approved", "Rejected"}:
        return redirect(url_for("admin_dancer_feedback"))

    execute_query(
        """
        UPDATE dancer_suggestions
        SET status = :status
        WHERE id = :suggestion_id
        """,
        {
            "status": new_status,
            "suggestion_id": suggestion_id,
        },
    )

    return redirect(url_for("admin_dancer_feedback"))


@app.route("/admin/dancer-flowers/<int:flower_id>/status", methods=["POST"])
def update_dancer_flower_status(flower_id):
    new_status = request.form.get("status", "").strip()

    if new_status not in {"Pending Review", "Approved", "Rejected"}:
        return redirect(url_for("admin_dancer_feedback"))

    execute_query(
        """
        UPDATE dancer_flowers
        SET status = :status
        WHERE id = :flower_id
        """,
        {
            "status": new_status,
            "flower_id": flower_id,
        },
    )

    return redirect(url_for("admin_dancer_feedback"))



@app.route("/people/teams")
def teams():
    return render_template("teams.html")


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
        WHERE needs_verification = 1
        AND review_status IN ('Needs Verification', 'Disputed')
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


@app.route("/ask", methods=["GET", "POST"])
def ask_archive():
    query = ""
    results = []
    searched = False

    if request.method == "POST":
        query = request.form.get("query", "").strip()
        searched = True

        if query:
            search_term = f"%{query.lower()}%"

            results = fetch_all(
                """
                SELECT *
                FROM submissions
                WHERE
                    LOWER(title) LIKE :search_term
                    OR LOWER(related_to) LIKE :search_term
                    OR LOWER(source_url) LIKE :search_term
                    OR LOWER(details_json) LIKE :search_term
                    OR LOWER(submission_type) LIKE :search_term
                ORDER BY
                    CASE
                        WHEN review_status = 'Verified' THEN 1
                        WHEN review_status = 'Community Supported' THEN 2
                        WHEN review_status = 'Needs Verification' THEN 3
                        WHEN review_status = 'Disputed' THEN 4
                        ELSE 5
                    END,
                    created_at DESC
                LIMIT 12
                """,
                {"search_term": search_term},
            )

    return render_template(
        "ask_archive.html",
        query=query,
        results=results,
        searched=searched,
    )



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



def ensure_portal_tables():
    dialect = engine.dialect.name

    if dialect == "postgresql":
        request_id = "id SERIAL PRIMARY KEY"
    else:
        request_id = "id INTEGER PRIMARY KEY AUTOINCREMENT"

    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS role_requests (
                    {request_id},
                    user_id INTEGER NOT NULL,
                    requested_role TEXT NOT NULL,
                    reason TEXT,
                    status TEXT DEFAULT 'Pending Review',
                    created_at TEXT NOT NULL
                )
                """
            )
        )

        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS contributor_user_id INTEGER"))
            conn.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS anonymous_submission INTEGER DEFAULT 0"))
        else:
            existing_columns = {
                row[1] for row in conn.execute(text("PRAGMA table_info(submissions)")).fetchall()
            }

            if "contributor_user_id" not in existing_columns:
                conn.execute(text("ALTER TABLE submissions ADD COLUMN contributor_user_id INTEGER"))

            if "anonymous_submission" not in existing_columns:
                conn.execute(text("ALTER TABLE submissions ADD COLUMN anonymous_submission INTEGER DEFAULT 0"))


@app.context_processor
def inject_logged_in_user():
    return {"logged_in_user": current_user()}


def get_contribution_points(user_id):
    submission_count = fetch_all(
        """
        SELECT COUNT(*) AS total
        FROM submissions
        WHERE contributor_user_id = :user_id
        """,
        {"user_id": user_id},
    )[0]["total"]

    profile_count = fetch_all(
        """
        SELECT COUNT(*) AS total
        FROM dancer_profiles
        WHERE user_id = :user_id
        """,
        {"user_id": user_id},
    )[0]["total"]

    return {
        "submission_count": submission_count,
        "profile_count": profile_count,
        "points": (submission_count * 5) + (profile_count * 10),
    }


def create_role_request(user_id, requested_role, reason):
    existing = fetch_all(
        """
        SELECT id
        FROM role_requests
        WHERE user_id = :user_id
        AND requested_role = :requested_role
        AND status = 'Pending Review'
        LIMIT 1
        """,
        {
            "user_id": user_id,
            "requested_role": requested_role,
        },
    )

    if existing:
        return

    execute_query(
        """
        INSERT INTO role_requests (
            user_id,
            requested_role,
            reason,
            status,
            created_at
        )
        VALUES (
            :user_id,
            :requested_role,
            :reason,
            :status,
            :created_at
        )
        """,
        {
            "user_id": user_id,
            "requested_role": requested_role,
            "reason": reason,
            "status": "Pending Review",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
    )




init_db()
ensure_dancer_tables()
ensure_portal_tables()




@app.route("/<organizer_slug>")
def organizer_detail(organizer_slug):
    blocked_slugs = {
        "admin",
        "account",
        "ask",
        "events",
        "people",
        "dancers",
        "producers",
        "battles",
        "awards",
        "verify",
        "about",
        "submit",
        "static",
        "contributor",
        "eventaffiliates",
    }

    if organizer_slug.lower() in blocked_slugs:
        return redirect(url_for("home"))

    all_events = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE submission_type = 'event'
        AND review_status IN ('Verified', 'Community Supported')
        ORDER BY created_at DESC
        """
    )

    organizer_events = []

    for event in all_events:
        organizer_name = event_organizer_name(event)

        if normalize_public_slug(organizer_name) == normalize_public_slug(organizer_slug):
            organizer_events.append(event)

    if not organizer_events:
        return redirect(url_for("events"))

    organizer_name = event_organizer_name(organizer_events[0])

    return render_template(
        "organizer_detail.html",
        organizer_name=organizer_name,
        organizer_slug=make_public_slug(organizer_name),
        organizer_events=organizer_events,
    )


@app.route("/<organizer_slug>/<event_slug>")
def organizer_event_detail(organizer_slug, event_slug):
    all_events = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE submission_type = 'event'
        AND review_status IN ('Verified', 'Community Supported')
        ORDER BY created_at DESC
        """
    )

    for event in all_events:
        organizer_match = normalize_public_slug(event_organizer_name(event)) == normalize_public_slug(organizer_slug)
        event_match = normalize_public_slug(event["title"]) == normalize_public_slug(event_slug)

        if organizer_match and event_match:
            return render_template("event_detail.html", event=event)

    return redirect(url_for("events"))



def ensure_profile_enrichment_columns():
    new_columns = {
        "aliases": "TEXT",
        "era": "TEXT",
        "style_notes": "TEXT",
        "signature_moves": "TEXT",
        "battle_history": "TEXT",
        "legacy_notes": "TEXT",
        "private_notes": "TEXT",
        "csv_source_note": "TEXT",
        "updated_from_csv_at": "TEXT",
    }

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            for column_name, column_type in new_columns.items():
                conn.execute(
                    text(f"ALTER TABLE dancer_profiles ADD COLUMN IF NOT EXISTS {column_name} {column_type}")
                )
        else:
            existing_columns = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(dancer_profiles)")).fetchall()
            }

            for column_name, column_type in new_columns.items():
                if column_name not in existing_columns:
                    conn.execute(
                        text(f"ALTER TABLE dancer_profiles ADD COLUMN {column_name} {column_type}")
                    )


def ensure_profile_claim_columns():
    dialect = engine.dialect.name

    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN IF NOT EXISTS recent_battle TEXT"))
            conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN IF NOT EXISTS claimed_at TEXT"))
        else:
            existing_columns = {
                row[1] for row in conn.execute(text("PRAGMA table_info(dancer_profiles)")).fetchall()
            }

            if "recent_battle" not in existing_columns:
                conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN recent_battle TEXT"))

            if "claimed_at" not in existing_columns:
                conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN claimed_at TEXT"))


def get_profile_by_slug(profile_slug):
    ensure_person_role_columns()
    ensure_profile_slug_column()
    ensure_profile_claim_columns()

    profiles = fetch_all(
        """
        SELECT *
        FROM dancer_profiles
        WHERE profile_slug = :profile_slug
        LIMIT 1
        """,
        {"profile_slug": profile_slug},
    )

    return profiles[0] if profiles else None


@app.route("/profiles/<profile_slug>/claim", methods=["GET", "POST"])
@app.route("/dancers/<profile_slug>/claim", methods=["GET", "POST"])
def claim_profile(profile_slug):
    profile = get_profile_by_slug(profile_slug)

    if not profile:
        return redirect(url_for("dancers"))

    user = current_user()
    error = ""

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        profile_name = request.form.get("dance_name", "").strip()
        team_affiliation = request.form.get("team_affiliation", "").strip()
        borough_scene = request.form.get("borough_scene", "").strip()
        recent_battle = request.form.get("recent_battle", "").strip()
        role_tags = request.form.get("role_tags", "").strip()

        if not user:
            if not email or not password:
                error = "Create an account or log in before claiming this profile."
            else:
                existing_users = fetch_all(
                    """
                    SELECT *
                    FROM archive_users
                    WHERE lower(email) = lower(:email)
                    LIMIT 1
                    """,
                    {"email": email},
                )

                if existing_users:
                    existing_user = existing_users[0]

                    if not check_password_hash(existing_user["password_hash"], password):
                        error = "That email already exists. Use the correct password or log in first."
                    else:
                        session["user_id"] = existing_user["id"]
                        user = existing_user
                else:
                    execute_query(
                        """
                        INSERT INTO archive_users (
                            display_name,
                            email,
                            password_hash,
                            role,
                            organization_name,
                            created_at
                        )
                        VALUES (
                            :display_name,
                            :email,
                            :password_hash,
                            :role,
                            :organization_name,
                            :created_at
                        )
                        """,
                        {
                            "display_name": display_name or profile_name or profile["dance_name"],
                            "email": email,
                            "password_hash": generate_password_hash(password),
                            "role": "contributor",
                            "organization_name": "",
                            "created_at": datetime.now().isoformat(timespec="seconds"),
                        },
                    )

                    new_user = fetch_all(
                        """
                        SELECT *
                        FROM archive_users
                        WHERE lower(email) = lower(:email)
                        LIMIT 1
                        """,
                        {"email": email},
                    )[0]

                    session["user_id"] = new_user["id"]
                    user = new_user

        if user and not error:
            final_name = profile_name or profile["dance_name"]
            final_slug = unique_profile_slug(final_name, profile["id"])

            execute_query(
                """
                UPDATE dancer_profiles
                SET user_id = :user_id,
                    dance_name = :dance_name,
                    profile_slug = :profile_slug,
                    team_affiliation = :team_affiliation,
                    borough_scene = :borough_scene,
                    recent_battle = :recent_battle,
                    role_tags = :role_tags,
                    status = :status,
                    claimed_at = :claimed_at
                WHERE id = :profile_id
                """,
                {
                    "user_id": user["id"],
                    "dance_name": final_name,
                    "profile_slug": final_slug,
                    "team_affiliation": team_affiliation,
                    "borough_scene": borough_scene,
                    "recent_battle": recent_battle,
                    "role_tags": role_tags or profile["role_tags"] or "Dancer",
                    "status": "Pending Review",
                    "claimed_at": datetime.now().isoformat(timespec="seconds"),
                    "profile_id": profile["id"],
                },
            )

            updated_profile = fetch_all(
                """
                SELECT *
                FROM dancer_profiles
                WHERE id = :profile_id
                LIMIT 1
                """,
                {"profile_id": profile["id"]},
            )[0]

            return redirect(profile_url(updated_profile))

    return render_template(
        "profile_claim.html",
        profile=profile,
        user=user,
        error=error,
    )


def format_ledger_date(value):
    if not value:
        return ""

    raw = str(value).strip()

    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(raw[:19], fmt)
            return parsed.strftime("%A, %d %B, %Y")
        except ValueError:
            continue

    return raw


@app.template_filter("ledger_date")
def ledger_date_filter(value):
    return format_ledger_date(value)


def normalize_profile_match_name(value):
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def profile_has_enrichment(profile):
    fields = [
        "team_affiliation",
        "borough_scene",
        "era",
        "style_notes",
        "signature_moves",
        "battle_history",
        "legacy_notes",
    ]

    return any((profile.get(field) or "").strip() for field in fields)


def find_similar_profiles(profile):
    if not profile:
        return []

    current_id = profile.get("id")
    current_name = profile.get("dance_name", "")
    current_key = normalize_profile_match_name(current_name)

    if not current_key:
        return []

    rows = fetch_all(
        """
        SELECT *
        FROM dancer_profiles
        WHERE id != :current_id
        ORDER BY lower(dance_name) ASC
        """,
        {"current_id": current_id},
    )

    matches = []

    for row in rows:
        row_key = normalize_profile_match_name(row.get("dance_name", ""))

        if not row_key:
            continue

        if current_key == row_key:
            matches.append(row)
            continue

        if current_key in row_key or row_key in current_key:
            matches.append(row)
            continue

    return matches[:8]


def merge_profile_text(primary, duplicate, field):
    primary_value = (primary.get(field) or "").strip()
    duplicate_value = (duplicate.get(field) or "").strip()

    if not duplicate_value:
        return primary_value

    if not primary_value:
        return duplicate_value

    if duplicate_value.lower() in primary_value.lower():
        return primary_value

    return primary_value + "\\n\\n" + duplicate_value


def merge_profile_roles(primary_roles, duplicate_roles):
    roles = []

    for role_set in [primary_roles, duplicate_roles]:
        for role in (role_set or "").replace("|", ",").split(","):
            role = role.strip()
            if role and role not in roles:
                roles.append(role)

    return ", ".join(roles)


@app.route("/admin/people/<int:primary_id>/merge/<int:duplicate_id>", methods=["POST"])
def admin_merge_people(primary_id, duplicate_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    primary = fetch_one(
        "SELECT * FROM dancer_profiles WHERE id = :id",
        {"id": primary_id},
    )

    duplicate = fetch_one(
        "SELECT * FROM dancer_profiles WHERE id = :id",
        {"id": duplicate_id},
    )

    if not primary or not duplicate:
        return redirect(url_for("dancers"))

    merge_fields = [
        "aliases",
        "team_affiliation",
        "borough_scene",
        "era",
        "style_notes",
        "signature_moves",
        "battle_history",
        "bio",
        "legacy_notes",
        "source_url",
        "csv_source_note",
    ]

    values = {
        "id": primary_id,
        "role_tags": merge_profile_roles(primary.get("role_tags"), duplicate.get("role_tags")),
    }

    for field in merge_fields:
        values[field] = merge_profile_text(primary, duplicate, field)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE dancer_profiles
                SET aliases = :aliases,
                    team_affiliation = :team_affiliation,
                    borough_scene = :borough_scene,
                    era = :era,
                    style_notes = :style_notes,
                    signature_moves = :signature_moves,
                    battle_history = :battle_history,
                    bio = :bio,
                    legacy_notes = :legacy_notes,
                    source_url = :source_url,
                    csv_source_note = :csv_source_note,
                    role_tags = :role_tags
                WHERE id = :id
                """
            ),
            values,
        )

        conn.execute(
            text("DELETE FROM dancer_profiles WHERE id = :duplicate_id"),
            {"duplicate_id": duplicate_id},
        )

    return redirect(profile_url(primary))
