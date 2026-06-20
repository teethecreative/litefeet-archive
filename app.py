from difflib import SequenceMatcher
import json
import os
import re
import requests
import secrets
from email.message import EmailMessage
from html import unescape
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen
from datetime import datetime, timedelta

from flask import abort, Flask, flash, redirect, render_template, request, session, url_for, Response
from sqlalchemy import create_engine, inspect, text
from werkzeug.security import check_password_hash, generate_password_hash
from markupsafe import Markup, escape
import hashlib

app = Flask(__name__)


@app.route("/robots.txt")
def robots_txt():
    return Response(
        "User-agent: *\n"
        "Allow: /\n"
        "Sitemap: https://thelitefeetvault.com/sitemap.xml\n",
        mimetype="text/plain",
    )


@app.route("/sitemap.xml")
def sitemap_xml():
    pages = [
        "",
        "ask",
        "events",
        "people/dancers",
        "people/teams",
        "litefeet-music",
        "battles",
        "awards",
        "verify",
        "about",
        "submit",
        "submit/event",
        "submit/music",
    ]

    urls = []
    for page in pages:
        loc = f"https://thelitefeetvault.com/{page}".rstrip("/")
        urls.append(f"""
    <url>
        <loc>{loc}</loc>
        <changefreq>weekly</changefreq>
        <priority>0.8</priority>
    </url>""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{''.join(urls)}
</urlset>
"""

    return Response(xml, mimetype="application/xml")
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


# --- Maintenance mode / Phase 0 rebuild guard ---

MAINTENANCE_ALLOWED_PATHS = {
    "/admin/login",
    "/account/login",
    "/login",
    "/maintenance-submit",
    "/static",
    "/favicon.ico",
}


def maintenance_uses_postgres():
    try:
        return engine.dialect.name.startswith("postgres")
    except Exception:
        return os.environ.get("DATABASE_URL", "").lower().startswith("postgres")


def ensure_site_settings_table():
    """Small key/value table for site-wide switches like maintenance mode."""
    with engine.begin() as conn:
        if maintenance_uses_postgres():
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS site_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS site_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """))


def get_site_setting(key, default=None):
    ensure_site_settings_table()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT value FROM site_settings WHERE key = :key LIMIT 1"),
            {"key": key},
        ).mappings().first()
    if not row:
        return default
    return row["value"]


def set_site_setting(key, value):
    ensure_site_settings_table()
    if maintenance_uses_postgres():
        execute_query("""
            INSERT INTO site_settings (key, value, updated_at)
            VALUES (:key, :value, CURRENT_TIMESTAMP)
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
        """, {"key": key, "value": value})
    else:
        execute_query("""
            INSERT OR REPLACE INTO site_settings (key, value, updated_at)
            VALUES (:key, :value, CURRENT_TIMESTAMP)
        """, {"key": key, "value": value})


def maintenance_mode_enabled():
    return get_site_setting("maintenance_mode", "on") == "on"


def current_request_is_admin_bypass():
    return bool(session.get("admin_logged_in") or current_user_is_admin())


def maintenance_path_allowed():
    path = request.path or "/"

    if path.startswith("/static/"):
        return True

    if path.startswith("/admin"):
        return True

    if path in MAINTENANCE_ALLOWED_PATHS:
        return True

    return False


@app.before_request
def maintenance_mode_guard():
    # Render health check bypass.
    # Render probes HEAD / while deciding whether the service is healthy.
    # Maintenance mode should not make Render think the service is down.
    if request.path == "/healthz":
        return None

    if request.method == "HEAD" and request.path == "/":
        return "", 200

    if not maintenance_mode_enabled():
        return None

    if current_request_is_admin_bypass():
        return None

    if maintenance_path_allowed():
        return None

    return render_template("maintenance.html"), 503


@app.route("/maintenance-submit", methods=["POST"])
def maintenance_submit():
    ensure_verification_tables()

    name = request.form.get("name", "").strip()
    contact = request.form.get("contact", "").strip()
    category = request.form.get("category", "").strip()
    details = request.form.get("details", "").strip()
    links = request.form.get("links", "").strip()
    follow_up = request.form.get("follow_up", "").strip()

    if not details:
        return render_template(
            "maintenance.html",
            maintenance_error="Please add a few details before submitting.",
        ), 400

    title = f"Maintenance submission: {category or 'General'}"
    description_parts = [
        f"Name / Alias: {name or 'Not provided'}",
        f"Email or IG: {contact or 'Not provided'}",
        f"Category: {category or 'General'}",
        "",
        "Details:",
        details,
    ]

    if links:
        description_parts.extend(["", "Links / Proof:", links])

    if follow_up:
        description_parts.extend(["", f"Can contact for follow-up: {follow_up}"])

    description = "\n".join(description_parts)

    # Insert only into columns that exist in the current submissions table.
    # This keeps maintenance submissions safe across older local SQLite schemas
    # and production Postgres schemas without dropping or rewriting data.
    with engine.connect() as conn:
        if maintenance_uses_postgres():
            column_rows = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'submissions'
            """)).fetchall()
            existing_columns = {row[0] for row in column_rows}
        else:
            column_rows = conn.execute(text("PRAGMA table_info(submissions)")).fetchall()
            existing_columns = {row[1] for row in column_rows}

    now_value = datetime.now().isoformat(timespec="seconds")

    candidate_values = {
        "title": title,
        "category": category or "Maintenance",
        "submission_type": category or "Maintenance",
        "description": description,
        "details": description,
        "body": description,
        "notes": description,
        "status": "Pending Review",
        "submitter_name": name,
        "submitter_contact": contact,
        "submitter_email": contact,
        "submitter_role": "Maintenance Page",
        "source": "maintenance_page",
        "source_url": links,
        "anonymous_submission": 0,
        "created_at": now_value,
        "updated_at": now_value,
        "submitted_at": now_value,
    }

    insert_values = {
        column: value
        for column, value in candidate_values.items()
        if column in existing_columns
    }

    if not insert_values:
        return render_template(
            "maintenance.html",
            maintenance_error="The Ledger received this, but the submission table needs admin setup before it can save.",
        ), 500

    columns_sql = ", ".join(insert_values.keys())
    values_sql = ", ".join(f":{column}" for column in insert_values.keys())

    execute_query(
        f"INSERT INTO submissions ({columns_sql}) VALUES ({values_sql})",
        insert_values,
    )

    return render_template("maintenance.html", maintenance_success=True)


@app.route("/admin/maintenance", methods=["GET", "POST"])
def admin_maintenance():
    if not current_user_is_admin() and not session.get("admin_logged_in"):
        return redirect(url_for("admin_login", next=request.path))

    if request.method == "POST":
        mode = request.form.get("maintenance_mode", "off")
        set_site_setting("maintenance_mode", "on" if mode == "on" else "off")
        flash("Maintenance mode updated.", "success")
        return redirect(url_for("admin_maintenance"))

    return render_template(
        "admin_maintenance.html",
        maintenance_mode=maintenance_mode_enabled(),
    )

# --- End maintenance mode / Phase 0 rebuild guard ---


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
        SELECT id, dance_name
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
    new_status = normalize_people_profile_status(request.form.get("status", "").strip())

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




def database_is_postgres():
    try:
        return engine.url.get_backend_name().startswith("postgres")
    except Exception:
        return False


def ledger_primary_key_sql():
    if database_is_postgres():
        return "id SERIAL PRIMARY KEY"
    return "id INTEGER PRIMARY KEY AUTOINCREMENT"


def fetch_all(query, params=None):
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        return result.mappings().all()


def execute_query(query, params=None):
    with engine.begin() as conn:
        conn.execute(text(query), params or {})



def ensure_account_review_columns():
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("archive_users")}

    if "account_status" not in columns:
        execute_query(
            "ALTER TABLE archive_users ADD COLUMN account_status TEXT NOT NULL DEFAULT 'pending'"
        )

    if "account_status_note" not in columns:
        execute_query(
            "ALTER TABLE archive_users ADD COLUMN account_status_note TEXT"
        )

    # Admin accounts should not get trapped in the pending queue.
    execute_query(
        """
        UPDATE archive_users
        SET account_status = 'approved'
        WHERE role = 'admin'
        AND account_status = 'pending'
        """
    )



def normalize_match_name(value):
    value = (value or "").lower().strip()
    keep = []
    for char in value:
        if char.isalnum() or char.isspace():
            keep.append(char)
    return " ".join("".join(keep).split())


def name_similarity(a, b):
    a = normalize_match_name(a)
    b = normalize_match_name(b)

    if not a or not b:
        return 0

    if a == b:
        return 100

    if a in b or b in a:
        return 92

    return int(SequenceMatcher(None, a, b).ratio() * 100)


def ensure_profile_link_tables():
    id_column = ledger_primary_key_sql()

    execute_query(
        f"""
        CREATE TABLE IF NOT EXISTS profile_account_links (
            {id_column},
            user_id INTEGER NOT NULL,
            profile_type TEXT NOT NULL DEFAULT 'dancer',
            profile_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            requested_at TEXT NOT NULL,
            reviewed_at TEXT,
            admin_note TEXT
        )
        """
    )

    execute_query(
        f"""
        CREATE TABLE IF NOT EXISTS profile_visibility_requests (
            {id_column},
            user_id INTEGER NOT NULL,
            profile_type TEXT NOT NULL DEFAULT 'dancer',
            profile_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            requested_action TEXT NOT NULL DEFAULT 'hide_from_public_profile',
            reason TEXT,
            public_profile_status TEXT NOT NULL DEFAULT 'pending',
            ledger_record_status TEXT NOT NULL DEFAULT 'retained',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            admin_note TEXT
        )
        """
    )

def find_similar_dancer_profiles_for_user(user, limit=8):
    ensure_profile_link_tables()

    display_name = user["display_name"] if user and "display_name" in user else ""
    email = user["email"] if user and "email" in user else ""

    search_terms = [
        display_name,
        email.split("@")[0] if email else "",
    ]

    profiles = fetch_all(
        """
        SELECT id, dance_name, real_name, team_affiliation, profile_slug
        FROM dancer_profiles
        ORDER BY dance_name ASC
        """
    )

    matches = []

    for profile in profiles:
        profile_names = [
            profile["dance_name"] or "",
            profile["real_name"] or "",
        ]

        best_score = 0

        for term in search_terms:
            for profile_name in profile_names:
                best_score = max(best_score, name_similarity(term, profile_name))

        if best_score >= 55:
            matches.append(
                {
                    "profile": profile,
                    "score": best_score,
                }
            )

    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches[:limit]




def ensure_profile_match_dismissals_table():
    id_column = ledger_primary_key_sql() if "ledger_primary_key_sql" in globals() else "id INTEGER PRIMARY KEY AUTOINCREMENT"

    execute_query(
        f"""
        CREATE TABLE IF NOT EXISTS profile_match_dismissals (
            {id_column},
            user_id INTEGER NOT NULL,
            profile_type TEXT NOT NULL DEFAULT 'dancer',
            profile_id INTEGER NOT NULL,
            dismissed_at TEXT NOT NULL,
            dismissed_by TEXT,
            admin_note TEXT
        )
        """
    )


def get_dismissed_profile_ids_for_user(user_id, profile_type="dancer"):
    ensure_profile_match_dismissals_table()

    rows = fetch_all(
        """
        SELECT profile_id
        FROM profile_match_dismissals
        WHERE user_id = :user_id
        AND profile_type = :profile_type
        """,
        {
            "user_id": user_id,
            "profile_type": profile_type,
        },
    )

    return {row["profile_id"] for row in rows}


def get_existing_profile_link_ids_for_user(user_id, profile_type="dancer"):
    ensure_profile_link_tables()

    rows = fetch_all(
        """
        SELECT profile_id
        FROM profile_account_links
        WHERE user_id = :user_id
        AND profile_type = :profile_type
        """,
        {
            "user_id": user_id,
            "profile_type": profile_type,
        },
    )

    return {row["profile_id"] for row in rows}


def filter_available_profile_suggestions(user_id, suggested_profiles, profile_type="dancer"):
    dismissed_ids = get_dismissed_profile_ids_for_user(user_id, profile_type)
    existing_link_ids = get_existing_profile_link_ids_for_user(user_id, profile_type)

    filtered = []

    for item in suggested_profiles:
        profile = item.get("profile") if isinstance(item, dict) else None
        if not profile:
            continue

        profile_id = profile["id"]

        if profile_id in dismissed_ids:
            continue

        if profile_id in existing_link_ids:
            continue

        filtered.append(item)

    return filtered


def current_user_required():
    user = get_current_user()
    if not user:
        return None
    return user


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




# --- Admin analytics and controversy helpers ---
def ensure_admin_analytics_tables():
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS site_visits (
                    id SERIAL PRIMARY KEY,
                    path TEXT,
                    method TEXT,
                    user_id INTEGER,
                    is_admin INTEGER DEFAULT 0,
                    referrer TEXT,
                    user_agent TEXT,
                    ip_hash TEXT,
                    created_at TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS admin_activity_dismissals (
                    id SERIAL PRIMARY KEY,
                    activity_key TEXT UNIQUE,
                    dismissed_at TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS music_play_events (
                    id SERIAL PRIMARY KEY,
                    media_item_id INTEGER,
                    user_id INTEGER,
                    is_admin INTEGER DEFAULT 0,
                    created_at TEXT
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS site_visits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT,
                    method TEXT,
                    user_id INTEGER,
                    is_admin INTEGER DEFAULT 0,
                    referrer TEXT,
                    user_agent TEXT,
                    ip_hash TEXT,
                    created_at TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS admin_activity_dismissals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activity_key TEXT UNIQUE,
                    dismissed_at TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS music_play_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    media_item_id INTEGER,
                    user_id INTEGER,
                    is_admin INTEGER DEFAULT 0,
                    created_at TEXT
                )
            """))


def anonymous_ip_hash():
    raw_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP", "").strip()
        or request.remote_addr
        or ""
    )
    if not raw_ip:
        return ""
    return hashlib.sha256(raw_ip.encode("utf-8")).hexdigest()[:24]


def dismissed_activity_keys():
    ensure_admin_analytics_tables()
    rows = fetch_all("SELECT activity_key FROM admin_activity_dismissals", {})
    return {row["activity_key"] for row in rows}


def activity_is_visible(activity_key, dismissed_keys):
    return activity_key not in dismissed_keys


def build_admin_activity_feed(limit=30):
    dismissed = dismissed_activity_keys()
    activity = []

    def add_item(activity_key, activity_type, title, description="", target_url="", created_at=""):
        if activity_is_visible(activity_key, dismissed):
            activity.append({
                "activity_key": activity_key,
                "activity_type": activity_type,
                "title": title,
                "description": description,
                "target_url": target_url,
                "created_at": created_at or "",
            })

    accounts = fetch_all("""
        SELECT id, display_name, email, role, created_at
        FROM archive_users
        ORDER BY created_at DESC
        LIMIT 20
    """, {})

    for account in accounts:
        add_item(
            f"account:{account['id']}",
            "New Account",
            account["display_name"] or account["email"] or "New account",
            f"{account['email'] or ''} · role: {account['role'] or 'member'}",
            "/admin/users",
            account["created_at"],
        )

    submissions = fetch_all("""
        SELECT id, submission_type, title, related_to, review_status, created_at
        FROM submissions
        ORDER BY created_at DESC
        LIMIT 30
    """, {})

    for submission in submissions:
        add_item(
            f"submission:{submission['id']}",
            "New Ledger Record",
            submission["title"] or "Untitled ledger record",
            f"{submission['submission_type'] or 'record'} · {submission['review_status'] or 'No status'} · {submission['related_to'] or ''}",
            f"/admin/submissions/{submission['id']}/edit",
            submission["created_at"],
        )

    role_requests = fetch_all("""
        SELECT role_requests.id, role_requests.requested_role, role_requests.status, role_requests.created_at,
               archive_users.display_name, archive_users.email
        FROM role_requests
        JOIN archive_users ON role_requests.user_id = archive_users.id
        ORDER BY role_requests.created_at DESC
        LIMIT 20
    """, {})

    for role_request in role_requests:
        add_item(
            f"role_request:{role_request['id']}",
            "Role Request",
            role_request["display_name"] or role_request["email"] or "Role request",
            f"Requested: {role_request['requested_role']} · Status: {role_request['status']}",
            "/admin/role-requests",
            role_request["created_at"],
        )

    try:
        music_rows = fetch_all("""
            SELECT id, title, artist_or_creator, media_type, created_at
            FROM media_items
            ORDER BY created_at DESC
            LIMIT 20
        """, {})

        for item in music_rows:
            add_item(
                f"music:{item['id']}",
                "Music Added",
                item["title"] or "Untitled music item",
                f"{item['artist_or_creator'] or 'Unknown'} · {item['media_type'] or 'music'}",
                f"/litefeet-music/release/{item['id']}",
                item["created_at"],
            )
    except Exception:
        pass

    activity.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return activity[:limit]


def controversy_reason_and_score(record, counts):
    true_count = int(counts.get("true") or 0)
    false_count = int(counts.get("false") or 0)
    debatable_count = int(counts.get("debatable") or 0)
    total_votes = true_count + false_count + debatable_count

    review_status = (record.get("review_status") or "").strip()
    submission_type = (record.get("submission_type") or "").strip()
    needs_verification = int(record.get("needs_verification") or 0)

    reasons = []
    score = 0

    if review_status == "Disputed":
        reasons.append("Disputed")
        score += 100

    if debatable_count > 0:
        reasons.append("Debatable votes")
        score += 60 + (debatable_count * 5)

    if true_count > 0 and false_count > 0:
        spread = abs(true_count - false_count)
        if spread <= 1:
            reasons.append("Close True/False split")
            score += 50 + total_votes

    if needs_verification == 1:
        # Keep explicit review-worthy records, but do not flood the queue with imported
        # dancer/move seed records that have 0 votes and no controversy yet.
        if submission_type not in {"dancer_profile", "move_info"} or total_votes > 0 or review_status in {"Needs Verification", "Disputed"} and submission_type in {"event", "battle_result", "award_info", "historical_claim"}:
            reasons.append("Flagged for verification")
            score += 25

    if review_status == "Needs Verification" and total_votes > 0:
        reasons.append("Community review active")
        score += 15

    if not reasons:
        return "", 0

    return ", ".join(dict.fromkeys(reasons)), score


def build_controversy_queue():
    ensure_verification_tables()

    submissions = fetch_all("""
        SELECT *
        FROM submissions
        WHERE needs_verification = 1
           OR review_status IN ('Needs Verification', 'Disputed')
           OR id IN (
                SELECT DISTINCT submission_id
                FROM verification_votes
           )
        ORDER BY created_at DESC
    """, {})

    counts_map = get_vote_counts_for_submissions(submissions)
    rows = []

    for submission in submissions:
        counts = counts_map.get(submission["id"], {"true": 0, "false": 0, "debatable": 0})
        reason, score = controversy_reason_and_score(submission, counts)

        if not reason:
            continue

        total_votes = int(counts.get("true") or 0) + int(counts.get("false") or 0) + int(counts.get("debatable") or 0)

        # Avoid showing generic imported dancer/move records with no actual controversy.
        if total_votes == 0 and submission["submission_type"] in {"dancer_profile", "move_info"}:
            continue

        item = dict(submission)
        item["true_count"] = int(counts.get("true") or 0)
        item["false_count"] = int(counts.get("false") or 0)
        item["debatable_count"] = int(counts.get("debatable") or 0)
        item["total_votes"] = total_votes
        item["controversy_reason"] = reason
        item["controversy_score"] = score
        rows.append(item)

    rows.sort(key=lambda item: (item["controversy_score"], item["total_votes"], item.get("created_at") or ""), reverse=True)
    return rows


@app.before_request
def track_public_site_visit():
    if request.endpoint == "static":
        return

    if request.method != "GET":
        return

    if request.path.startswith("/static"):
        return

    ensure_admin_analytics_tables()

    user = current_user()
    user_id = user.get("id") if user else None
    is_admin = 1 if session.get("admin_logged_in") or current_user_is_admin() else 0

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO site_visits (
                    path,
                    method,
                    user_id,
                    is_admin,
                    referrer,
                    user_agent,
                    ip_hash,
                    created_at
                )
                VALUES (
                    :path,
                    :method,
                    :user_id,
                    :is_admin,
                    :referrer,
                    :user_agent,
                    :ip_hash,
                    :created_at
                )
            """),
            {
                "path": request.path,
                "method": request.method,
                "user_id": user_id,
                "is_admin": is_admin,
                "referrer": request.referrer or "",
                "user_agent": request.headers.get("User-Agent", "")[:500],
                "ip_hash": anonymous_ip_hash(),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )


@app.route("/admin/activity/dismiss", methods=["POST"])
def dismiss_admin_activity():
    if not current_user_is_admin():
        return redirect(url_for("admin_login"))

    ensure_admin_analytics_tables()

    activity_key = request.form.get("activity_key", "").strip()
    if activity_key:
        with engine.begin() as conn:
            try:
                conn.execute(
                    text("""
                        INSERT INTO admin_activity_dismissals (
                            activity_key,
                            dismissed_at
                        )
                        VALUES (
                            :activity_key,
                            :dismissed_at
                        )
                    """),
                    {
                        "activity_key": activity_key,
                        "dismissed_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )
            except Exception:
                pass

    return redirect(request.referrer or url_for("admin_home"))



# --- Safe return-to-admin route override ---
@app.before_request
def safe_return_to_admin_override():
    if request.path != "/admin/return-to-admin":
        return

    if not session.get("admin_logged_in") and not current_user_is_admin():
        return redirect(url_for("admin_login"))

    # Clear any public-view/admin-preview flags that may exist.
    for key in [
        "view_site_as_public",
        "viewing_site_as_public",
        "admin_public_view",
        "public_view",
        "force_public_view",
    ]:
        session.pop(key, None)

    return redirect(url_for("admin_home"))


@app.route("/admin")
def admin_home():
    if not current_user_is_admin():
        return redirect(url_for("admin_login"))

    ensure_admin_analytics_tables()
    ensure_music_play_count_columns()

    if engine.dialect.name == "postgresql":
        visits_today = fetch_all("""
            SELECT COUNT(*) AS count
            FROM site_visits
            WHERE created_at >= TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD')
        """, {})[0]["count"]

        hourly_visits = fetch_all("""
            SELECT SUBSTRING(created_at, 1, 13) AS bucket, COUNT(*) AS count
            FROM site_visits
            WHERE created_at >= TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD')
            GROUP BY SUBSTRING(created_at, 1, 13)
            ORDER BY bucket DESC
            LIMIT 24
        """, {})

        daily_visits = fetch_all("""
            SELECT SUBSTRING(created_at, 1, 10) AS bucket, COUNT(*) AS count
            FROM site_visits
            GROUP BY SUBSTRING(created_at, 1, 10)
            ORDER BY bucket DESC
            LIMIT 14
        """, {})
    else:
        visits_today = fetch_all("""
            SELECT COUNT(*) AS count
            FROM site_visits
            WHERE created_at >= date('now')
        """, {})[0]["count"]

        hourly_visits = fetch_all("""
            SELECT substr(created_at, 1, 13) AS bucket, COUNT(*) AS count
            FROM site_visits
            WHERE created_at >= date('now')
            GROUP BY substr(created_at, 1, 13)
            ORDER BY bucket DESC
            LIMIT 24
        """, {})

        daily_visits = fetch_all("""
            SELECT substr(created_at, 1, 10) AS bucket, COUNT(*) AS count
            FROM site_visits
            GROUP BY substr(created_at, 1, 10)
            ORDER BY bucket DESC
            LIMIT 14
        """, {})

    top_pages = fetch_all("""
        SELECT path, COUNT(*) AS count
        FROM site_visits
        WHERE is_admin = 0
        GROUP BY path
        ORDER BY count DESC
        LIMIT 10
    """, {})

    new_accounts_today = fetch_all("""
        SELECT COUNT(*) AS count
        FROM archive_users
        WHERE created_at >= :today
    """, {"today": datetime.now().date().isoformat()})[0]["count"]

    total_accounts = fetch_all("SELECT COUNT(*) AS count FROM archive_users", {})[0]["count"]
    pending_role_requests = fetch_all("SELECT COUNT(*) AS count FROM role_requests WHERE status = 'Pending'", {})[0]["count"]
    pending_submissions = fetch_all("SELECT COUNT(*) AS count FROM submissions WHERE review_status = 'Pending Review'", {})[0]["count"]

    try:
        total_music_releases = fetch_all("SELECT COUNT(*) AS count FROM media_items WHERE media_type = 'music_release'", {})[0]["count"]
        total_ledger_plays = fetch_all("SELECT COALESCE(SUM(play_count), 0) AS count FROM media_items", {})[0]["count"]
    except Exception:
        total_music_releases = 0
        total_ledger_plays = 0

    controversy_queue = build_controversy_queue()
    activity_feed = build_admin_activity_feed()

    return render_template(
        "admin_home.html",
        visits_today=visits_today,
        hourly_visits=hourly_visits,
        daily_visits=daily_visits,
        top_pages=top_pages,
        new_accounts_today=new_accounts_today,
        total_accounts=total_accounts,
        pending_role_requests=pending_role_requests,
        pending_submissions=pending_submissions,
        total_music_releases=total_music_releases,
        total_ledger_plays=total_ledger_plays,
        controversy_count=len(controversy_queue),
        controversy_queue=controversy_queue[:8],
        activity_feed=activity_feed,
    )

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
        status = normalize_people_profile_status(request.form.get("status", "").strip())

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
                "status": normalize_people_profile_status(status),
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







def ensure_person_tier_columns():
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN IF NOT EXISTS public_tier TEXT"))
            conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN IF NOT EXISTS hall_of_fame_status TEXT"))
        else:
            cols = conn.execute(text("PRAGMA table_info(dancer_profiles)")).fetchall()
            existing = {col[1] for col in cols}
            if "public_tier" not in existing:
                conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN public_tier TEXT"))
            if "hall_of_fame_status" not in existing:
                conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN hall_of_fame_status TEXT"))


def ensure_activity_status_column():
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN IF NOT EXISTS activity_status TEXT DEFAULT 'unknown'"))
        else:
            cols = conn.execute(text("PRAGMA table_info(dancer_profiles)")).fetchall()
            existing = {col[1] for col in cols}
            if "activity_status" not in existing:
                conn.execute(text("ALTER TABLE dancer_profiles ADD COLUMN activity_status TEXT DEFAULT 'unknown'"))


def ensure_media_items_table():
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS media_items (
                        id SERIAL PRIMARY KEY,
                        media_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        artist_or_creator TEXT,
                        url TEXT NOT NULL,
                        platform TEXT,
                        release_date TEXT,
                        event_name TEXT,
                        description TEXT,
                        status TEXT DEFAULT 'Published',
                        created_at TEXT
                    )
                    """
                )
            )
        else:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS media_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        media_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        artist_or_creator TEXT,
                        url TEXT NOT NULL,
                        platform TEXT,
                        release_date TEXT,
                        event_name TEXT,
                        description TEXT,
                        status TEXT DEFAULT 'Published',
                        created_at TEXT
                    )
                    """
                )
            )


def detect_media_platform(url):
    value = (url or "").lower()

    if "youtube.com" in value or "youtu.be" in value or "music.youtube.com" in value:
        return "YouTube"
    if "soundcloud.com" in value:
        return "SoundCloud"
    if "spotify.com" in value:
        return "Spotify"
    if "music.apple.com" in value or "itunes.apple.com" in value:
        return "Apple Music"
    if "untitled.stream" in value:
        return "Untitled"

    return "Link"



def spotify_embed_url(url):
    parsed = urlparse(url or "")
    parts = [part for part in parsed.path.split("/") if part]

    if "open.spotify.com" not in parsed.netloc.lower():
        return ""

    if len(parts) >= 2:
        return f"https://open.spotify.com/embed/{parts[0]}/{parts[1]}"

    return ""


def apple_music_embed_url(url):
    parsed = urlparse(url or "")

    if "music.apple.com" not in parsed.netloc.lower():
        return ""

    return "https://embed.music.apple.com" + parsed.path + (("?" + parsed.query) if parsed.query else "")


@app.template_filter("media_embed_url")


def extract_youtube_video_id(url):
    value = (url or "").strip()
    if not value:
        return ""

    parsed = urlparse(value)
    host = parsed.netloc.lower().replace("www.", "")
    path_parts = [part for part in parsed.path.split("/") if part]

    if host in {"youtube.com", "music.youtube.com", "m.youtube.com"}:
        query = parse_qs(parsed.query)
        if query.get("v"):
            return query["v"][0]

        if path_parts and path_parts[0] in {"shorts", "live", "embed"} and len(path_parts) > 1:
            return path_parts[1]

    if host == "youtu.be" and path_parts:
        return path_parts[0]

    return ""


def clean_youtube_watch_url(url):
    video_id = extract_youtube_video_id(url)
    if not video_id:
        return url or ""

    return f"https://www.youtube.com/watch?v={video_id}"


def youtube_embed_url(url):
    video_id = extract_youtube_video_id(url)
    if not video_id:
        return ""

    return f"https://www.youtube.com/embed/{video_id}"


def fetch_youtube_metadata(url):
    video_id = extract_youtube_video_id(url)
    if not video_id:
        return {}

    watch_url = clean_youtube_watch_url(url)
    oembed_url = "https://www.youtube.com/oembed?url=" + quote(watch_url, safe="") + "&format=json"

    try:
        response = requests.get(
            oembed_url,
            timeout=10,
            headers={"User-Agent": "LiteFeetLedger/1.0"},
        )

        if response.status_code >= 300:
            return {
                "title": "",
                "artist_or_creator": "",
                "platform": "YouTube",
                "url": watch_url,
                "embed_url": youtube_embed_url(watch_url),
                "description": "Imported from YouTube.",
                "tracks": [],
            }

        data = response.json()

        return {
            "title": (data.get("title") or "").strip(),
            "artist_or_creator": (data.get("author_name") or "").strip(),
            "platform": "YouTube",
            "url": watch_url,
            "embed_url": youtube_embed_url(watch_url),
            "description": "Imported from YouTube.",
            "tracks": [],
        }

    except Exception as exc:
        print("YouTube metadata pull failed:", exc)
        return {
            "title": "",
            "artist_or_creator": "",
            "platform": "YouTube",
            "url": watch_url,
            "embed_url": youtube_embed_url(watch_url),
            "description": "Imported from YouTube.",
            "tracks": [],
        }


def media_embed_url(url):
    platform = detect_media_platform(url)

    if platform == "YouTube":
        return youtube_embed_url(url)
    if platform == "SoundCloud":
        return (
            "https://w.soundcloud.com/player/?url="
            + quote(url or "", safe="")
            + "&auto_play=false&hide_related=true&show_comments=false"
            + "&show_user=true&show_reposts=false&show_teaser=false&visual=false"
        )
    if platform == "Spotify":
        return spotify_embed_url(url)
    if platform == "Apple Music":
        return apple_music_embed_url(url)

    return ""


@app.template_filter("media_platform")
def media_platform(url):
    return detect_media_platform(url)


@app.route("/admin/media", methods=["GET", "POST"])
def admin_media():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login", next=request.path))

    ensure_media_items_table()

    if request.method == "POST":
        media_type = request.form.get("media_type", "").strip()
        submission_type = request.form.get("submission_type", "single").strip() or "single"
        title = request.form.get("title", "").strip()
        artist_or_creator = request.form.get("artist_or_creator", "").strip()
        url = request.form.get("url", "").strip()
        release_date = request.form.get("release_date", "").strip()
        event_name = request.form.get("event_name", "").strip()
        description = request.form.get("description", "").strip()
        embed_code = request.form.get("embed_code", "").strip()
        embed_url = extract_embed_src(embed_code)
        status = request.form.get("status", "Published").strip() or "Published"
        platform = detect_media_platform(url)

        if media_type and title and url:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO media_items (
                            media_type,
                            title,
                            artist_or_creator,
                            url,
                            platform,
                            release_date,
                            event_name,
                            description,
                            status,
                            created_at
                        )
                        VALUES (
                            :media_type,
                            :title,
                            :artist_or_creator,
                            :url,
                            :platform,
                            :release_date,
                            :event_name,
                            :description,
                            :status,
                            :created_at
                        )
                        """
                    ),
                    {
                        "media_type": media_type,
                        "title": title,
                        "artist_or_creator": artist_or_creator,
                        "url": source_url,
                        "platform": platform,
                        "release_date": release_date,
                        "event_name": event_name,
                        "description": description,
                        "status": normalize_people_profile_status(status),
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )

        return redirect(url_for("admin_media"))

    media_items = fetch_all(
        """
        SELECT *
        FROM media_items
        ORDER BY
            CASE WHEN release_date IS NULL OR release_date = '' THEN created_at ELSE release_date END DESC,
            created_at DESC
        """
    )

    return render_template("admin_media.html", media_items=media_items)


@app.route("/admin/media/<int:item_id>/delete", methods=["POST"])
def admin_media_delete(item_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login", next=request.path))

    ensure_media_items_table()

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM media_items WHERE id = :id"),
            {"id": item_id},
        )

    return redirect(url_for("admin_media"))


@app.route("/")
def home():
    ensure_media_items_table()

    latest_battle_videos = fetch_all(
        """
        SELECT *
        FROM media_items
        WHERE media_type = 'battle_video'
          AND status = 'Published'
        ORDER BY
            CASE WHEN release_date IS NULL OR release_date = '' THEN created_at ELSE release_date END DESC,
            created_at DESC
        LIMIT 6
        """
    )

    latest_music_releases = fetch_all(
        """
        SELECT *
        FROM media_items
        WHERE media_type = 'music_release'
          AND status = 'Published'
        ORDER BY
            CASE WHEN release_date IS NULL OR release_date = '' THEN created_at ELSE release_date END DESC,
            created_at DESC
        LIMIT 20
        """
    )

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

    upcoming_calendar_items = list(upcoming_soon or []) + list(upcoming_later or [])
    next_calendar_item = upcoming_calendar_items[0] if upcoming_calendar_items else None
    homepage_calendar_items = upcoming_calendar_items[1:4] if len(upcoming_calendar_items) > 1 else []

    return render_template(
        "home.html",
        latest_battle_videos=latest_battle_videos,
        latest_music_releases=latest_music_releases,
        next_calendar_item=next_calendar_item,
        homepage_calendar_items=homepage_calendar_items,
    )


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
    ensure_account_review_columns()

    users = fetch_all(
        """
        SELECT *
        FROM archive_users
        ORDER BY created_at DESC
        """
    )

    grouped_users = {
        "pending": [],
        "approved": [],
        "rejected": [],
    }

    for user in users:
        status = user["account_status"] or "pending"
        if status not in grouped_users:
            status = "pending"
        grouped_users[status].append(user)

    return render_template(
        "admin_users.html",
        users=users,
        grouped_users=grouped_users,
    )




@app.route("/admin/users/<int:user_id>")
def admin_user_detail(user_id):
    ensure_account_review_columns()
    ensure_profile_link_tables()

    user_rows = fetch_all(
        """
        SELECT *
        FROM archive_users
        WHERE id = :user_id
        LIMIT 1
        """,
        {"user_id": user_id},
    )

    if not user_rows:
        flash("User account not found.", "error")
        return redirect(url_for("admin_users"))

    user = user_rows[0]

    suggested_profiles = find_similar_dancer_profiles_for_user(user, limit=12)
    suggested_profiles = filter_available_profile_suggestions(user_id, suggested_profiles)

    profile_links = fetch_all(
        """
        SELECT profile_account_links.*,
               dancer_profiles.dance_name,
               dancer_profiles.real_name,
               dancer_profiles.team_affiliation,
               dancer_profiles.profile_slug
        FROM profile_account_links
        JOIN dancer_profiles ON profile_account_links.profile_id = dancer_profiles.id
        WHERE profile_account_links.user_id = :user_id
        AND profile_account_links.profile_type = 'dancer'
        ORDER BY
            CASE profile_account_links.status
                WHEN 'approved' THEN 1
                WHEN 'pending' THEN 2
                WHEN 'rejected' THEN 3
                ELSE 4
            END,
            profile_account_links.requested_at DESC
        """,
        {"user_id": user_id},
    )

    linked_profile_ids = {link["profile_id"] for link in profile_links}

    return render_template(
        "admin_user_detail.html",
        user=user,
        suggested_profiles=suggested_profiles,
        profile_links=profile_links,
        linked_profile_ids=linked_profile_ids,
    )


@app.route("/admin/users/<int:user_id>/profile-links/<int:profile_id>/attach", methods=["POST"])
def admin_attach_profile_to_user(user_id, profile_id):
    ensure_account_review_columns()
    ensure_profile_link_tables()

    user_rows = fetch_all(
        """
        SELECT id, display_name, email
        FROM archive_users
        WHERE id = :user_id
        LIMIT 1
        """,
        {"user_id": user_id},
    )

    if not user_rows:
        flash("User account not found.", "error")
        return redirect(url_for("admin_users"))

    profile_rows = fetch_all(
        """
        SELECT id, dance_name, real_name
        FROM dancer_profiles
        WHERE id = :profile_id
        LIMIT 1
        """,
        {"profile_id": profile_id},
    )

    if not profile_rows:
        flash("Profile card not found.", "error")
        return redirect(url_for("admin_user_detail", user_id=user_id))

    existing = fetch_all(
        """
        SELECT id
        FROM profile_account_links
        WHERE user_id = :user_id
        AND profile_type = 'dancer'
        AND profile_id = :profile_id
        LIMIT 1
        """,
        {
            "user_id": user_id,
            "profile_id": profile_id,
        },
    )

    now_value = datetime.now().isoformat(timespec="seconds")
    admin_note = request.form.get("admin_note", "").strip() or "Attached by admin."

    if existing:
        execute_query(
            """
            UPDATE profile_account_links
            SET status = 'approved',
                reviewed_at = :reviewed_at,
                admin_note = :admin_note
            WHERE id = :link_id
            """,
            {
                "reviewed_at": now_value,
                "admin_note": admin_note,
                "link_id": existing[0]["id"],
            },
        )
    else:
        execute_query(
            """
            INSERT INTO profile_account_links (
                user_id,
                profile_type,
                profile_id,
                status,
                requested_at,
                reviewed_at,
                admin_note
            )
            VALUES (
                :user_id,
                'dancer',
                :profile_id,
                'approved',
                :requested_at,
                :reviewed_at,
                :admin_note
            )
            """,
            {
                "user_id": user_id,
                "profile_id": profile_id,
                "requested_at": now_value,
                "reviewed_at": now_value,
                "admin_note": admin_note,
            },
        )

    flash("Profile card attached to account.", "success")
    return redirect(url_for("admin_user_detail", user_id=user_id))




@app.route("/admin/users/<int:user_id>/profile-links/<int:profile_id>/dismiss", methods=["POST"])
def admin_dismiss_profile_suggestion(user_id, profile_id):
    ensure_profile_link_tables()
    ensure_profile_match_dismissals_table()

    user_rows = fetch_all(
        """
        SELECT id
        FROM archive_users
        WHERE id = :user_id
        LIMIT 1
        """,
        {"user_id": user_id},
    )

    if not user_rows:
        flash("User account not found.", "error")
        return redirect(url_for("admin_users"))

    profile_rows = fetch_all(
        """
        SELECT id
        FROM dancer_profiles
        WHERE id = :profile_id
        LIMIT 1
        """,
        {"profile_id": profile_id},
    )

    if not profile_rows:
        flash("Profile card not found.", "error")
        return redirect(url_for("admin_user_detail", user_id=user_id))

    existing = fetch_all(
        """
        SELECT id
        FROM profile_match_dismissals
        WHERE user_id = :user_id
        AND profile_type = 'dancer'
        AND profile_id = :profile_id
        LIMIT 1
        """,
        {
            "user_id": user_id,
            "profile_id": profile_id,
        },
    )

    if not existing:
        execute_query(
            """
            INSERT INTO profile_match_dismissals (
                user_id,
                profile_type,
                profile_id,
                dismissed_at,
                dismissed_by,
                admin_note
            )
            VALUES (
                :user_id,
                'dancer',
                :profile_id,
                :dismissed_at,
                'admin',
                :admin_note
            )
            """,
            {
                "user_id": user_id,
                "profile_id": profile_id,
                "dismissed_at": datetime.now().isoformat(timespec="seconds"),
                "admin_note": request.form.get("admin_note", "").strip(),
            },
        )

    flash("Suggested profile card dismissed for this account.", "success")
    return redirect(url_for("admin_user_detail", user_id=user_id))


@app.route("/admin/users/<int:user_id>/profile-links/<int:link_id>/status", methods=["POST"])
def admin_update_user_profile_link_status(user_id, link_id):
    ensure_profile_link_tables()

    status = request.form.get("status", "").strip()
    admin_note = request.form.get("admin_note", "").strip()

    if status not in {"pending", "approved", "rejected"}:
        flash("Invalid profile link status.", "error")
        return redirect(url_for("admin_user_detail", user_id=user_id))

    execute_query(
        """
        UPDATE profile_account_links
        SET status = :status,
            reviewed_at = :reviewed_at,
            admin_note = :admin_note
        WHERE id = :link_id
        AND user_id = :user_id
        """,
        {
            "status": status,
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            "admin_note": admin_note,
            "link_id": link_id,
            "user_id": user_id,
        },
    )

    flash("Profile link status updated.", "success")
    return redirect(url_for("admin_user_detail", user_id=user_id))


@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
def update_user_role(user_id):
    ensure_account_review_columns()

    new_role = request.form.get("role", "").strip()

    allowed_roles = {
        "contributor",
        "affiliate_host",
        "admin",
        "suspended",
    }

    if new_role not in allowed_roles:
        flash("Invalid role selected.", "error")
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

    flash("User role updated.", "success")
    return redirect(url_for("admin_users"))




def send_account_approval_email(user):
    resend_api_key = os.environ.get("RESEND_API_KEY", "").strip()

    if not resend_api_key:
        print("Account approval email skipped: RESEND_API_KEY is not configured.")
        return False

    recipient = (user["email"] or "").strip()

    if not recipient or "@" not in recipient:
        print("Account approval email skipped: user email missing.")
        return False

    sender = (
        os.environ.get("ACCOUNT_APPROVAL_EMAIL_FROM", "").strip()
        or os.environ.get("PROFILE_SUGGESTION_EMAIL_FROM", "").strip()
        or os.environ.get("PROOF_EMAIL_FROM", "LiteFeet Ledger <proof@thelitefeetvault.com>").strip()
    )

    if not sender:
        print("Account approval email skipped: sender missing.")
        return False

    display_name = user["display_name"] or "there"
    role = (user["role"] or "contributor").replace("_", " ").title()
    site_url = get_public_site_url()
    account_url = f"{site_url}/account" if site_url else "/account"

    subject = "Your LiteFeet Ledger account was approved"

    body = f"""Hi {display_name},

Your LiteFeet Ledger account has been approved.

Account role: {role}

You can now log in and use your approved account features here:
{account_url}

If you believe your account should be connected to an existing dancer or producer profile, use the profile connection option inside your account.

- LiteFeet Ledger
"""

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "text": body,
        },
        timeout=20,
    )

    if response.status_code >= 300:
        print(f"Account approval email failed: {response.status_code} {response.text}")
        return False

    return True


@app.route("/admin/users/<int:user_id>/status", methods=["POST"])
def update_user_status(user_id):
    ensure_account_review_columns()

    new_status = request.form.get("account_status", "").strip()
    note = request.form.get("account_status_note", "").strip()

    allowed_statuses = {
        "pending",
        "approved",
        "rejected",
    }

    if new_status not in allowed_statuses:
        flash("Invalid account status selected.", "error")
        return redirect(url_for("admin_users"))

    user_rows = fetch_all(
        """
        SELECT id, display_name, email, role, account_status
        FROM archive_users
        WHERE id = :user_id
        LIMIT 1
        """,
        {"user_id": user_id},
    )

    if not user_rows:
        flash("User account not found.", "error")
        return redirect(url_for("admin_users"))

    user_before = user_rows[0]
    old_status = user_before["account_status"] or "pending"

    execute_query(
        """
        UPDATE archive_users
        SET account_status = :account_status,
            account_status_note = :account_status_note
        WHERE id = :user_id
        """,
        {
            "account_status": new_status,
            "account_status_note": note,
            "user_id": user_id,
        },
    )

    flash("Account status updated.", "success")

    if old_status != "approved" and new_status == "approved":
        try:
            sent = send_account_approval_email(user_before)
            if sent:
                flash("Approval email sent.", "success")
            else:
                flash("Account approved, but approval email was skipped. Check email settings.", "error")
        except Exception as exc:
            print("Account approval email failed:", exc)
            flash("Account approved, but the approval email failed.", "error")

    return redirect(url_for("admin_users"))





@app.route("/account/profile-link")
def account_profile_link():
    user = current_user_required()
    if not user:
        return redirect(url_for("account_login"))

    ensure_profile_link_tables()

    existing_links = fetch_all(
        """
        SELECT profile_account_links.*,
               dancer_profiles.dance_name,
               dancer_profiles.real_name,
               dancer_profiles.team_affiliation
        FROM profile_account_links
        LEFT JOIN dancer_profiles ON profile_account_links.profile_id = dancer_profiles.id
        WHERE profile_account_links.user_id = :user_id
        AND profile_account_links.profile_type = 'dancer'
        ORDER BY profile_account_links.requested_at DESC
        """,
        {"user_id": user["id"]},
    )

    suggested_profiles = find_similar_dancer_profiles_for_user(user)
    suggested_profiles = filter_available_profile_suggestions(user["id"], suggested_profiles)

    return render_template(
        "account_profile_link.html",
        user=user,
        suggested_profiles=suggested_profiles,
        existing_links=existing_links,
    )


@app.route("/account/profile-link/<int:profile_id>/request", methods=["POST"])
def request_profile_link(profile_id):
    user = current_user_required()
    if not user:
        return redirect(url_for("account_login"))

    ensure_profile_link_tables()

    profile_rows = fetch_all(
        """
        SELECT id
        FROM dancer_profiles
        WHERE id = :profile_id
        LIMIT 1
        """,
        {"profile_id": profile_id},
    )

    if not profile_rows:
        flash("Profile card not found.", "error")
        return redirect(url_for("account_profile_link"))

    existing = fetch_all(
        """
        SELECT id
        FROM profile_account_links
        WHERE user_id = :user_id
        AND profile_type = 'dancer'
        AND profile_id = :profile_id
        LIMIT 1
        """,
        {
            "user_id": user["id"],
            "profile_id": profile_id,
        },
    )

    if existing:
        flash("This profile connection is already in review.", "success")
        return redirect(url_for("account_profile_link"))

    execute_query(
        """
        INSERT INTO profile_account_links (
            user_id,
            profile_type,
            profile_id,
            status,
            requested_at,
            admin_note
        )
        VALUES (
            :user_id,
            'dancer',
            :profile_id,
            'pending',
            :requested_at,
            :admin_note
        )
        """,
        {
            "user_id": user["id"],
            "profile_id": profile_id,
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "admin_note": "Requested by account holder.",
        },
    )

    flash("Profile connection request submitted.", "success")
    return redirect(url_for("account_profile_link"))


@app.route("/account/profile-visibility", methods=["GET", "POST"])
def account_profile_visibility():
    user = current_user_required()
    if not user:
        return redirect(url_for("account_login"))

    ensure_profile_link_tables()

    approved_links = fetch_all(
        """
        SELECT profile_account_links.*,
               dancer_profiles.dance_name,
               dancer_profiles.real_name
        FROM profile_account_links
        JOIN dancer_profiles ON profile_account_links.profile_id = dancer_profiles.id
        WHERE profile_account_links.user_id = :user_id
        AND profile_account_links.profile_type = 'dancer'
        AND profile_account_links.status = 'approved'
        ORDER BY dancer_profiles.dance_name ASC
        """,
        {"user_id": user["id"]},
    )

    if request.method == "POST":
        profile_id = request.form.get("profile_id", "").strip()
        field_name = request.form.get("field_name", "").strip()
        reason = request.form.get("reason", "").strip()

        approved_profile_ids = {str(link["profile_id"]) for link in approved_links}

        if profile_id not in approved_profile_ids:
            flash("You can only request changes for an approved linked profile.", "error")
            return redirect(url_for("account_profile_visibility"))

        if not field_name:
            flash("Add the profile detail you want reviewed.", "error")
            return redirect(url_for("account_profile_visibility"))

        execute_query(
            """
            INSERT INTO profile_visibility_requests (
                user_id,
                profile_type,
                profile_id,
                field_name,
                requested_action,
                reason,
                public_profile_status,
                ledger_record_status,
                created_at
            )
            VALUES (
                :user_id,
                'dancer',
                :profile_id,
                :field_name,
                'hide_from_public_profile',
                :reason,
                'pending',
                'retained',
                :created_at
            )
            """,
            {
                "user_id": user["id"],
                "profile_id": int(profile_id),
                "field_name": field_name,
                "reason": reason,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

        flash("Visibility request submitted. Ledger records remain retained unless separately corrected or disputed.", "success")
        return redirect(url_for("account_profile_visibility"))

    requests = fetch_all(
        """
        SELECT profile_visibility_requests.*,
               dancer_profiles.dance_name,
               dancer_profiles.real_name
        FROM profile_visibility_requests
        JOIN dancer_profiles ON profile_visibility_requests.profile_id = dancer_profiles.id
        WHERE profile_visibility_requests.user_id = :user_id
        ORDER BY profile_visibility_requests.created_at DESC
        """,
        {"user_id": user["id"]},
    )

    return render_template(
        "account_profile_visibility.html",
        user=user,
        approved_links=approved_links,
        requests=requests,
    )


@app.route("/admin/profile-links")
def admin_profile_links():
    ensure_profile_link_tables()

    links = fetch_all(
        """
        SELECT profile_account_links.*,
               archive_users.display_name,
               archive_users.email,
               archive_users.organization_name,
               dancer_profiles.dance_name,
               dancer_profiles.real_name,
               dancer_profiles.team_affiliation
        FROM profile_account_links
        JOIN archive_users ON profile_account_links.user_id = archive_users.id
        JOIN dancer_profiles ON profile_account_links.profile_id = dancer_profiles.id
        WHERE profile_account_links.profile_type = 'dancer'
        ORDER BY profile_account_links.requested_at DESC
        """
    )

    grouped_links = {
        "pending": [],
        "approved": [],
        "rejected": [],
    }

    for link in links:
        status = link["status"] or "pending"
        if status not in grouped_links:
            status = "pending"
        grouped_links[status].append(link)

    return render_template("admin_profile_links.html", grouped_links=grouped_links)


@app.route("/admin/profile-links/<int:link_id>/status", methods=["POST"])
def admin_update_profile_link_status(link_id):
    ensure_profile_link_tables()

    status = request.form.get("status", "").strip()
    admin_note = request.form.get("admin_note", "").strip()

    if status not in {"pending", "approved", "rejected"}:
        flash("Invalid profile link status.", "error")
        return redirect(url_for("admin_profile_links"))

    execute_query(
        """
        UPDATE profile_account_links
        SET status = :status,
            reviewed_at = :reviewed_at,
            admin_note = :admin_note
        WHERE id = :link_id
        """,
        {
            "status": status,
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            "admin_note": admin_note,
            "link_id": link_id,
        },
    )

    flash("Profile link request updated.", "success")
    return redirect(url_for("admin_profile_links"))


@app.route("/admin/profile-visibility-requests")
def admin_profile_visibility_requests():
    ensure_profile_link_tables()

    requests = fetch_all(
        """
        SELECT profile_visibility_requests.*,
               archive_users.display_name,
               archive_users.email,
               dancer_profiles.dance_name,
               dancer_profiles.real_name
        FROM profile_visibility_requests
        JOIN archive_users ON profile_visibility_requests.user_id = archive_users.id
        JOIN dancer_profiles ON profile_visibility_requests.profile_id = dancer_profiles.id
        ORDER BY profile_visibility_requests.created_at DESC
        """
    )

    return render_template("admin_profile_visibility_requests.html", requests=requests)


@app.route("/admin/profile-visibility-requests/<int:request_id>/status", methods=["POST"])
def admin_update_profile_visibility_request(request_id):
    ensure_profile_link_tables()

    public_profile_status = request.form.get("public_profile_status", "").strip()
    admin_note = request.form.get("admin_note", "").strip()

    if public_profile_status not in {"pending", "approved", "rejected"}:
        flash("Invalid visibility request status.", "error")
        return redirect(url_for("admin_profile_visibility_requests"))

    execute_query(
        """
        UPDATE profile_visibility_requests
        SET public_profile_status = :public_profile_status,
            ledger_record_status = 'retained',
            reviewed_at = :reviewed_at,
            admin_note = :admin_note
        WHERE id = :request_id
        """,
        {
            "public_profile_status": public_profile_status,
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            "admin_note": admin_note,
            "request_id": request_id,
        },
    )

    flash("Visibility request updated. Ledger record status remains retained.", "success")
    return redirect(url_for("admin_profile_visibility_requests"))


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



@app.route("/calendar/add", methods=["GET", "POST"])
@app.route("/events/submit", methods=["GET", "POST"])
def submit_event():
    ensure_phase2_ledger_tables()

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
            errors.append("Add the calendar item name.")

        if not event_date:
            errors.append("Add the date.")

        if not event_time:
            errors.append("Add the time.")

        if len(event_location) < 2:
            errors.append("Add the location.")

        if errors:
            return render_template("event_submit.html", errors=errors), 400

        is_affiliate = current_user_is_affiliate_host()
        user = current_user()
        review_status = "Community Supported" if is_affiliate else "Pending Review"

        details = [
            {"label": "Event Timing", "value": form_data.get("event_timing", "").strip()},
            {"label": "Calendar Type", "value": form_data.get("calendar_type", "").strip()},
            {"label": "Organization Name", "value": event_org},
            {"label": "Event Name", "value": event_name},
            {"label": "Event Date", "value": event_date},
            {"label": "Event Time", "value": event_time},
            {"label": "Event Location", "value": event_location},
            {"label": "Borough", "value": form_data.get("borough", "").strip()},
            {"label": "Venue Name", "value": form_data.get("venue_name", "").strip()},
            {"label": "Cost", "value": form_data.get("cost_text", "").strip()},
            {"label": "Recurring Rule", "value": form_data.get("recurrence_rule", "").strip()},
            {"label": "Host Names", "value": form_data.get("host_names", "").strip()},
            {"label": "DJ Names", "value": form_data.get("dj_names", "").strip()},
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

        submitter_name = form_data.get("submitter_name", "").strip()
        contact = form_data.get("contact", "").strip()

        if user:
            submitter_name = submitter_name or user["display_name"] or ""
            contact = contact or user["email"] or ""

        now_value = datetime.now().isoformat(timespec="seconds")

        submission_id = phase2_safe_insert_and_get_id(
            "submissions",
            {
                "submission_type": "event",
                "title": event_name,
                "related_to": event_org,
                "source_url": form_data.get("source_url", "").strip() or form_data.get("flyer_url", "").strip(),
                "submitter_name": submitter_name,
                "submitter_role": form_data.get("submitter_role", "").strip(),
                "contact": contact,
                "needs_verification": 0 if is_affiliate else 1,
                "review_status": review_status,
                "details_json": json.dumps(details, ensure_ascii=False),
                "created_at": now_value,
                "contributor_user_id": user["id"] if user else None,
                "anonymous_submission": 0,
            },
        )

        upsert_calendar_metadata(submission_id, form_data)

        return redirect(url_for("event_detail", event_id=submission_id))

    return render_template("event_submit.html", errors=[])



@app.route("/calendar")
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




@app.route("/dancers")
def dancers_index_redirect():
    return redirect(url_for("dancers"), code=302)


@app.route("/people/dancers/create")
def people_dancers_create_redirect():
    return redirect(url_for("create_dancer_profile"), code=302)


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
@app.route("/people-teams")
@app.route("/people-and-teams")
@app.route("/people/dancers")
def dancers():
    for fn_name in [
        "ensure_person_role_columns",
        "ensure_profile_slug_column",
        "ensure_profile_alias_columns",
    ]:
        fn = globals().get(fn_name)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    rows = fetch_all(
        """
        SELECT
            id,
            user_id,
            dance_name,
            real_name,
            team_affiliation,
            borough_scene,
            bio,
            source_url,
            status,
            created_at,
            role_tags,
            profile_slug,
            recent_battle,
            aliases,
            era,
            style_notes,
            signature_moves,
            battle_history,
            legacy_notes
        FROM dancer_profiles
        ORDER BY LOWER(COALESCE(dance_name, '')) ASC
        """,
        {},
    )

    profiles = []
    for row in rows:
        item = dict(row)
        item["directory_status"] = normalize_people_profile_status(item.get("status"))
        profiles.append(item)

    return render_template(
        "dancers.html",
        profiles=profiles,
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




def fetch_music_releases_for_profile_name(profile_name):
    if not profile_name:
        return []

    ensure_media_items_table()
    ensure_music_play_count_columns()
    ensure_music_platform_stat_columns()

    return fetch_all(
        """
        SELECT *
        FROM media_items
        WHERE media_type = 'music_release'
          AND status = 'Published'
          AND LOWER(COALESCE(artist_or_creator, '')) = LOWER(:profile_name)
        ORDER BY
            CASE WHEN release_date IS NULL OR release_date = '' THEN created_at ELSE release_date END DESC
        LIMIT 20
        """,
        {"profile_name": profile_name},
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
    profile_releases = fetch_music_releases_for_profile_name(profile_name)

    return render_template(
        "dancer_profile_detail.html",
        profile=profile,
        flowers=flowers,
        suggestions=suggestions,
        ledger_mentions=ledger_mentions,
        similar_profiles=similar_profiles,
        has_enrichment=has_enrichment,
        profile_releases=profile_releases,
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




def split_email_list(value):
    emails = []
    seen = set()

    for raw_email in (value or "").replace(";", ",").split(","):
        email = raw_email.strip()
        if not email or "@" not in email:
            continue

        lowered = email.lower()
        if lowered not in seen:
            emails.append(email)
            seen.add(lowered)

    return emails


def get_public_site_url():
    configured_url = os.environ.get("PUBLIC_SITE_URL", "").strip().rstrip("/")
    if configured_url:
        return configured_url

    try:
        return request.url_root.rstrip("/")
    except RuntimeError:
        return ""


def get_dancer_profile_notification_recipients(dancer_id):
    ensure_profile_link_tables()

    rows = fetch_all(
        """
        SELECT archive_users.email
        FROM profile_account_links
        JOIN archive_users ON profile_account_links.user_id = archive_users.id
        WHERE profile_account_links.profile_type = 'dancer'
        AND profile_account_links.profile_id = :dancer_id
        AND profile_account_links.status = 'approved'
        AND archive_users.email IS NOT NULL
        AND archive_users.email != ''
        """,
        {"dancer_id": dancer_id},
    )

    recipients = []
    seen = set()

    for row in rows:
        email = (row["email"] or "").strip()
        if not email or "@" not in email:
            continue

        lowered = email.lower()
        if lowered not in seen:
            recipients.append(email)
            seen.add(lowered)

    # Fallback keeps unclaimed profiles from losing notifications completely.
    fallback_to = (
        os.environ.get("PROFILE_SUGGESTION_EMAIL_TO", "").strip()
        or os.environ.get("PROOF_EMAIL_TO", "").strip()
    )

    for email in split_email_list(fallback_to):
        lowered = email.lower()
        if lowered not in seen:
            recipients.append(email)
            seen.add(lowered)

    return recipients


def send_profile_suggestion_email(dancer_id, suggestion_text, submitter_name="", submitter_role="", contact="", source_url=""):
    resend_api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not resend_api_key:
        print("Profile suggestion email skipped: RESEND_API_KEY is not configured.")
        return False

    sender = (
        os.environ.get("PROFILE_SUGGESTION_EMAIL_FROM", "").strip()
        or os.environ.get("PROOF_EMAIL_FROM", "LiteFeet Ledger <proof@thelitefeetvault.com>").strip()
    )

    recipients = get_dancer_profile_notification_recipients(dancer_id)

    if not sender or not recipients:
        print("Profile suggestion email skipped: sender or recipients missing.")
        return False

    profile_rows = fetch_all(
        """
        SELECT id, dance_name, real_name, profile_slug
        FROM dancer_profiles
        WHERE id = :dancer_id
        LIMIT 1
        """,
        {"dancer_id": dancer_id},
    )

    if profile_rows:
        profile = profile_rows[0]
        profile_name = profile["dance_name"] or profile["real_name"] or f"Profile #{dancer_id}"
    else:
        profile_name = f"Profile #{dancer_id}"

    site_url = get_public_site_url()
    profile_url = f"{site_url}/dancers/{dancer_id}" if site_url else f"/dancers/{dancer_id}"
    admin_url = f"{site_url}/admin/dancer-feedback" if site_url else "/admin/dancer-feedback"

    subject = f"New suggestion on your LiteFeet Ledger profile: {profile_name}"

    body = f"""A new community suggestion was submitted for this LiteFeet Ledger profile.

Profile: {profile_name}
Profile link: {profile_url}

Suggestion:
{suggestion_text}

Submitted by: {submitter_name or 'Not provided'}
Submitter role: {submitter_role or 'Not provided'}
Contact: {contact or 'Not provided'}
Source: {source_url or 'Not provided'}

This suggestion is pending admin review before it appears publicly.

Admin review:
{admin_url}
"""

    payload = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "text": body,
    }

    if contact and "@" in contact:
        payload["reply_to"] = contact

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )

    if response.status_code >= 300:
        print(f"Profile suggestion email failed: {response.status_code} {response.text}")
        return False

    return True


@app.route("/dancers/<int:dancer_id>/suggest", methods=["POST"])
@app.route("/dancers/<int:dancer_id>/suggestions", methods=["POST"])
def suggest_dancer_update(dancer_id):
    suggestion_text = (
        request.form.get("suggestion_text", "").strip()
        or request.form.get("message", "").strip()
    )
    submitter_name = request.form.get("submitter_name", "").strip()
    submitter_role = request.form.get("submitter_role", "").strip()
    contact = request.form.get("contact", "").strip()
    source_url = request.form.get("source_url", "").strip()

    if not suggestion_text:
        flash("Add a suggestion before submitting.", "error")
        return redirect(url_for("dancer_profile_detail_by_id", dancer_id=dancer_id))

    profile_rows = fetch_all(
        """
        SELECT id
        FROM dancer_profiles
        WHERE id = :dancer_id
        LIMIT 1
        """,
        {"dancer_id": dancer_id},
    )

    if not profile_rows:
        flash("Dancer profile not found.", "error")
        return redirect(url_for("dancers"))

    execute_query(
        """
        INSERT INTO dancer_suggestions (
            dancer_profile_id,
            suggestion_text,
            submitter_name,
            submitter_role,
            contact,
            source_url,
            status,
            created_at
        )
        VALUES (
            :dancer_profile_id,
            :suggestion_text,
            :submitter_name,
            :submitter_role,
            :contact,
            :source_url,
            'Pending Review',
            :created_at
        )
        """,
        {
            "dancer_profile_id": dancer_id,
            "suggestion_text": suggestion_text,
            "submitter_name": submitter_name,
            "submitter_role": submitter_role,
            "contact": contact,
            "source_url": source_url,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
    )

    try:
        send_profile_suggestion_email(
            dancer_id=dancer_id,
            suggestion_text=suggestion_text,
            submitter_name=submitter_name,
            submitter_role=submitter_role,
            contact=contact,
            source_url=source_url,
        )
    except Exception as exc:
        print("Profile suggestion email failed:", exc)

    flash("Suggestion submitted for review.", "success")
    return redirect(url_for("dancer_profile_detail_by_id", dancer_id=dancer_id))



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
    new_status = normalize_people_profile_status(request.form.get("status", "").strip())

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
    new_status = normalize_people_profile_status(request.form.get("status", "").strip())

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
    new_status = normalize_people_profile_status(request.form.get("status", "").strip())

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


@app.route("/ledger-review")
@app.route("/verify")
def verify_claims():
    ensure_verification_tables()

    if "build_controversy_queue" in globals():
        submissions = build_controversy_queue()
    else:
        raw_submissions = fetch_all(
            """
            SELECT *
            FROM submissions
            WHERE needs_verification = 1
               OR review_status IN ('Needs Verification', 'Disputed')
               OR id IN (
                    SELECT DISTINCT submission_id
                    FROM verification_votes
               )
            ORDER BY created_at DESC
            """,
            {},
        )

        vote_counts = get_vote_counts_for_submissions(raw_submissions)
        submissions = []

        for submission in raw_submissions:
            counts = vote_counts.get(submission["id"], {"true": 0, "false": 0, "debatable": 0})
            true_count = int(counts.get("true") or 0)
            false_count = int(counts.get("false") or 0)
            debatable_count = int(counts.get("debatable") or 0)
            total_votes = true_count + false_count + debatable_count

            reasons = []
            score = 0

            if submission["review_status"] == "Disputed":
                reasons.append("Disputed")
                score += 100

            if debatable_count > 0:
                reasons.append("Debatable votes")
                score += 60 + debatable_count

            if true_count > 0 and false_count > 0 and abs(true_count - false_count) <= 1:
                reasons.append("Close True/False split")
                score += 50 + total_votes

            if int(submission["needs_verification"] or 0) == 1:
                # Keep explicit event/battle/award/claim flags, but do not flood with
                # imported dancer/move ghost records that have no votes yet.
                if submission["submission_type"] not in {"dancer_profile", "move_info"} or total_votes > 0:
                    reasons.append("Flagged for verification")
                    score += 25

            if not reasons:
                continue

            if total_votes == 0 and submission["submission_type"] in {"dancer_profile", "move_info"}:
                continue

            row = dict(submission)
            row["true_count"] = true_count
            row["false_count"] = false_count
            row["debatable_count"] = debatable_count
            row["total_votes"] = total_votes
            row["controversy_reason"] = ", ".join(dict.fromkeys(reasons))
            row["controversy_score"] = score
            submissions.append(row)

        submissions.sort(
            key=lambda item: (
                item.get("controversy_score") or 0,
                item.get("total_votes") or 0,
                item.get("created_at") or "",
            ),
            reverse=True,
        )

    return render_template(
        "verify_claims.html",
        submissions=submissions,
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



# --- Temporary admin-only gates for unfinished public sections ---
@app.before_request
def gate_unfinished_public_sections():
    gated_paths = {
        "/ask",
        "/battles",
        "/awards",
    }

    if request.path in gated_paths and not current_user_is_admin():
        return redirect(url_for("home"))


@app.route("/ask")
@app.route("/ask", methods=["GET", "POST"])
def ask_archive():
    ensure_phase2_ledger_tables()

    if request.method == "POST":
        return ask_ledger_search_phase3a()

    conversations = []
    user = current_user()
    is_admin = bool(session.get("admin_logged_in"))

    if user or is_admin:
        try:
            conversations = fetch_all(
                """
                SELECT *
                FROM ask_conversations
                ORDER BY updated_at DESC, created_at DESC, id DESC
                LIMIT 12
                """,
                {},
            )
        except Exception:
            conversations = []

    return render_template(
        "ask_archive.html",
        recent_ask_conversations=conversations,
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






RESERVED_PUBLIC_SLUGS = {
    "admin",
    "account",
    "ask",
    "awards",
    "battles",
    "contributor",
    "dancer",
    "dancers",
    "event",
    "event-affiliates",
    "events",
    "litefeet-music",
    "music",
    "people",
    "producers",
    "releases",
    "robots.txt",
    "sitemap.xml",
    "static",
    "submit",
    "teams",
    "verify",
}


def is_reserved_public_slug(value):
    return (value or "").strip().lower() in RESERVED_PUBLIC_SLUGS


@app.route("/<organizer_slug>")
def organizer_detail(organizer_slug):
    if is_reserved_public_slug(organizer_slug):
        abort(404)

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
    if is_reserved_public_slug(organizer_slug):
        abort(404)

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




def parse_ledger_date_value(value):
    if not value:
        return None

    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            continue

    return None


@app.template_filter("music_release_date")
def music_release_date_filter(value):
    date_value = parse_ledger_date_value(value)
    if not date_value:
        return "Unknown"

    today = datetime.now().date()
    days_old = (today - date_value).days

    # Last two weeks gets weekday.
    if 0 <= days_old <= 14:
        return date_value.strftime("%A, %B %-d, %Y")

    # Older dates stay cleaner.
    return date_value.strftime("%B %-d, %Y")


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
    ensure_person_role_columns()
    ensure_profile_enrichment_columns()

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


@app.context_processor
def inject_nav_account_context():
    user = current_user()

    claimed_profile = None

    if user:
        claimed_profile = fetch_one(
            """
            SELECT *
            FROM dancer_profiles
            WHERE user_id = :user_id
            ORDER BY id DESC
            LIMIT 1
            """,
            {"user_id": user["id"]},
        )

    return {
        "nav_current_user": user,
        "nav_claimed_profile": claimed_profile,
        "nav_is_admin": bool(session.get("admin_logged_in")),
        "nav_anonymous_mode": bool(session.get("anonymous_mode")),
    }


@app.route("/account")
def account_home():
    user = current_user()

    if not user and not session.get("admin_logged_in"):
        return redirect(url_for("account_login"))

    claimed_profile = None
    contributions = []

    if user:
        claimed_profile = fetch_one(
            """
            SELECT *
            FROM dancer_profiles
            WHERE user_id = :user_id
            ORDER BY id DESC
            LIMIT 1
            """,
            {"user_id": user["id"]},
        )

        contributions = fetch_all(
            """
            SELECT *
            FROM submissions
            WHERE lower(contact) = lower(:email)
               OR lower(submitter_name) = lower(:display_name)
            ORDER BY created_at DESC
            LIMIT 50
            """,
            {
                "email": user.get("email", ""),
                "display_name": user.get("display_name", ""),
            },
        )

    if session.get("admin_logged_in") and not contributions:
        contributions = fetch_all(
            """
            SELECT *
            FROM submissions
            ORDER BY created_at DESC
            LIMIT 50
            """
        )

    return render_template(
        "account_home.html",
        user=user,
        claimed_profile=claimed_profile,
        contributions=contributions,
        anonymous_mode=bool(session.get("anonymous_mode")),
        is_admin=bool(session.get("admin_logged_in")),
    )


@app.route("/account/anonymous-mode", methods=["POST"])
def toggle_anonymous_mode():
    session["anonymous_mode"] = not bool(session.get("anonymous_mode"))
    return redirect(request.referrer or url_for("account_home"))








def extract_embed_src(value):
    value = (value or "").strip()

    if not value:
        return ""

    # If they paste a full iframe embed code, keep only the iframe src.
    match = re.search(r'''src=["']([^"']+)["']''', value)
    if match:
        return match.group(1).strip()

    # If they paste a normal URL, keep the URL.
    if value.startswith("http://") or value.startswith("https://"):
        return value

    return ""


def ensure_media_embed_column():
    ensure_media_items_table()

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE media_items ADD COLUMN IF NOT EXISTS embed_url TEXT"))
        else:
            cols = conn.execute(text("PRAGMA table_info(media_items)")).fetchall()
            existing = {col[1] for col in cols}
            if "embed_url" not in existing:
                conn.execute(text("ALTER TABLE media_items ADD COLUMN embed_url TEXT"))


def normalize_music_text(value):
    value = (value or "").lower().strip()
    value = value.replace("&", "and")
    value = re.sub(r"\\b(feat|ft|featuring)\\b\\.?"," ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\\s+", " ", value).strip()
    return value


def music_release_key(title, artist_or_creator):
    title_key = normalize_music_text(title)
    artist_key = normalize_music_text(artist_or_creator)
    return f"{artist_key}::{title_key}".strip(":")


def ensure_media_release_key_column():
    ensure_media_items_table()

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE media_items ADD COLUMN IF NOT EXISTS canonical_release_key TEXT"))
        else:
            cols = conn.execute(text("PRAGMA table_info(media_items)")).fetchall()
            existing = {col[1] for col in cols}
            if "canonical_release_key" not in existing:
                conn.execute(text("ALTER TABLE media_items ADD COLUMN canonical_release_key TEXT"))








def fetch_public_page_html(url):
    url = (url or "").strip()

    if not url.startswith(("http://", "https://")):
        return ""

    try:
        request_obj = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 LiteFeetLedgerBot/1.0"
            },
        )

        with urlopen(request_obj, timeout=8) as response:
            content_type = response.headers.get("Content-Type", "")

            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return ""

            raw = response.read(800000)

        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def extract_meta_content(html, property_name):
    if not html:
        return ""

    patterns = [
        rf'<meta[^>]+property=["\\\']{re.escape(property_name)}["\\\'][^>]+content=["\\\']([^"\\\']+)["\\\']',
        rf'<meta[^>]+content=["\\\']([^"\\\']+)["\\\'][^>]+property=["\\\']{re.escape(property_name)}["\\\']',
        rf'<meta[^>]+name=["\\\']{re.escape(property_name)}["\\\'][^>]+content=["\\\']([^"\\\']+)["\\\']',
        rf'<meta[^>]+content=["\\\']([^"\\\']+)["\\\'][^>]+name=["\\\']{re.escape(property_name)}["\\\']',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, flags=re.I | re.S)
        if match:
            return unescape(match.group(1)).strip()

    return ""


def extract_page_title(html):
    value = extract_meta_content(html, "og:title")

    if value:
        return value

    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.I | re.S)

    if match:
        return unescape(re.sub(r"\s+", " ", match.group(1))).strip()

    return ""


def clean_imported_track_title(value):
    value = unescape(value or "").strip()
    value = re.sub(r"\s+", " ", value).strip()

    if not value:
        return ""

    junk_values = {
        "play",
        "pause",
        "copy link",
        "embed",
        "save to library",
        "share",
        "shuffle",
        "repeat",
    }

    if value.lower() in junk_values:
        return ""

    if len(value) > 140:
        return ""

    return value


def extract_possible_track_titles(html):
    if not html:
        return []

    candidates = []

    # Pull repeated JSON-ish titles from modern web apps.
    for match in re.finditer(r'"title"\s*:\s*"([^"]{2,140})"', html):
        candidates.append(match.group(1))

    for match in re.finditer(r'"name"\s*:\s*"([^"]{2,140})"', html):
        candidates.append(match.group(1))

    # Pull aria-labels that sometimes contain track names.
    for match in re.finditer(r'aria-label=["\\\']([^"\\\']{2,140})["\\\']', html):
        candidates.append(match.group(1))

    cleaned = []
    seen = set()

    for candidate in candidates:
        value = clean_imported_track_title(candidate)
        key = normalize_music_text(value)

        if not value or not key:
            continue

        if key in seen:
            continue

        # Avoid importing the whole page title as a track too often.
        if key in {"home", "library", "login", "sign up"}:
            continue

        seen.add(key)
        cleaned.append(value)

    return cleaned[:40]


def infer_project_title_from_link(url, html):
    title = extract_page_title(html)

    if title:
        # Clean common suffixes but keep actual project wording.
        title = re.sub(r"\s+[-|]\s+(Untitled|SoundCloud|Spotify|Apple Music|YouTube).*$", "", title, flags=re.I).strip()
        return title

    parsed = urlparse(url or "")
    slug = parsed.path.rstrip("/").split("/")[-1]
    slug = re.sub(r"[-_]+", " ", slug).strip()

    return slug.title() if slug else "Untitled Project"


def fetch_music_link_metadata(url):
    platform = detect_media_platform(url)

    # YouTube pages contain a lot of interface text like Like, Dislike, Save,
    # comments, recommendations, and generic site descriptions.
    # Do not use the generic scraper for YouTube.
    if platform == "YouTube":
        return fetch_youtube_metadata(url)

    html = fetch_public_page_html(url)
    if not html:
        return {
            "title": "",
            "artist_or_creator": "",
            "platform": platform or detect_media_platform(url),
            "url": url,
            "description": "",
            "tracks": [],
        }

    title = infer_project_title_from_link(url, html)
    description = (
        extract_meta_content(html, "og:description")
        or extract_meta_content(html, "description")
        or ""
    )

    return {
        "title": title,
        "artist_or_creator": "",
        "platform": platform or detect_media_platform(url),
        "url": url,
        "description": description,
        "tracks": extract_possible_track_titles(html),
    }

def ensure_music_projects_table():
    ensure_media_items_table()

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS music_projects (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT NULL,
                        artist_or_creator TEXT,
                        url TEXT,
                        platform TEXT,
                        release_date TEXT,
                        description TEXT,
                        status TEXT DEFAULT 'Published',
                        created_at TEXT
                    )
                    """
                )
            )

            conn.execute(text("ALTER TABLE media_items ADD COLUMN IF NOT EXISTS music_project_id INTEGER"))
            conn.execute(text("ALTER TABLE media_items ADD COLUMN IF NOT EXISTS track_number INTEGER"))
            conn.execute(text("ALTER TABLE media_items ADD COLUMN IF NOT EXISTS playable_url TEXT"))
        else:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS music_projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        artist_or_creator TEXT,
                        url TEXT,
                        platform TEXT,
                        release_date TEXT,
                        description TEXT,
                        status TEXT DEFAULT 'Published',
                        created_at TEXT
                    )
                    """
                )
            )

            cols = conn.execute(text("PRAGMA table_info(media_items)")).fetchall()
            existing = {col[1] for col in cols}

            if "music_project_id" not in existing:
                conn.execute(text("ALTER TABLE media_items ADD COLUMN music_project_id INTEGER"))
            if "track_number" not in existing:
                conn.execute(text("ALTER TABLE media_items ADD COLUMN track_number INTEGER"))
            if "playable_url" not in existing:
                conn.execute(text("ALTER TABLE media_items ADD COLUMN playable_url TEXT"))


def parse_project_tracklist(tracklist):
    tracks = []

    for raw_line in (tracklist or "").splitlines():
        line = raw_line.strip()

        if not line:
            continue

        line = re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip()
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            tracks.append(line)

    return tracks


def ensure_music_feedback_table():
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS music_feedback (
                        id SERIAL PRIMARY KEY,
                        media_item_id INTEGER NOT NULL,
                        rating INTEGER,
                        would_lab INTEGER DEFAULT 0,
                        would_shoot_video INTEGER DEFAULT 0,
                        would_battle INTEGER DEFAULT 0,
                        feedback TEXT,
                        submitter_name TEXT,
                        voter_key TEXT,
                        created_at TEXT
                    )
                    """
                )
            )
            conn.execute(text("ALTER TABLE music_feedback ADD COLUMN IF NOT EXISTS voter_key TEXT"))
            conn.execute(text("ALTER TABLE music_feedback ADD COLUMN IF NOT EXISTS would_lab INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE music_feedback ADD COLUMN IF NOT EXISTS would_shoot_video INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE music_feedback ADD COLUMN IF NOT EXISTS would_battle INTEGER DEFAULT 0"))
        else:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS music_feedback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        media_item_id INTEGER NOT NULL,
                        rating INTEGER,
                        would_lab INTEGER DEFAULT 0,
                        would_shoot_video INTEGER DEFAULT 0,
                        would_battle INTEGER DEFAULT 0,
                        feedback TEXT,
                        submitter_name TEXT,
                        voter_key TEXT,
                        created_at TEXT
                    )
                    """
                )
            )
            cols = conn.execute(text("PRAGMA table_info(music_feedback)")).fetchall()
            existing = {col[1] for col in cols}

            if "voter_key" not in existing:
                conn.execute(text("ALTER TABLE music_feedback ADD COLUMN voter_key TEXT"))
            if "would_lab" not in existing:
                conn.execute(text("ALTER TABLE music_feedback ADD COLUMN would_lab INTEGER DEFAULT 0"))
            if "would_shoot_video" not in existing:
                conn.execute(text("ALTER TABLE music_feedback ADD COLUMN would_shoot_video INTEGER DEFAULT 0"))
            if "would_battle" not in existing:
                conn.execute(text("ALTER TABLE music_feedback ADD COLUMN would_battle INTEGER DEFAULT 0"))


def music_voter_key():
    user = current_user()

    if user:
        return "user:" + str(user.get("id") or user.get("email") or user.get("display_name"))

    if not session.get("music_voter_key"):
        session["music_voter_key"] = "session:" + secrets.token_urlsafe(16)

    return session["music_voter_key"]






def ensure_music_play_count_columns():
    ensure_media_items_table()

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE media_items ADD COLUMN IF NOT EXISTS play_count INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE media_items ADD COLUMN IF NOT EXISTS last_played_at TEXT"))
        else:
            cols = conn.execute(text("PRAGMA table_info(media_items)")).fetchall()
            existing = {col[1] for col in cols}

            if "play_count" not in existing:
                conn.execute(text("ALTER TABLE media_items ADD COLUMN play_count INTEGER DEFAULT 0"))

            if "last_played_at" not in existing:
                conn.execute(text("ALTER TABLE media_items ADD COLUMN last_played_at TEXT"))


def ensure_music_release_status_columns():
    ensure_media_items_table()
    ensure_music_projects_table()

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE media_items ADD COLUMN IF NOT EXISTS release_stage TEXT DEFAULT 'released'"))
            conn.execute(text("ALTER TABLE music_projects ADD COLUMN IF NOT EXISTS release_stage TEXT DEFAULT 'released'"))
        else:
            media_cols = conn.execute(text("PRAGMA table_info(media_items)")).fetchall()
            media_existing = {col[1] for col in media_cols}

            if "release_stage" not in media_existing:
                conn.execute(text("ALTER TABLE media_items ADD COLUMN release_stage TEXT DEFAULT 'released'"))

            project_cols = conn.execute(text("PRAGMA table_info(music_projects)")).fetchall()
            project_existing = {col[1] for col in project_cols}

            if "release_stage" not in project_existing:
                conn.execute(text("ALTER TABLE music_projects ADD COLUMN release_stage TEXT DEFAULT 'released'"))


def music_period_cutoff(period):
    today = datetime.now()

    if period == "all":
        return None
    if period == "week":
        return today - timedelta(days=7)
    if period == "30":
        return today - timedelta(days=30)
    if period == "60":
        return today - timedelta(days=60)
    if period == "6months":
        return today - timedelta(days=183)
    if period == "year":
        return today - timedelta(days=365)

    return today - timedelta(days=30)




@app.route("/releases/submit", methods=["GET", "POST"])
def submit_music_release():
    return redirect(url_for("submit_music_project"))

    user = current_user()

    if not user and not session.get("admin_logged_in"):
        return redirect(url_for("account_login", next=request.path))

    ensure_media_items_table()
    ensure_media_release_key_column()
    ensure_media_embed_column()

    error = ""

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        artist_or_creator = request.form.get("artist_or_creator", "").strip()
        url = request.form.get("url", "").strip()
        release_date = request.form.get("release_date", "").strip()
        description = request.form.get("description", "").strip()

        if not title or not artist_or_creator or not release_date:
            error = "Title, producer/artist, and release date are required. The link is optional."
        else:
            try:
                parsed_release_date = datetime.strptime(release_date, "%Y-%m-%d").date()
                today = datetime.now().date()

                if parsed_release_date > today:
                    error = "Release date cannot be in the future."
            except ValueError:
                error = "Use a valid release date."

        if not error:
            canonical_release_key = music_release_key(title, artist_or_creator)
            platform = metadata.get("platform") or detect_media_platform(source_url) if source_url else "No Link Yet"

            existing_releases = fetch_all(
                """
                SELECT id, title, artist_or_creator, canonical_release_key
                FROM media_items
                WHERE media_type = 'music_release'
                """
            )

            duplicate = None
            for release in existing_releases:
                existing_key = release.get("canonical_release_key") or music_release_key(
                    release.get("title"),
                    release.get("artist_or_creator"),
                )

                if existing_key == canonical_release_key:
                    duplicate = release
                    break

            if duplicate:
                return redirect(url_for("litefeet_music", duplicate="1"))

            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO media_items (
                            media_type,
                            title,
                            artist_or_creator,
                            url,
                            platform,
                            release_date,
                            event_name,
                            description,
                            status,
                            canonical_release_key,
                            embed_url,
                            created_at
                        )
                        VALUES (
                            'music_release',
                            :title,
                            :artist_or_creator,
                            :url,
                            :platform,
                            :release_date,
                            '',
                            :description,
                            'Published',
                            :canonical_release_key,
                            :embed_url,
                            :created_at
                        )
                        """
                    ),
                    {
                        "title": title,
                        "artist_or_creator": artist_or_creator,
                        "url": source_url,
                        "platform": platform,
                        "release_date": release_date,
                        "description": description,
                        "canonical_release_key": canonical_release_key,
                        "embed_url": "",
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )

            return redirect(url_for("litefeet_music"))

    return render_template("submit_music_release.html", error=error)






@app.route("/litefeet-music/projects/preview", methods=["POST"])
def preview_music_project():
    ensure_music_projects_table()

    url = request.form.get("url", "").strip()
    embed_code = request.form.get("embed_code", "").strip()
    embed_url = extract_embed_src(embed_code)
    source_url = url or embed_url

    if not source_url:
        return redirect(url_for("submit_music_project", error="source_required"))

    metadata = fetch_music_link_metadata(source_url)
    pulled_tracks = metadata.get("tracks", []) or []

    return render_template(
        "submit_music_project.html",
        error="",
        preview_mode=True,
        pulled_from_link=True,
        title=metadata.get("title", ""),
        artist_or_creator="",
        url=source_url,
        embed_code=embed_code,
        release_date="",
        description=metadata.get("description", ""),
        tracklist="\n".join(pulled_tracks),
        platform=metadata.get("platform", ""),
    )


@app.route("/litefeet-music/projects/submit", methods=["GET", "POST"])
def submit_music_project():
    user = current_user()

    if not user and not session.get("admin_logged_in"):
        return redirect(url_for("account_login", next=request.path))

    ensure_music_projects_table()
    ensure_media_release_key_column()
    ensure_music_release_status_columns()

    error = ""

    if request.method == "POST":
        submission_type = request.form.get("submission_type", "single").strip() or "single"
        title = request.form.get("title", "").strip()
        artist_or_creator = request.form.get("artist_or_creator", "").strip()
        url = request.form.get("url", "").strip()
        embed_code = request.form.get("embed_code", "").strip()
        embed_url = extract_embed_src(embed_code)
        source_url = url or embed_url
        playable_url = request.form.get("playable_url", "").strip()
        release_stage = request.form.get("release_stage", "released").strip() or "released"
        release_date = request.form.get("release_date", "").strip()
        description = request.form.get("description", "").strip()
        tracklist = request.form.get("tracklist", "").strip()

        metadata = fetch_music_link_metadata(source_url) if source_url else {}
        tracks = parse_project_tracklist(tracklist)

        if not tracks and metadata.get("tracks"):
            tracks = [] if detect_media_platform(source_url) == "YouTube" else metadata.get("tracks", [])

        if not title and metadata.get("title"):
            title = metadata.get("title", "")

        if not description and metadata.get("description"):
            description = metadata.get("description", "")

        if not source_url and not title and not tracks:
            error = "Add a music link, embed link, title, or tracklist so the Ledger has something to save."
        elif release_date:
            try:
                parsed_release_date = datetime.strptime(release_date, "%Y-%m-%d").date()
                if parsed_release_date > datetime.now().date() and release_stage == "released":
                    error = "Future dates should be marked as Preview or Coming Soon."
            except ValueError:
                error = "Use a valid release date."

        if not error:
            platform = metadata.get("platform") or detect_media_platform(source_url) if source_url else "No Link Yet"
            now_value = datetime.now().isoformat(timespec="seconds")

            if not title:
                if tracks:
                    title = tracks[0]
                else:
                    title = metadata.get("title") or "Untitled Music Submission"

            if not artist_or_creator:
                artist_or_creator = "Unknown"

            if not release_date:
                release_date = ""

            # SINGLE SONG: save only one media_items record. Do NOT create music_projects row.
            if submission_type == "single":
                canonical_release_key = music_release_key(title, artist_or_creator)

                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO media_items (
                                media_type,
                                title,
                                artist_or_creator,
                                url,
                                platform,
                                release_date,
                                event_name,
                                description,
                                status,
                                canonical_release_key,
                                release_stage,
                                music_project_id,
                                track_number,
                                playable_url,
                                created_at
                            )
                            VALUES (
                                'music_release',
                                :title,
                                :artist_or_creator,
                                :url,
                                :platform,
                                :release_date,
                                '',
                                :description,
                                'Published',
                                :canonical_release_key,
                                :release_stage,
                                NULL,
                                NULL,
                                :playable_url,
                                :created_at
                            )
                            """
                        ),
                        {
                            "title": title,
                            "artist_or_creator": artist_or_creator,
                            "url": source_url,
                            "platform": platform,
                            "release_date": release_date,
                            "description": description,
                            "canonical_release_key": canonical_release_key,
                            "release_stage": release_stage,
                            "playable_url": playable_url,
                            "created_at": now_value,
                        },
                    )

                return redirect(url_for("litefeet_music", period="all"))

            # PROJECT / PACK / PLAYLIST: create a project row and track rows.
            if not tracks:
                tracks = [title]

            with engine.begin() as conn:
                result = conn.execute(
                    text(
                        """
                        INSERT INTO music_projects (
                            title,
                            artist_or_creator,
                            url,
                            platform,
                            release_date,
                            description,
                            status,
                            release_stage,
                            created_at
                        )
                        VALUES (
                            :title,
                            :artist_or_creator,
                            :url,
                            :platform,
                            :release_date,
                            :description,
                            'Published',
                            :release_stage,
                            :created_at
                        )
                        RETURNING id
                        """
                    )
                    if engine.dialect.name == "postgresql"
                    else text(
                        """
                        INSERT INTO music_projects (
                            title,
                            artist_or_creator,
                            url,
                            platform,
                            release_date,
                            description,
                            status,
                            release_stage,
                            created_at
                        )
                        VALUES (
                            :title,
                            :artist_or_creator,
                            :url,
                            :platform,
                            :release_date,
                            :description,
                            'Published',
                            :release_stage,
                            :created_at
                        )
                        """
                    ),
                    {
                        "title": title,
                        "artist_or_creator": artist_or_creator,
                        "url": source_url,
                        "platform": platform,
                        "release_date": release_date,
                        "description": description,
                        "release_stage": release_stage,
                        "created_at": now_value,
                    },
                )

                if engine.dialect.name == "postgresql":
                    project_id = result.scalar()
                else:
                    project_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()

                for index, track_title in enumerate(tracks, start=1):
                    canonical_release_key = music_release_key(track_title, artist_or_creator)

                    conn.execute(
                        text(
                            """
                            INSERT INTO media_items (
                                media_type,
                                title,
                                artist_or_creator,
                                url,
                                platform,
                                release_date,
                                event_name,
                                description,
                                status,
                                canonical_release_key,
                                release_stage,
                                music_project_id,
                                track_number,
                                playable_url,
                                created_at
                            )
                            VALUES (
                                'music_release',
                                :track_title,
                                :artist_or_creator,
                                :url,
                                :platform,
                                :release_date,
                                :event_name,
                                :description,
                                'Published',
                                :canonical_release_key,
                                :release_stage,
                                :music_project_id,
                                :track_number,
                                :playable_url,
                                :created_at
                            )
                            """
                        ),
                        {
                            "track_title": track_title,
                            "artist_or_creator": artist_or_creator,
                            "url": source_url,
                            "platform": platform,
                            "release_date": release_date,
                            "event_name": title,
                            "description": f"Track {index} from {title}",
                            "canonical_release_key": canonical_release_key,
                            "release_stage": release_stage,
                            "music_project_id": project_id,
                            "track_number": index,
                            "playable_url": playable_url if index == 1 else "",
                            "created_at": now_value,
                        },
                    )

            return redirect(url_for("litefeet_music", period="all"))

    return render_template("submit_music_project.html", error=error)





@app.route("/litefeet-music/release/<int:item_id>")
def music_release_detail(item_id):
    ensure_media_items_table()
    ensure_music_feedback_table()
    ensure_music_play_count_columns()
    ensure_music_platform_stat_columns()

    rows = fetch_all(
        """
        SELECT
            m.*,
            COALESCE(AVG(f.rating), 0) AS average_rating,
            COUNT(f.id) AS feedback_count,
            COALESCE(SUM(f.would_lab), 0) AS lab_count,
            COALESCE(SUM(f.would_shoot_video), 0) AS video_count,
            COALESCE(SUM(f.would_battle), 0) AS battle_count
        FROM media_items m
        LEFT JOIN music_feedback f ON f.media_item_id = m.id
        WHERE m.id = :id
          AND m.media_type = 'music_release'
        GROUP BY m.id
        LIMIT 1
        """,
        {"id": item_id},
    )

    if not rows:
        abort(404)

    item = dict(rows[0])

    producer_profiles = fetch_all(
        """
        SELECT id, dance_name
        FROM dancer_profiles
        WHERE dance_name IS NOT NULL
        """
    )

    producer_profile_map = {
        normalize_name(row["dance_name"]): dict(row)
        for row in producer_profiles
        if row["dance_name"]
    }

    item["producer_profile"] = producer_profile_map.get(
        normalize_name(item.get("artist_or_creator") or "")
    )

    return render_template("music_release_detail.html", item=item)


@app.route("/litefeet-music")
def litefeet_music():
    ensure_media_items_table()
    ensure_music_feedback_table()
    ensure_music_projects_table()

    period = request.args.get("period", "30")
    cutoff_date = music_period_cutoff(period)
    cutoff = cutoff_date.date().isoformat() if cutoff_date else ""
    voter_key = music_voter_key()

    releases = fetch_all(
        """
        SELECT
            m.*,
            COALESCE(AVG(f.rating), 0) AS average_rating,
            COUNT(f.id) AS feedback_count,
            COALESCE(SUM(f.would_lab), 0) AS lab_count,
            COALESCE(SUM(f.would_shoot_video), 0) AS video_count,
            COALESCE(SUM(f.would_battle), 0) AS battle_count
        FROM media_items m
        LEFT JOIN music_feedback f ON f.media_item_id = m.id
        WHERE m.media_type = 'music_release'
          AND m.status = 'Published'
          AND (
                :cutoff = ''
                OR m.release_date >= :cutoff
                OR (m.release_date IS NULL OR m.release_date = '')
          )
        GROUP BY m.id
        ORDER BY
            average_rating DESC,
            feedback_count DESC,
            CASE WHEN m.release_date IS NULL OR m.release_date = '' THEN m.created_at ELSE m.release_date END DESC
        LIMIT 20
        """,
        {"cutoff": cutoff},
    )

    radar_cutoff = (datetime.now().date() - timedelta(days=7)).isoformat()

    music_projects = fetch_all(
        """
        SELECT
            p.*,
            COUNT(m.id) AS track_count
        FROM music_projects p
        LEFT JOIN media_items m ON m.music_project_id = p.id
        WHERE p.status = 'Published'
        GROUP BY p.id
        ORDER BY
            CASE WHEN p.release_date IS NULL OR p.release_date = '' THEN p.created_at ELSE p.release_date END DESC,
            p.created_at DESC
        LIMIT 20
        """
    )

    releases = [dict(item) for item in releases]

    release_radar = fetch_all(
        """
        SELECT
            m.*,
            COALESCE(AVG(f.rating), 0) AS average_rating,
            COUNT(f.id) AS feedback_count,
            COALESCE(SUM(f.would_lab), 0) AS lab_count,
            COALESCE(SUM(f.would_shoot_video), 0) AS video_count,
            COALESCE(SUM(f.would_battle), 0) AS battle_count
        FROM media_items m
        LEFT JOIN music_feedback f ON f.media_item_id = m.id
        WHERE m.media_type = 'music_release'
          AND m.status = 'Published'
          AND m.release_date >= :radar_cutoff
        GROUP BY m.id
        ORDER BY
            m.release_date DESC,
            m.created_at DESC
        LIMIT 20
        """,
        {"radar_cutoff": radar_cutoff},
    )

    release_radar = [dict(item) for item in release_radar]

    producer_profiles = fetch_all(
        """
        SELECT id, dance_name
        FROM dancer_profiles
        WHERE dance_name IS NOT NULL
        """
    )

    producer_profile_map = {
        normalize_music_text(row["dance_name"]): row
        for row in producer_profiles
        if row.get("dance_name")
    }

    for item in releases:
        producer_key = normalize_music_text(item.get("artist_or_creator"))
        item["producer_profile"] = producer_profile_map.get(producer_key)

    for item in release_radar:
        producer_key = normalize_music_text(item.get("artist_or_creator"))
        item["producer_profile"] = producer_profile_map.get(producer_key)

    voter_feedback_rows = fetch_all(
        """
        SELECT media_item_id, rating, would_lab, would_shoot_video, would_battle
        FROM music_feedback
        WHERE voter_key = :voter_key
        """,
        {"voter_key": voter_key},
    )

    voter_feedback = {
        str(row["media_item_id"]): {
            "rating": row.get("rating"),
            "would_lab": row.get("would_lab"),
            "would_shoot_video": row.get("would_shoot_video"),
            "would_battle": row.get("would_battle"),
        }
        for row in voter_feedback_rows
    }

    return render_template(
        "litefeet_music.html",
        releases=releases,
        release_radar=release_radar,
        music_projects=music_projects,
        period=period,
        voter_feedback=voter_feedback,
    )






ALLOWED_PROOF_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
MAX_PROOF_FILE_BYTES = 8 * 1024 * 1024


def proof_file_allowed(filename):
    if not filename:
        return False

    value = filename.lower().strip()
    return any(value.endswith(ext) for ext in ALLOWED_PROOF_EXTENSIONS)


def send_play_count_proof_email(subject, body, file_storage, reply_to=""):
    resend_api_key = os.environ.get("RESEND_API_KEY", "").strip()
    proof_from = os.environ.get("PROOF_EMAIL_FROM", "LiteFeet Ledger <proof@thelitefeetvault.com>").strip()
    proof_to = os.environ.get("PROOF_EMAIL_TO", "teethecreative@gmail.com").strip()

    if not resend_api_key or not proof_from or not proof_to:
        raise RuntimeError("Resend proof email settings are not configured.")

    filename = secure_filename(file_storage.filename or "proof")
    if not proof_file_allowed(filename):
        raise ValueError("Proof must be a PNG, JPG, WEBP, or PDF file.")

    file_bytes = file_storage.read()

    if not file_bytes:
        raise ValueError("Proof file was empty.")

    if len(file_bytes) > MAX_PROOF_FILE_BYTES:
        raise ValueError("Proof file is too large. Max size is 8MB.")

    import base64
    encoded_file = base64.b64encode(file_bytes).decode("utf-8")

    payload = {
        "from": proof_from,
        "to": [proof_to],
        "subject": subject,
        "text": body,
        "attachments": [
            {
                "filename": filename,
                "content": encoded_file,
            }
        ],
    }

    if reply_to:
        payload["reply_to"] = reply_to

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )

    if response.status_code >= 300:
        raise RuntimeError(f"Resend email failed: {response.status_code} {response.text}")


@app.route("/music/stats-proof", methods=["POST"])
def music_stats_proof_submit():
    track_title = request.form.get("track_title", "").strip()
    producer = request.form.get("producer", "").strip()
    platform = request.form.get("platform", "").strip()
    submitter_name = request.form.get("submitter_name", "").strip()
    submitter_email = request.form.get("submitter_email", "").strip()
    notes = request.form.get("notes", "").strip()
    proof_file = request.files.get("proof_file")

    if not proof_file or not proof_file.filename:
        return redirect((request.referrer or url_for("litefeet_music")) + "?proof=missing")

    subject = "LiteFeet Ledger Play Count Proof"
    if track_title:
        subject += f" - {track_title}"
    if producer:
        subject += f" - {producer}"

    body = f"""LiteFeet Ledger play count proof submitted.

Track: {track_title or 'Not provided'}
Producer / Artist: {producer or 'Not provided'}
Platform: {platform or 'Not provided'}

Submitted by: {submitter_name or 'Not provided'}
Submitter email: {submitter_email or 'Not provided'}

Notes:
{notes or 'None'}

This proof file was attached to the email and was not stored by the site.
"""

    try:
        send_play_count_proof_email(subject, body, proof_file)
    except Exception as exc:
        print("Proof email failed:", exc)
        return redirect((request.referrer or url_for("litefeet_music")) + "?proof=error")

    return redirect((request.referrer or url_for("litefeet_music")) + "?proof=sent")


@app.route("/music/<int:item_id>/play", methods=["POST"])
def music_play_count(item_id):
    ensure_music_play_count_columns()

    # Admin/testing plays should not affect public Ledger Plays.
    if session.get("admin_logged_in") or current_user_is_admin():
        rows = fetch_all(
            """
            SELECT play_count
            FROM media_items
            WHERE id = :id
            LIMIT 1
            """,
            {"id": item_id},
        )

        row = rows[0] if rows else None

        return {
            "ok": True,
            "play_count": row["play_count"] if row else 0,
            "admin_ignored": True,
        }

    user = current_user()
    user_id = user.get("id") if user else None
    now_value = datetime.now().isoformat(timespec="seconds")

    ensure_admin_analytics_tables()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE media_items
                SET play_count = COALESCE(play_count, 0) + 1,
                    last_played_at = :last_played_at
                WHERE id = :id
                """
            ),
            {
                "id": item_id,
                "last_played_at": now_value,
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO music_play_events (
                    media_item_id,
                    user_id,
                    is_admin,
                    created_at
                )
                VALUES (
                    :media_item_id,
                    :user_id,
                    0,
                    :created_at
                )
                """
            ),
            {
                "media_item_id": item_id,
                "user_id": user_id,
                "created_at": now_value,
            },
        )

    rows = fetch_all(
        """
        SELECT play_count
        FROM media_items
        WHERE id = :id
        LIMIT 1
        """,
        {"id": item_id},
    )

    row = rows[0] if rows else None

    return {
        "ok": True,
        "play_count": row["play_count"] if row else 0,
    }


def music_feedback_submit(item_id):
    ensure_music_feedback_table()

    user = current_user()
    if not user:
        return redirect(url_for("account_login", next=request.referrer or url_for("litefeet_music")))

    voter_key = music_voter_key()
    action = request.form.get("action", "").strip()
    feedback = request.form.get("feedback", "").strip()

    rating = None
    rating_raw = request.form.get("rating", "").strip()

    if rating_raw:
        try:
            rating = int(rating_raw)
        except ValueError:
            rating = None

        if rating is not None:
            if rating < 1:
                rating = None
            elif rating > 10:
                rating = 10

    # Public music feedback stays anonymous even though login is required.
    submitter_name = "Anonymous"

    existing_rows = fetch_all(
        """
        SELECT *
        FROM music_feedback
        WHERE media_item_id = :media_item_id
          AND voter_key = :voter_key
        LIMIT 1
        """,
        {"media_item_id": item_id, "voter_key": voter_key},
    )

    existing = existing_rows[0] if existing_rows else None

    current_rating = existing.get("rating") if existing else None
    current_lab = int(existing.get("would_lab") or 0) if existing else 0
    current_video = int(existing.get("would_shoot_video") or 0) if existing else 0
    current_battle = int(existing.get("would_battle") or 0) if existing else 0
    current_feedback = existing.get("feedback") if existing else ""

    # Full form submit: user can choose Lab, Video, and Battle together.
    if not action or action == "full":
        current_rating = rating
        current_lab = 1 if request.form.get("would_lab") else 0
        current_video = 1 if request.form.get("would_shoot_video") else 0
        current_battle = 1 if request.form.get("would_battle") else 0
        current_feedback = feedback

    # Quick toggle support, if any old buttons still post action values.
    elif action == "lab":
        current_lab = 0 if current_lab else 1
    elif action == "video":
        current_video = 0 if current_video else 1
    elif action == "battle":
        current_battle = 0 if current_battle else 1
    elif action == "rating":
        current_rating = rating
    elif action == "feedback":
        current_feedback = feedback

    if existing:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE music_feedback
                    SET rating = :rating,
                        would_lab = :would_lab,
                        would_shoot_video = :would_shoot_video,
                        would_battle = :would_battle,
                        feedback = :feedback,
                        submitter_name = :submitter_name
                    WHERE id = :id
                    """
                ),
                {
                    "id": existing["id"],
                    "rating": current_rating,
                    "would_lab": current_lab,
                    "would_shoot_video": current_video,
                    "would_battle": current_battle,
                    "feedback": current_feedback,
                    "submitter_name": submitter_name,
                },
            )
    else:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO music_feedback (
                        media_item_id,
                        rating,
                        would_lab,
                        would_shoot_video,
                        would_battle,
                        feedback,
                        submitter_name,
                        voter_key,
                        created_at
                    )
                    VALUES (
                        :media_item_id,
                        :rating,
                        :would_lab,
                        :would_shoot_video,
                        :would_battle,
                        :feedback,
                        :submitter_name,
                        :voter_key,
                        :created_at
                    )
                    """
                ),
                {
                    "media_item_id": item_id,
                    "rating": current_rating,
                    "would_lab": current_lab,
                    "would_shoot_video": current_video,
                    "would_battle": current_battle,
                    "feedback": current_feedback,
                    "submitter_name": submitter_name,
                    "voter_key": voter_key,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            )

    return redirect(request.referrer or url_for("litefeet_music"))


def music_playback_status(item):
    playable_url = item.get("playable_url") if hasattr(item, "get") else ""
    source_url = item.get("url") if hasattr(item, "get") else ""

    if playable_url and audio_url_is_direct_playable(playable_url):
        return {
            "label": "Playable Audio",
            "admin_note": "Direct audio URL exists. This can play in the site audio player.",
            "state": "audio",
        }

    if playable_url:
        return {
            "label": "Playable Link Added",
            "admin_note": "A playable URL exists, but it is not a common direct audio file type. Test it in the browser.",
            "state": "maybe",
        }

    if source_url and media_embed_url(source_url):
        return {
            "label": "Playable Embed",
            "admin_note": "The source link can be embedded. For audio-only playback, add a direct playable URL.",
            "state": "embed",
        }

    if source_url:
        return {
            "label": "Source Only",
            "admin_note": "Source link exists, but the site cannot play it directly. Add a direct audio URL or embeddable track link.",
            "state": "source_only",
        }

    return {
        "label": "Archived Only",
        "admin_note": "No source link or playable URL exists. The Ledger can show metadata, but cannot play this track.",
        "state": "archived",
    }


@app.template_filter("music_playback_status")
def music_playback_status_filter(item):
    return music_playback_status(item)


@app.route("/admin/music/release/<int:item_id>/edit", methods=["GET", "POST"])
def admin_music_release_edit(item_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login", next=request.path))

    ensure_media_items_table()
    ensure_media_release_key_column()
    ensure_music_projects_table()

    rows = fetch_all(
        """
        SELECT *
        FROM media_items
        WHERE id = :id
          AND media_type = 'music_release'
        LIMIT 1
        """,
        {"id": item_id},
    )

    if not rows:
        abort(404)

    item = dict(rows[0])

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        artist_or_creator = request.form.get("artist_or_creator", "").strip()
        url = request.form.get("url", "").strip()
        playable_url = request.form.get("playable_url", "").strip()
        release_date = request.form.get("release_date", "").strip()
        platform = request.form.get("platform", "").strip() or detect_media_platform(url)
        event_name = request.form.get("event_name", "").strip()
        description = request.form.get("description", "").strip()
        status = request.form.get("status", "Published").strip() or "Published"
        track_number_raw = request.form.get("track_number", "").strip()

        try:
            track_number = int(track_number_raw) if track_number_raw else None
        except ValueError:
            track_number = None

        canonical_release_key = music_release_key(title, artist_or_creator)

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE media_items
                    SET title = :title,
                        artist_or_creator = :artist_or_creator,
                        url = :url,
                        playable_url = :playable_url,
                        platform = :platform,
                        release_date = :release_date,
                        event_name = :event_name,
                        description = :description,
                        status = :status,
                        track_number = :track_number,
                        canonical_release_key = :canonical_release_key
                    WHERE id = :id
                    """
                ),
                {
                    "id": item_id,
                    "title": title,
                    "artist_or_creator": artist_or_creator,
                    "url": url,
                    "playable_url": playable_url,
                    "platform": platform,
                    "release_date": release_date,
                    "event_name": event_name,
                    "description": description,
                    "status": normalize_people_profile_status(status),
                    "track_number": track_number,
                    "canonical_release_key": canonical_release_key,
                },
            )

        return redirect(url_for("litefeet_music", period="all"))

    return render_template("admin_music_release_edit.html", item=item)


@app.route("/admin/music/release/<int:item_id>/delete", methods=["POST"])
def admin_music_release_delete(item_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login", next=request.path))

    ensure_media_items_table()

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM music_feedback WHERE media_item_id = :id"),
            {"id": item_id},
        )
        conn.execute(
            text("DELETE FROM media_items WHERE id = :id AND media_type = 'music_release'"),
            {"id": item_id},
        )

    return redirect(request.referrer or url_for("litefeet_music", period="all"))



@app.route("/admin/music/project/<int:project_id>/edit", methods=["GET", "POST"])
def admin_music_project_edit(project_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login", next=request.path))

    ensure_music_projects_table()
    ensure_music_release_status_columns()

    rows = fetch_all(
        """
        SELECT *
        FROM music_projects
        WHERE id = :id
        LIMIT 1
        """,
        {"id": project_id},
    )

    if not rows:
        abort(404)

    project = dict(rows[0])

    tracks = fetch_all(
        """
        SELECT *
        FROM media_items
        WHERE music_project_id = :project_id
          AND media_type = 'music_release'
        ORDER BY track_number ASC, id ASC
        """,
        {"project_id": project_id},
    )

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        artist_or_creator = request.form.get("artist_or_creator", "").strip()
        url = request.form.get("url", "").strip()
        platform = request.form.get("platform", "").strip() or detect_media_platform(url)
        release_date = request.form.get("release_date", "").strip()
        release_stage = request.form.get("release_stage", "released").strip() or "released"
        description = request.form.get("description", "").strip()
        status = request.form.get("status", "Published").strip() or "Published"

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE music_projects
                    SET title = :title,
                        artist_or_creator = :artist_or_creator,
                        url = :url,
                        platform = :platform,
                        release_date = :release_date,
                        release_stage = :release_stage,
                        description = :description,
                        status = :status
                    WHERE id = :id
                    """
                ),
                {
                    "id": project_id,
                    "title": title,
                    "artist_or_creator": artist_or_creator,
                    "url": url,
                    "platform": platform,
                    "release_date": release_date,
                    "release_stage": release_stage,
                    "description": description,
                    "status": normalize_people_profile_status(status),
                },
            )

            conn.execute(
                text(
                    """
                    UPDATE media_items
                    SET artist_or_creator = :artist_or_creator,
                        url = :url,
                        platform = :platform,
                        release_date = :release_date,
                        release_stage = :release_stage,
                        event_name = :event_name,
                        status = :status
                    WHERE music_project_id = :project_id
                      AND media_type = 'music_release'
                    """
                ),
                {
                    "project_id": project_id,
                    "artist_or_creator": artist_or_creator,
                    "url": url,
                    "platform": platform,
                    "release_date": release_date,
                    "release_stage": release_stage,
                    "event_name": title,
                    "status": normalize_people_profile_status(status),
                },
            )

        return redirect(url_for("litefeet_music", period="all"))

    return render_template("admin_music_project_edit.html", project=project, tracks=tracks)


@app.route("/admin/music/project/<int:project_id>/delete", methods=["POST"])
def admin_music_project_delete(project_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login", next=request.path))

    ensure_music_projects_table()

    track_rows = fetch_all(
        """
        SELECT id
        FROM media_items
        WHERE music_project_id = :project_id
        """,
        {"project_id": project_id},
    )

    track_ids = [row["id"] for row in track_rows]

    with engine.begin() as conn:
        for track_id in track_ids:
            conn.execute(
                text("DELETE FROM music_feedback WHERE media_item_id = :id"),
                {"id": track_id},
            )

        conn.execute(
            text("DELETE FROM media_items WHERE music_project_id = :project_id"),
            {"project_id": project_id},
        )

        conn.execute(
            text("DELETE FROM music_projects WHERE id = :project_id"),
            {"project_id": project_id},
        )

    return redirect(url_for("litefeet_music", period="all"))



@app.route("/admin/view-as-public", methods=["POST"])
def admin_view_as_public():
    if session.get("admin_logged_in"):
        session["admin_return_available"] = True
        session["admin_logged_in"] = False

    return redirect(request.referrer or url_for("home"))


@app.route("/admin/return-to-admin", methods=["POST"])
def admin_return_to_admin():
    if session.get("admin_return_available"):
        session["admin_logged_in"] = True
        session.pop("admin_return_available", None)

    return redirect(request.referrer or url_for("home"))


# --- Global details_json compatibility helpers ---
def parse_submission_details(record_or_details):
    import json

    if record_or_details is None:
        return {}

    # SQLAlchemy row / dict with details_json
    try:
        if hasattr(record_or_details, "get") and record_or_details.get("details_json") is not None:
            raw = record_or_details.get("details_json")
        else:
            raw = record_or_details
    except Exception:
        raw = record_or_details

    # Row object fallback
    try:
        if not isinstance(raw, (str, list, dict)) and raw["details_json"] is not None:
            raw = raw["details_json"]
    except Exception:
        pass

    if raw is None:
        return {}

    if isinstance(raw, (list, dict)):
        return raw

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}

        try:
            return json.loads(raw)
        except Exception:
            return {}

    return {}


def get_detail_value(record_or_details, label):
    details = parse_submission_details(record_or_details)

    def clean_value(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            cleaned_items = []
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("value")
                    note = item.get("note")
                    featuring = item.get("featuring")

                    if name and note:
                        cleaned_items.append(f"{name} ({note})")
                    elif name:
                        cleaned_items.append(str(name))
                    elif featuring:
                        cleaned_items.append(", ".join(str(x) for x in featuring))
                    else:
                        cleaned_items.append(str(item))
                else:
                    cleaned_items.append(str(item))

            return " | ".join(cleaned_items)

        if isinstance(value, dict):
            name = value.get("name") or value.get("title") or value.get("value")
            note = value.get("note")

            if name and note:
                return f"{name} ({note})"
            if name:
                return str(name)

            return ", ".join(f"{k}: {v}" for k, v in value.items())

        return str(value)

    def record_value(key):
        try:
            if hasattr(record_or_details, "get"):
                return record_or_details.get(key)
        except Exception:
            pass

        try:
            return record_or_details[key]
        except Exception:
            return None

    # Legacy format:
    # [{"label": "Event Date", "value": "2026-06-06"}, ...]
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict) and item.get("label") == label:
                return clean_value(item.get("value"))
        return ""

    # Structured format:
    # {"event_date": "2026-06-06", "time": "...", "battles": [...]}
    if isinstance(details, dict):
        label_key_map = {
            "Event Name": ["event_name", "title"],
            "Organization Name": ["organization_name", "organizer", "series", "presented_by"],
            "Event Date": ["event_date", "date"],
            "Event Time": ["event_time", "time"],
            "Event Location": ["event_location", "location", "venue"],
            "Venue Notes": ["venue_notes", "note", "message"],
            "Battle Type": ["battle_type", "type"],
            "Age Restriction": ["age_restriction", "requirement"],
            "Entry": ["entry"],
            "Host": ["host", "hosted_by"],
            "Judges": ["judges", "special_guest_judges"],
            "Event Results": ["event_results", "results"],
            "Results Status": ["results_status"],
            "Needs Confirmation": ["needs_confirmation", "confirmation_needed"],
            "Archive Note": ["archive_note", "notes"],
            "Battle List": ["battle_list", "battles"],
            "Studio": ["studio", "venue"],
            "Borough": ["borough"],
            "End Results": ["end_results", "results"],
            "Organizer": ["organizer", "presented_by", "series", "related_to"],
            "Event Host": ["event_host", "host", "hosted_by"],
        }

        possible_keys = label_key_map.get(label, [])
        possible_keys.extend([
            label,
            label.lower(),
            label.lower().replace(" ", "_"),
        ])

        for key in possible_keys:
            if key in details and details.get(key) not in (None, ""):
                return clean_value(details.get(key))

        if label == "Event Name":
            return clean_value(record_value("title"))

        if label in ["Organization Name", "Organizer"]:
            return clean_value(record_value("related_to"))

    return ""


# --- Dancer profile safe event/detail helper overrides ---
def _safe_row_get(row, key, default=""):
    try:
        if hasattr(row, "get"):
            value = row.get(key, default)
        else:
            value = row[key]
    except Exception:
        value = default

    return default if value is None else value


def parse_submission_details(record_or_details):
    import json

    if record_or_details is None:
        return {}

    raw = record_or_details

    try:
        if hasattr(record_or_details, "get") and record_or_details.get("details_json") is not None:
            raw = record_or_details.get("details_json")
    except Exception:
        pass

    try:
        if not isinstance(raw, (str, list, dict)) and raw["details_json"] is not None:
            raw = raw["details_json"]
    except Exception:
        pass

    if raw is None:
        return {}

    if isinstance(raw, (list, dict)):
        return raw

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}

        try:
            return json.loads(raw)
        except Exception:
            return {}

    return {}


def get_detail_value(record_or_details, label):
    details = parse_submission_details(record_or_details)

    def clean_value(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            output = []
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("value")
                    note = item.get("note")
                    if name and note:
                        output.append(f"{name} ({note})")
                    elif name:
                        output.append(str(name))
                    else:
                        output.append(str(item))
                else:
                    output.append(str(item))
            return " | ".join(output)
        if isinstance(value, dict):
            name = value.get("name") or value.get("title") or value.get("value")
            note = value.get("note")
            if name and note:
                return f"{name} ({note})"
            if name:
                return str(name)
            return ", ".join(f"{k}: {v}" for k, v in value.items())
        return str(value)

    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict) and item.get("label") == label:
                return clean_value(item.get("value"))
        return ""

    if isinstance(details, dict):
        label_key_map = {
            "Event Name": ["event_name", "title"],
            "Organization Name": ["organization_name", "organizer", "series", "presented_by"],
            "Event Date": ["event_date", "date"],
            "Event Time": ["event_time", "time"],
            "Event Location": ["event_location", "location", "venue"],
            "Venue Notes": ["venue_notes", "note", "message"],
            "Entry": ["entry"],
            "Host": ["host", "hosted_by"],
            "Judges": ["judges", "special_guest_judges"],
            "Battle List": ["battle_list", "battles"],
            "Organizer": ["organizer", "presented_by", "series", "related_to"],
            "Event Host": ["event_host", "host", "hosted_by"],
        }

        possible_keys = label_key_map.get(label, [])
        possible_keys.extend([
            label,
            label.lower(),
            label.lower().replace(" ", "_"),
        ])

        for key in possible_keys:
            if key in details and details.get(key) not in (None, ""):
                return clean_value(details.get(key))

    return ""


def event_organizer_name(event):
    organizer = (
        get_detail_value(event, "Organizer")
        or get_detail_value(event, "Organization Name")
        or get_detail_value(event, "Event Host")
        or _safe_row_get(event, "related_to", "")
    )
    return organizer or "LiteFeet Ledger"


def event_public_url(event):
    event_id = _safe_row_get(event, "id", "")
    if event_id:
        return f"/events/{event_id}"
    return "/events"


# --- Runtime helper compatibility patch v2 ---
def ensure_music_platform_stat_columns():
    """
    Compatibility shim for profile/music routes that still call the older
    platform-stat setup name.
    """
    for fn_name in [
        "ensure_media_items_table",
        "ensure_music_feedback_table",
        "ensure_music_play_count_columns",
        "ensure_music_release_status_columns",
    ]:
        fn = globals().get(fn_name)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass


def ensure_verification_tables():
    """
    Compatibility shim for Verify routes.
    Keeps the verification_votes table available across SQLite/Postgres.
    """
    fn = globals().get("ensure_verification_flag_column")
    if callable(fn):
        try:
            fn()
        except Exception:
            pass

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS verification_votes (
                    id SERIAL PRIMARY KEY,
                    submission_id INTEGER,
                    vote_type TEXT,
                    voter_name TEXT,
                    contact TEXT,
                    source_url TEXT,
                    created_at TEXT
                )
            """))
            for col_sql in [
                "ALTER TABLE verification_votes ADD COLUMN IF NOT EXISTS contact TEXT",
                "ALTER TABLE verification_votes ADD COLUMN IF NOT EXISTS source_url TEXT",
                "ALTER TABLE verification_votes ADD COLUMN IF NOT EXISTS voter_name TEXT",
                "ALTER TABLE verification_votes ADD COLUMN IF NOT EXISTS created_at TEXT",
            ]:
                try:
                    conn.execute(text(col_sql))
                except Exception:
                    pass
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS verification_votes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submission_id INTEGER,
                    vote_type TEXT,
                    voter_name TEXT,
                    contact TEXT,
                    source_url TEXT,
                    created_at TEXT
                )
            """))

            cols = conn.execute(text("PRAGMA table_info(verification_votes)")).fetchall()
            existing = {col[1] for col in cols}

            for col_name, col_type in [
                ("contact", "TEXT"),
                ("source_url", "TEXT"),
                ("voter_name", "TEXT"),
                ("created_at", "TEXT"),
            ]:
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE verification_votes ADD COLUMN {col_name} {col_type}"))


def parse_submission_details(record_or_details):
    import json

    if record_or_details is None:
        return {}

    raw = record_or_details

    try:
        if hasattr(record_or_details, "get") and record_or_details.get("details_json") is not None:
            raw = record_or_details.get("details_json")
    except Exception:
        pass

    try:
        if not isinstance(raw, (str, list, dict)) and raw["details_json"] is not None:
            raw = raw["details_json"]
    except Exception:
        pass

    if raw is None:
        return {}

    if isinstance(raw, (list, dict)):
        return raw

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}

        try:
            return json.loads(raw)
        except Exception:
            return {}

    return {}


def get_detail_value(record_or_details, label):
    details = parse_submission_details(record_or_details)

    def clean_value(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            return str(value)

        if isinstance(value, list):
            output = []
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("value")
                    note = item.get("note")
                    featuring = item.get("featuring")

                    if name and note:
                        output.append(f"{name} ({note})")
                    elif name:
                        output.append(str(name))
                    elif featuring:
                        output.append(", ".join(str(x) for x in featuring))
                    else:
                        output.append(str(item))
                else:
                    output.append(str(item))

            return " | ".join(output)

        if isinstance(value, dict):
            name = value.get("name") or value.get("title") or value.get("value")
            note = value.get("note")

            if name and note:
                return f"{name} ({note})"
            if name:
                return str(name)

            return ", ".join(f"{k}: {v}" for k, v in value.items())

        return str(value)

    def record_value(key):
        try:
            if hasattr(record_or_details, "get"):
                return record_or_details.get(key)
        except Exception:
            pass

        try:
            return record_or_details[key]
        except Exception:
            return None

    # Legacy format:
    # [{"label": "Event Date", "value": "2026-06-06"}, ...]
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict) and item.get("label") == label:
                return clean_value(item.get("value"))
        return ""

    # Structured format:
    # {"event_date": "2026-06-06", "time": "..."}
    if isinstance(details, dict):
        label_key_map = {
            "Event Name": ["event_name", "title"],
            "Organization Name": ["organization_name", "organizer", "series", "presented_by"],
            "Event Date": ["event_date", "date"],
            "Event Time": ["event_time", "time"],
            "Event Location": ["event_location", "location", "venue"],
            "Venue Notes": ["venue_notes", "note", "message"],
            "Battle Type": ["battle_type", "type"],
            "Age Restriction": ["age_restriction", "requirement"],
            "Entry": ["entry"],
            "Host": ["host", "hosted_by"],
            "Judges": ["judges", "special_guest_judges"],
            "Event Results": ["event_results", "results"],
            "Results Status": ["results_status"],
            "Needs Confirmation": ["needs_confirmation", "confirmation_needed"],
            "Archive Note": ["archive_note", "notes"],
            "Battle List": ["battle_list", "battles"],
            "Studio": ["studio", "venue"],
            "Borough": ["borough"],
            "End Results": ["end_results", "results"],
            "Organizer": ["organizer", "presented_by", "series", "related_to"],
            "Event Host": ["event_host", "host", "hosted_by"],
        }

        possible_keys = label_key_map.get(label, [])
        possible_keys.extend([
            label,
            label.lower(),
            label.lower().replace(" ", "_"),
        ])

        for key in possible_keys:
            if key in details and details.get(key) not in (None, ""):
                return clean_value(details.get(key))

        if label == "Event Name":
            return clean_value(record_value("title"))

        if label in ["Organization Name", "Organizer"]:
            return clean_value(record_value("related_to"))

    return ""


def detail_value_filter(record_or_details, label):
    return get_detail_value(record_or_details, label)


def event_organizer_name(event):
    return (
        get_detail_value(event, "Organizer")
        or get_detail_value(event, "Organization Name")
        or get_detail_value(event, "Event Host")
        or (event.get("related_to") if hasattr(event, "get") else "")
        or "LiteFeet Ledger"
    )


def event_public_url(event):
    try:
        event_id = event.get("id") if hasattr(event, "get") else event["id"]
    except Exception:
        event_id = ""

    if event_id:
        return f"/events/{event_id}"

    return "/events"


# Re-register filters so templates stop using the old list-only filter from line 60.
try:
    app.jinja_env.filters["detail_value"] = detail_value_filter
    app.jinja_env.filters["event_public_url"] = event_public_url
except Exception:
    pass


# --- People profile status simplification ---
def normalize_people_profile_status(status):
    value = (status or "").strip().lower()

    if value in {
        "active",
        "approved",
        "verified",
        "community supported",
        "claimed",
    }:
        return "Active"

    return "Inactive"



# --- Phase 2 Ledger data model helpers ---
def ledger_table_columns(conn, table_name):
    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
            """),
            {"table_name": table_name},
        ).fetchall()
        return {row[0] for row in rows}

    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def ledger_add_column_if_missing(conn, table_name, column_name, column_sql):
    existing_columns = ledger_table_columns(conn, table_name)

    if column_name in existing_columns:
        return

    if maintenance_uses_postgres():
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_sql}"))
    else:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def ensure_phase2_ledger_tables():
    id_column = "id SERIAL PRIMARY KEY" if maintenance_uses_postgres() else "id INTEGER PRIMARY KEY AUTOINCREMENT"

    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS ask_conversations (
                {id_column},
                user_id INTEGER,
                visitor_key TEXT,
                title TEXT,
                status TEXT DEFAULT 'open',
                source_context TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS ask_messages (
                {id_column},
                conversation_id INTEGER,
                sender_type TEXT,
                message_text TEXT,
                verification_status TEXT,
                source_url TEXT,
                created_at TEXT
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS community_perspectives (
                {id_column},
                related_type TEXT,
                related_id INTEGER,
                submission_id INTEGER,
                user_id INTEGER,
                perspective_text TEXT,
                source_url TEXT,
                perspective_status TEXT DEFAULT 'Pending Review',
                review_label TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS profile_claims (
                {id_column},
                user_id INTEGER,
                profile_type TEXT DEFAULT 'dancer',
                profile_id INTEGER,
                claimant_name TEXT,
                claimant_contact TEXT,
                claim_reason TEXT,
                proof_url TEXT,
                claim_status TEXT DEFAULT 'Pending Review',
                reviewed_by INTEGER,
                reviewed_at TEXT,
                created_at TEXT
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS saved_items (
                {id_column},
                user_id INTEGER,
                item_type TEXT,
                item_id INTEGER,
                label TEXT,
                notes TEXT,
                created_at TEXT
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS calendar_item_metadata (
                {id_column},
                submission_id INTEGER,
                calendar_type TEXT,
                recurrence_rule TEXT,
                borough TEXT,
                venue_name TEXT,
                flyer_url TEXT,
                cost_text TEXT,
                dj_names TEXT,
                host_names TEXT,
                judges_text TEXT,
                visibility_status TEXT DEFAULT 'public',
                created_at TEXT,
                updated_at TEXT
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS battle_records (
                {id_column},
                submission_id INTEGER,
                event_submission_id INTEGER,
                battle_type TEXT,
                competitor_one TEXT,
                competitor_two TEXT,
                competitor_one_team TEXT,
                competitor_two_team TEXT,
                winner TEXT,
                official_winner TEXT,
                judges_text TEXT,
                video_url TEXT,
                controversy_score INTEGER DEFAULT 0,
                community_input_status TEXT DEFAULT 'None',
                review_status TEXT DEFAULT 'Needs Review',
                created_at TEXT,
                updated_at TEXT
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS team_access_grants (
                {id_column},
                team_name TEXT,
                team_profile_id INTEGER,
                user_id INTEGER,
                access_role TEXT,
                granted_by_user_id INTEGER,
                status TEXT DEFAULT 'Pending Review',
                created_at TEXT,
                updated_at TEXT
            )
        """))

        table_columns = {
            "ask_conversations": {
                "user_id": "INTEGER",
                "visitor_key": "TEXT",
                "title": "TEXT",
                "status": "TEXT DEFAULT 'open'",
                "source_context": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            },
            "ask_messages": {
                "conversation_id": "INTEGER",
                "sender_type": "TEXT",
                "message_text": "TEXT",
                "verification_status": "TEXT",
                "source_url": "TEXT",
                "created_at": "TEXT",
            },
            "community_perspectives": {
                "related_type": "TEXT",
                "related_id": "INTEGER",
                "submission_id": "INTEGER",
                "user_id": "INTEGER",
                "perspective_text": "TEXT",
                "source_url": "TEXT",
                "perspective_status": "TEXT DEFAULT 'Pending Review'",
                "review_label": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            },
            "profile_claims": {
                "user_id": "INTEGER",
                "profile_type": "TEXT DEFAULT 'dancer'",
                "profile_id": "INTEGER",
                "claimant_name": "TEXT",
                "claimant_contact": "TEXT",
                "claim_reason": "TEXT",
                "proof_url": "TEXT",
                "claim_status": "TEXT DEFAULT 'Pending Review'",
                "reviewed_by": "INTEGER",
                "reviewed_at": "TEXT",
                "created_at": "TEXT",
            },
            "saved_items": {
                "user_id": "INTEGER",
                "item_type": "TEXT",
                "item_id": "INTEGER",
                "label": "TEXT",
                "notes": "TEXT",
                "created_at": "TEXT",
            },
            "calendar_item_metadata": {
                "submission_id": "INTEGER",
                "calendar_type": "TEXT",
                "recurrence_rule": "TEXT",
                "borough": "TEXT",
                "venue_name": "TEXT",
                "flyer_url": "TEXT",
                "cost_text": "TEXT",
                "dj_names": "TEXT",
                "host_names": "TEXT",
                "judges_text": "TEXT",
                "visibility_status": "TEXT DEFAULT 'public'",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            },
            "battle_records": {
                "submission_id": "INTEGER",
                "event_submission_id": "INTEGER",
                "battle_type": "TEXT",
                "competitor_one": "TEXT",
                "competitor_two": "TEXT",
                "competitor_one_team": "TEXT",
                "competitor_two_team": "TEXT",
                "winner": "TEXT",
                "official_winner": "TEXT",
                "judges_text": "TEXT",
                "video_url": "TEXT",
                "controversy_score": "INTEGER DEFAULT 0",
                "community_input_status": "TEXT DEFAULT 'None'",
                "review_status": "TEXT DEFAULT 'Needs Review'",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            },
            "team_access_grants": {
                "team_name": "TEXT",
                "team_profile_id": "INTEGER",
                "user_id": "INTEGER",
                "access_role": "TEXT",
                "granted_by_user_id": "INTEGER",
                "status": "TEXT DEFAULT 'Pending Review'",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            },
        }

        for table_name, columns in table_columns.items():
            for column_name, column_sql in columns.items():
                ledger_add_column_if_missing(conn, table_name, column_name, column_sql)


try:
    ensure_phase2_ledger_tables()
except Exception as phase2_error:
    print(f"Phase 2 Ledger table setup skipped: {phase2_error}")


# --- Phase 2C Ask beta routes ---
def ledger_insert_and_get_id(table_name, values):
    columns = list(values.keys())
    columns_sql = ", ".join(columns)
    values_sql = ", ".join(f":{column}" for column in columns)

    with engine.begin() as conn:
        if maintenance_uses_postgres():
            result = conn.execute(
                text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql}) RETURNING id"),
                values,
            )
            return result.scalar()

        result = conn.execute(
            text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql})"),
            values,
        )
        return result.lastrowid


def ask_beta_user_key():
    import uuid

    user = current_user()
    if user:
        return user["id"], None

    if session.get("admin_logged_in"):
        visitor_key = session.get("ask_admin_visitor_key")
        if not visitor_key:
            visitor_key = f"admin-{uuid.uuid4().hex}"
            session["ask_admin_visitor_key"] = visitor_key
        return None, visitor_key

    visitor_key = session.get("ask_visitor_key")
    if not visitor_key:
        visitor_key = f"visitor-{uuid.uuid4().hex}"
        session["ask_visitor_key"] = visitor_key

    return None, visitor_key


def fetch_ask_conversation(conversation_id):
    ensure_phase2_ledger_tables()

    rows = fetch_all(
        """
        SELECT *
        FROM ask_conversations
        WHERE id = :conversation_id
        LIMIT 1
        """,
        {"conversation_id": conversation_id},
    )

    return rows[0] if rows else None


def can_view_ask_conversation(conversation):
    if not conversation:
        return False

    if session.get("admin_logged_in"):
        return True

    user = current_user()
    if user and conversation["user_id"] == user["id"]:
        return True

    visitor_key = session.get("ask_visitor_key") or session.get("ask_admin_visitor_key")
    if visitor_key and conversation["visitor_key"] == visitor_key:
        return True

    return False


@app.context_processor
def inject_ask_beta_context():
    try:
        ensure_phase2_ledger_tables()

        if not (current_user() or session.get("admin_logged_in")):
            return {"recent_ask_conversations": []}

        user_id, visitor_key = ask_beta_user_key()

        if user_id:
            conversations = fetch_all(
                """
                SELECT *
                FROM ask_conversations
                WHERE user_id = :user_id
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 8
                """,
                {"user_id": user_id},
            )
        elif session.get("admin_logged_in"):
            conversations = fetch_all(
                """
                SELECT *
                FROM ask_conversations
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 8
                """,
                {},
            )
        else:
            conversations = fetch_all(
                """
                SELECT *
                FROM ask_conversations
                WHERE visitor_key = :visitor_key
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 8
                """,
                {"visitor_key": visitor_key},
            )

        return {"recent_ask_conversations": conversations}
    except Exception:
        return {"recent_ask_conversations": []}


@app.route("/ask/submit", methods=["POST"])
def ask_beta_submit():
    ensure_phase2_ledger_tables()

    if not (current_user() or session.get("admin_logged_in")):
        return redirect(url_for("account_login"))

    question = request.form.get("question", "").strip()
    source_url = request.form.get("source_url", "").strip()
    context_note = request.form.get("context_note", "").strip()

    if len(question) < 3:
        return redirect(url_for("ask_archive"))

    now_value = datetime.now().isoformat(timespec="seconds")
    user_id, visitor_key = ask_beta_user_key()

    title = question[:80]
    if len(question) > 80:
        title = title.rstrip() + "..."

    conversation_id = ledger_insert_and_get_id(
        "ask_conversations",
        {
            "user_id": user_id,
            "visitor_key": visitor_key,
            "title": title,
            "status": "open",
            "source_context": context_note,
            "created_at": now_value,
            "updated_at": now_value,
        },
    )

    ledger_insert_and_get_id(
        "ask_messages",
        {
            "conversation_id": conversation_id,
            "sender_type": "user",
            "message_text": question,
            "verification_status": "Submitted",
            "source_url": source_url,
            "created_at": now_value,
        },
    )

    beta_reply = (
        "This Ask beta record was saved. The next build step will connect questions to real Ledger search, "
        "separate Verified / Community Supported / Debated / Unknown context, and allow community perspective records "
        "when someone disagrees or adds proof."
    )

    ledger_insert_and_get_id(
        "ask_messages",
        {
            "conversation_id": conversation_id,
            "sender_type": "ledger",
            "message_text": beta_reply,
            "verification_status": "Beta Placeholder",
            "source_url": "",
            "created_at": now_value,
        },
    )

    return redirect(url_for("ask_conversation_detail", conversation_id=conversation_id))


@app.route("/ask/conversations/<int:conversation_id>")
def ask_conversation_detail(conversation_id):
    ensure_phase2_ledger_tables()

    conversation = fetch_ask_conversation(conversation_id)
    if not can_view_ask_conversation(conversation):
        return redirect(url_for("ask_archive"))

    messages = fetch_all(
        """
        SELECT *
        FROM ask_messages
        WHERE conversation_id = :conversation_id
        ORDER BY created_at ASC, id ASC
        """,
        {"conversation_id": conversation_id},
    )

    return render_template(
        "ask_conversation.html",
        conversation=conversation,
        messages=messages,
    )


# --- Phase 2D profile claims and saved items ---
@app.context_processor
def inject_account_phase2_dashboard_data():
    try:
        ensure_phase2_ledger_tables()

        user = current_user()
        if not user:
            return {
                "profile_claims": [],
                "saved_items": [],
                "user_submissions": [],
            }

        user_submissions = fetch_all(
            """
            SELECT *
            FROM submissions
            WHERE contributor_user_id = :user_id
               OR lower(contact) = lower(:email)
               OR lower(submitter_name) = lower(:display_name)
            ORDER BY created_at DESC
            LIMIT 20
            """,
            {
                "user_id": user["id"],
                "email": user["email"] or "",
                "display_name": user["display_name"] or "",
            },
        )

        profile_claims = fetch_all(
            """
            SELECT profile_claims.*,
                   dancer_profiles.dance_name,
                   dancer_profiles.profile_slug,
                   dancer_profiles.team_affiliation
            FROM profile_claims
            LEFT JOIN dancer_profiles
              ON profile_claims.profile_type = 'dancer'
             AND profile_claims.profile_id = dancer_profiles.id
            WHERE profile_claims.user_id = :user_id
            ORDER BY profile_claims.created_at DESC
            LIMIT 20
            """,
            {"user_id": user["id"]},
        )

        saved_items = fetch_all(
            """
            SELECT *
            FROM saved_items
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT 30
            """,
            {"user_id": user["id"]},
        )

        return {
            "user_submissions": user_submissions,
            "profile_claims": profile_claims,
            "saved_items": saved_items,
        }
    except Exception:
        return {
            "profile_claims": [],
            "saved_items": [],
            "user_submissions": [],
        }


@app.route("/account/profile-claims", methods=["POST"])
def submit_profile_claim_phase2():
    ensure_phase2_ledger_tables()

    user = current_user()
    if not user:
        return redirect(url_for("account_login"))

    profile_type = request.form.get("profile_type", "dancer").strip() or "dancer"
    profile_id_raw = request.form.get("profile_id", "").strip()
    claim_reason = request.form.get("claim_reason", "").strip()
    proof_url = request.form.get("proof_url", "").strip()

    try:
        profile_id = int(profile_id_raw)
    except Exception:
        return redirect(url_for("dancers"))

    now_value = datetime.now().isoformat(timespec="seconds")

    existing = fetch_all(
        """
        SELECT id
        FROM profile_claims
        WHERE user_id = :user_id
          AND profile_type = :profile_type
          AND profile_id = :profile_id
          AND claim_status IN ('Pending Review', 'Approved')
        LIMIT 1
        """,
        {
            "user_id": user["id"],
            "profile_type": profile_type,
            "profile_id": profile_id,
        },
    )

    if not existing:
        execute_query(
            """
            INSERT INTO profile_claims (
                user_id,
                profile_type,
                profile_id,
                claimant_name,
                claimant_contact,
                claim_reason,
                proof_url,
                claim_status,
                created_at
            )
            VALUES (
                :user_id,
                :profile_type,
                :profile_id,
                :claimant_name,
                :claimant_contact,
                :claim_reason,
                :proof_url,
                :claim_status,
                :created_at
            )
            """,
            {
                "user_id": user["id"],
                "profile_type": profile_type,
                "profile_id": profile_id,
                "claimant_name": user["display_name"] or "",
                "claimant_contact": user["email"] or "",
                "claim_reason": claim_reason,
                "proof_url": proof_url,
                "claim_status": "Pending Review",
                "created_at": now_value,
            },
        )

    return redirect(request.referrer or url_for("account_home"))


@app.route("/account/save-item", methods=["POST"])
def save_ledger_item():
    ensure_phase2_ledger_tables()

    user = current_user()
    if not user:
        return redirect(url_for("account_login"))

    item_type = request.form.get("item_type", "").strip()
    item_id_raw = request.form.get("item_id", "").strip()
    label = request.form.get("label", "").strip()
    notes = request.form.get("notes", "").strip()

    if not item_type or not item_id_raw:
        return redirect(request.referrer or url_for("account_home"))

    try:
        item_id = int(item_id_raw)
    except Exception:
        return redirect(request.referrer or url_for("account_home"))

    existing = fetch_all(
        """
        SELECT id
        FROM saved_items
        WHERE user_id = :user_id
          AND item_type = :item_type
          AND item_id = :item_id
        LIMIT 1
        """,
        {
            "user_id": user["id"],
            "item_type": item_type,
            "item_id": item_id,
        },
    )

    now_value = datetime.now().isoformat(timespec="seconds")

    if not existing:
        execute_query(
            """
            INSERT INTO saved_items (
                user_id,
                item_type,
                item_id,
                label,
                notes,
                created_at
            )
            VALUES (
                :user_id,
                :item_type,
                :item_id,
                :label,
                :notes,
                :created_at
            )
            """,
            {
                "user_id": user["id"],
                "item_type": item_type,
                "item_id": item_id,
                "label": label,
                "notes": notes,
                "created_at": now_value,
            },
        )

    return redirect(request.referrer or url_for("account_home"))


@app.route("/account/saved-items/<int:saved_item_id>/delete", methods=["POST"])
def delete_saved_ledger_item(saved_item_id):
    ensure_phase2_ledger_tables()

    user = current_user()
    if not user:
        return redirect(url_for("account_login"))

    execute_query(
        """
        DELETE FROM saved_items
        WHERE id = :saved_item_id
          AND user_id = :user_id
        """,
        {
            "saved_item_id": saved_item_id,
            "user_id": user["id"],
        },
    )

    return redirect(request.referrer or url_for("account_home"))


# --- Phase 2E structured battle records ---
def phase2_insert_and_get_id(table_name, values):
    helper = globals().get("ledger_insert_and_get_id")
    if callable(helper):
        return helper(table_name, values)

    columns = list(values.keys())
    columns_sql = ", ".join(columns)
    values_sql = ", ".join(f":{column}" for column in columns)

    with engine.begin() as conn:
        if maintenance_uses_postgres():
            result = conn.execute(
                text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql}) RETURNING id"),
                values,
            )
            return result.scalar()

        result = conn.execute(
            text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql})"),
            values,
        )
        return result.lastrowid


@app.context_processor
def inject_phase2_battle_records():
    try:
        ensure_phase2_ledger_tables()

        structured_battle_records = fetch_all(
            """
            SELECT *
            FROM battle_records
            ORDER BY
                CASE WHEN updated_at IS NULL OR updated_at = '' THEN created_at ELSE updated_at END DESC,
                id DESC
            LIMIT 200
            """,
            {},
        )

        return {"structured_battle_records": structured_battle_records}
    except Exception:
        return {"structured_battle_records": []}


@app.route("/battles/add", methods=["GET", "POST"])
def battle_submit_phase2():
    ensure_phase2_ledger_tables()

    if request.method == "GET":
        return render_template("battle_submit.html")

    battle_type = request.form.get("battle_type", "").strip()
    competitor_one = request.form.get("competitor_one", "").strip()
    competitor_two = request.form.get("competitor_two", "").strip()
    competitor_one_team = request.form.get("competitor_one_team", "").strip()
    competitor_two_team = request.form.get("competitor_two_team", "").strip()
    winner = request.form.get("winner", "").strip()
    official_winner = request.form.get("official_winner", "").strip()
    event_name = request.form.get("event_name", "").strip()
    event_date = request.form.get("event_date", "").strip()
    judges_text = request.form.get("judges_text", "").strip()
    video_url = request.form.get("video_url", "").strip()
    community_input_status = request.form.get("community_input_status", "").strip() or "None"
    context_note = request.form.get("context_note", "").strip()
    submitter_name = request.form.get("submitter_name", "").strip()
    submitter_role = request.form.get("submitter_role", "").strip()
    contact = request.form.get("contact", "").strip()

    user = current_user()
    now_value = datetime.now().isoformat(timespec="seconds")

    if user:
        submitter_name = submitter_name or user["display_name"] or ""
        contact = contact or user["email"] or ""

    title_parts = [part for part in [competitor_one, "vs", competitor_two] if part]
    title = " ".join(title_parts).strip() or "Battle record"

    related_to = event_name or "Battle Records"

    details = [
        {"label": "Battle Type", "value": battle_type},
        {"label": "Competitor One", "value": competitor_one},
        {"label": "Competitor Two", "value": competitor_two},
        {"label": "Competitor One Team", "value": competitor_one_team},
        {"label": "Competitor Two Team", "value": competitor_two_team},
        {"label": "Winner", "value": winner},
        {"label": "Official Winner", "value": official_winner},
        {"label": "Event Name", "value": event_name},
        {"label": "Event Date", "value": event_date},
        {"label": "Judges", "value": judges_text},
        {"label": "Video URL", "value": video_url},
        {"label": "Community Input Status", "value": community_input_status},
        {"label": "Context Note", "value": context_note},
    ]

    details = [item for item in details if item["value"]]

    submission_id = phase2_insert_and_get_id(
        "submissions",
        {
            "submission_type": "battle_record",
            "title": title,
            "related_to": related_to,
            "source_url": video_url,
            "submitter_name": submitter_name,
            "submitter_role": submitter_role,
            "contact": contact,
            "needs_verification": 1,
            "review_status": "Pending Review",
            "details_json": json.dumps(details, ensure_ascii=False),
            "created_at": now_value,
            "contributor_user_id": user["id"] if user else None,
            "anonymous_submission": 0,
        },
    )

    battle_id = phase2_insert_and_get_id(
        "battle_records",
        {
            "submission_id": submission_id,
            "event_submission_id": None,
            "battle_type": battle_type,
            "competitor_one": competitor_one,
            "competitor_two": competitor_two,
            "competitor_one_team": competitor_one_team,
            "competitor_two_team": competitor_two_team,
            "winner": winner,
            "official_winner": official_winner,
            "judges_text": judges_text,
            "video_url": video_url,
            "controversy_score": 0,
            "community_input_status": community_input_status,
            "review_status": "Needs Review",
            "created_at": now_value,
            "updated_at": now_value,
        },
    )

    return redirect(url_for("battle_record_detail_phase2", battle_id=battle_id))


@app.route("/battle-records/<int:battle_id>")
def battle_record_detail_phase2(battle_id):
    ensure_phase2_ledger_tables()

    rows = fetch_all(
        """
        SELECT *
        FROM battle_records
        WHERE id = :battle_id
        LIMIT 1
        """,
        {"battle_id": battle_id},
    )

    if not rows:
        return redirect(url_for("battles"))

    battle = rows[0]
    submission = None

    if battle["submission_id"]:
        submission_rows = fetch_all(
            """
            SELECT *
            FROM submissions
            WHERE id = :submission_id
            LIMIT 1
            """,
            {"submission_id": battle["submission_id"]},
        )
        submission = submission_rows[0] if submission_rows else None

    return render_template(
        "battle_record_detail.html",
        battle=battle,
        submission=submission,
    )


# --- Phase 2F calendar metadata helpers and routes ---
def phase2_safe_insert_and_get_id(table_name, values):
    helper = globals().get("phase2_insert_and_get_id") or globals().get("ledger_insert_and_get_id")
    if callable(helper):
        return helper(table_name, values)

    columns = list(values.keys())
    columns_sql = ", ".join(columns)
    values_sql = ", ".join(f":{column}" for column in columns)

    with engine.begin() as conn:
        if maintenance_uses_postgres():
            result = conn.execute(
                text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql}) RETURNING id"),
                values,
            )
            return result.scalar()

        result = conn.execute(
            text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql})"),
            values,
        )
        return result.lastrowid


def fetch_calendar_metadata(submission_id):
    ensure_phase2_ledger_tables()

    rows = fetch_all(
        """
        SELECT *
        FROM calendar_item_metadata
        WHERE submission_id = :submission_id
        LIMIT 1
        """,
        {"submission_id": submission_id},
    )

    return rows[0] if rows else None


def calendar_metadata_values_from_form(submission_id, form_data):
    now_value = datetime.now().isoformat(timespec="seconds")

    return {
        "submission_id": submission_id,
        "calendar_type": (
            form_data.get("calendar_type", "").strip()
            or form_data.get("event_timing", "").strip()
        ),
        "recurrence_rule": form_data.get("recurrence_rule", "").strip(),
        "borough": form_data.get("borough", "").strip(),
        "venue_name": form_data.get("venue_name", "").strip(),
        "flyer_url": (
            form_data.get("flyer_url", "").strip()
            or form_data.get("source_url", "").strip()
        ),
        "cost_text": form_data.get("cost_text", "").strip(),
        "dj_names": form_data.get("dj_names", "").strip(),
        "host_names": form_data.get("host_names", "").strip(),
        "judges_text": (
            form_data.get("judges_text", "").strip()
            or form_data.get("event_judges", "").strip()
        ),
        "visibility_status": form_data.get("visibility_status", "public").strip() or "public",
        "created_at": now_value,
        "updated_at": now_value,
    }


def upsert_calendar_metadata(submission_id, form_data):
    ensure_phase2_ledger_tables()

    values = calendar_metadata_values_from_form(submission_id, form_data)
    existing = fetch_calendar_metadata(submission_id)

    if existing:
        update_values = dict(values)
        update_values["metadata_id"] = existing["id"]

        execute_query(
            """
            UPDATE calendar_item_metadata
            SET calendar_type = :calendar_type,
                recurrence_rule = :recurrence_rule,
                borough = :borough,
                venue_name = :venue_name,
                flyer_url = :flyer_url,
                cost_text = :cost_text,
                dj_names = :dj_names,
                host_names = :host_names,
                judges_text = :judges_text,
                visibility_status = :visibility_status,
                updated_at = :updated_at
            WHERE id = :metadata_id
            """,
            update_values,
        )

        return existing["id"]

    return phase2_safe_insert_and_get_id("calendar_item_metadata", values)


@app.context_processor
def inject_calendar_metadata_helpers():
    return {
        "calendar_metadata_for": fetch_calendar_metadata,
    }


@app.route("/calendar/items/<int:event_id>/metadata", methods=["POST"])
def update_calendar_metadata_phase2(event_id):
    ensure_phase2_ledger_tables()

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
        return redirect(url_for("events"))

    event = events[0]
    user = current_user()

    can_edit = bool(session.get("admin_logged_in"))

    if user and event["contributor_user_id"] and event["contributor_user_id"] == user["id"]:
        can_edit = True

    if not can_edit:
        return redirect(url_for("account_login"))

    upsert_calendar_metadata(event_id, request.form)

    return redirect(url_for("event_detail", event_id=event_id))


# --- Phase 2G community perspective records ---
def phase2g_add_column_if_missing(conn, table_name, column_name, column_sql):
    if "ledger_table_columns" in globals():
        existing_columns = ledger_table_columns(conn, table_name)
    elif maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
            """),
            {"table_name": table_name},
        ).fetchall()
        existing_columns = {row[0] for row in rows}
    else:
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        existing_columns = {row[1] for row in rows}

    if column_name in existing_columns:
        return

    if maintenance_uses_postgres():
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_sql}"))
    else:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def ensure_phase2g_community_perspective_columns():
    ensure_phase2_ledger_tables()

    with engine.begin() as conn:
        phase2g_add_column_if_missing(conn, "community_perspectives", "submitter_name", "TEXT")
        phase2g_add_column_if_missing(conn, "community_perspectives", "submitter_contact", "TEXT")
        phase2g_add_column_if_missing(conn, "community_perspectives", "anonymous_input", "INTEGER DEFAULT 0")


def phase2g_insert_and_get_id(table_name, values):
    helper = (
        globals().get("phase2_safe_insert_and_get_id")
        or globals().get("phase2_insert_and_get_id")
        or globals().get("ledger_insert_and_get_id")
    )

    if callable(helper):
        return helper(table_name, values)

    columns = list(values.keys())
    columns_sql = ", ".join(columns)
    values_sql = ", ".join(f":{column}" for column in columns)

    with engine.begin() as conn:
        if maintenance_uses_postgres():
            result = conn.execute(
                text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql}) RETURNING id"),
                values,
            )
            return result.scalar()

        result = conn.execute(
            text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql})"),
            values,
        )
        return result.lastrowid


def phase2g_optional_int(value):
    value = str(value or "").strip()

    if not value:
        return None

    try:
        return int(value)
    except Exception:
        return None


def fetch_community_perspectives_for(related_type=None, related_id=None, submission_id=None, limit=25):
    ensure_phase2g_community_perspective_columns()

    clauses = ["COALESCE(perspective_status, '') != 'Rejected'"]
    params = {"limit": limit}

    if related_type:
        clauses.append("related_type = :related_type")
        params["related_type"] = related_type

    if related_id not in (None, ""):
        clauses.append("related_id = :related_id")
        params["related_id"] = int(related_id)

    if submission_id not in (None, ""):
        clauses.append("submission_id = :submission_id")
        params["submission_id"] = int(submission_id)

    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""

    return fetch_all(
        f"""
        SELECT *
        FROM community_perspectives
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """,
        params,
    )


def fetch_community_perspective(perspective_id):
    ensure_phase2g_community_perspective_columns()

    rows = fetch_all(
        """
        SELECT *
        FROM community_perspectives
        WHERE id = :perspective_id
        LIMIT 1
        """,
        {"perspective_id": perspective_id},
    )

    return rows[0] if rows else None


def community_perspective_related_url(record):
    if not record:
        return url_for("verify_claims")

    related_type = record["related_type"] or ""
    related_id = record["related_id"]

    if related_type in {"event", "calendar", "submission"} and related_id:
        return f"/events/{related_id}"

    if related_type in {"battle", "battle_record"} and related_id:
        return f"/battle-records/{related_id}"

    if related_type in {"profile", "dancer"} and related_id:
        rows = fetch_all(
            """
            SELECT *
            FROM dancer_profiles
            WHERE id = :profile_id
            LIMIT 1
            """,
            {"profile_id": related_id},
        )
        if rows:
            return profile_url(rows[0])
        return f"/dancers/{related_id}"

    if related_type in {"music", "music_release"} and related_id:
        try:
            return url_for("music_release_detail", item_id=related_id)
        except Exception:
            return url_for("litefeet_music")

    return url_for("verify_claims")


@app.context_processor
def inject_phase2g_community_perspectives():
    try:
        ensure_phase2g_community_perspective_columns()

        recent = fetch_community_perspectives_for(limit=12)

        return {
            "recent_community_perspectives": recent,
            "community_perspectives_for": fetch_community_perspectives_for,
            "community_perspective_related_url": community_perspective_related_url,
        }
    except Exception:
        return {
            "recent_community_perspectives": [],
            "community_perspectives_for": lambda *args, **kwargs: [],
            "community_perspective_related_url": lambda record: url_for("verify_claims"),
        }


@app.route("/community-perspectives", methods=["POST"])
def submit_community_perspective_phase2g():
    ensure_phase2g_community_perspective_columns()

    related_type = request.form.get("related_type", "general").strip() or "general"
    related_id = phase2g_optional_int(request.form.get("related_id"))
    submission_id = phase2g_optional_int(request.form.get("submission_id"))
    perspective_text = request.form.get("perspective_text", "").strip()
    source_url = request.form.get("source_url", "").strip()
    review_label = request.form.get("review_label", "Community Perspective").strip() or "Community Perspective"
    submitter_name = request.form.get("submitter_name", "").strip()
    submitter_contact = request.form.get("submitter_contact", "").strip()
    anonymous_input = 1 if request.form.get("anonymous_input") == "yes" else 0
    return_to = request.form.get("return_to", "").strip()

    user = current_user()

    if user and not submitter_name:
        submitter_name = user["display_name"] or ""

    if user and not submitter_contact:
        submitter_contact = user["email"] or ""

    if len(perspective_text) < 3:
        if return_to.startswith("/"):
            return redirect(return_to)
        return redirect(url_for("verify_claims"))

    now_value = datetime.now().isoformat(timespec="seconds")

    perspective_id = phase2g_insert_and_get_id(
        "community_perspectives",
        {
            "related_type": related_type,
            "related_id": related_id,
            "submission_id": submission_id,
            "user_id": user["id"] if user else None,
            "perspective_text": perspective_text,
            "source_url": source_url,
            "perspective_status": "Pending Review",
            "review_label": review_label,
            "submitter_name": submitter_name,
            "submitter_contact": submitter_contact,
            "anonymous_input": anonymous_input,
            "created_at": now_value,
            "updated_at": now_value,
        },
    )

    if return_to.startswith("/"):
        return redirect(return_to)

    return redirect(url_for("community_perspective_detail_phase2g", perspective_id=perspective_id))


@app.route("/community-perspectives/<int:perspective_id>")
def community_perspective_detail_phase2g(perspective_id):
    perspective = fetch_community_perspective(perspective_id)

    if not perspective:
        return redirect(url_for("verify_claims"))

    return render_template(
        "community_perspective_detail.html",
        perspective=perspective,
        related_url=community_perspective_related_url(perspective),
    )


# --- Phase 2H admin moderation for Phase 2 tables ---
def phase2h_admin_required():
    if not current_user_is_admin():
        return redirect(url_for("admin_login"))
    return None


def phase2h_ensure_all_tables():
    ensure_phase2_ledger_tables()

    phase2g_helper = globals().get("ensure_phase2g_community_perspective_columns")
    if callable(phase2g_helper):
        phase2g_helper()


@app.route("/admin/phase2")
@app.route("/admin/phase2-moderation")
def admin_phase2_moderation():
    gate = phase2h_admin_required()
    if gate:
        return gate

    phase2h_ensure_all_tables()

    profile_claims = fetch_all(
        """
        SELECT profile_claims.*,
               dancer_profiles.dance_name,
               dancer_profiles.profile_slug,
               dancer_profiles.team_affiliation,
               archive_users.display_name AS user_display_name,
               archive_users.email AS user_email
        FROM profile_claims
        LEFT JOIN dancer_profiles
          ON profile_claims.profile_type = 'dancer'
         AND profile_claims.profile_id = dancer_profiles.id
        LEFT JOIN archive_users
          ON profile_claims.user_id = archive_users.id
        ORDER BY profile_claims.created_at DESC, profile_claims.id DESC
        LIMIT 100
        """,
        {},
    )

    community_perspectives = fetch_all(
        """
        SELECT *
        FROM community_perspectives
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        {},
    )

    battle_records = fetch_all(
        """
        SELECT *
        FROM battle_records
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT 100
        """,
        {},
    )

    ask_conversations = fetch_all(
        """
        SELECT ask_conversations.*,
               archive_users.display_name,
               archive_users.email
        FROM ask_conversations
        LEFT JOIN archive_users
          ON ask_conversations.user_id = archive_users.id
        ORDER BY ask_conversations.updated_at DESC, ask_conversations.created_at DESC, ask_conversations.id DESC
        LIMIT 100
        """,
        {},
    )

    calendar_metadata = fetch_all(
        """
        SELECT calendar_item_metadata.*,
               submissions.title,
               submissions.related_to,
               submissions.review_status
        FROM calendar_item_metadata
        LEFT JOIN submissions
          ON calendar_item_metadata.submission_id = submissions.id
        ORDER BY calendar_item_metadata.updated_at DESC, calendar_item_metadata.created_at DESC, calendar_item_metadata.id DESC
        LIMIT 100
        """,
        {},
    )

    return render_template(
        "admin_phase2_moderation.html",
        profile_claims=profile_claims,
        community_perspectives=community_perspectives,
        battle_records=battle_records,
        ask_conversations=ask_conversations,
        calendar_metadata=calendar_metadata,
    )


@app.route("/admin/phase2/profile-claims/<int:claim_id>/status", methods=["POST"])
def admin_phase2_profile_claim_status(claim_id):
    gate = phase2h_admin_required()
    if gate:
        return gate

    phase2h_ensure_all_tables()

    new_status = request.form.get("claim_status", "").strip()
    allowed = {"Pending Review", "Approved", "Rejected", "Needs Follow-up"}

    if new_status not in allowed:
        return redirect(url_for("admin_phase2_moderation"))

    execute_query(
        """
        UPDATE profile_claims
        SET claim_status = :claim_status,
            reviewed_by = NULL,
            reviewed_at = :reviewed_at
        WHERE id = :claim_id
        """,
        {
            "claim_status": new_status,
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            "claim_id": claim_id,
        },
    )

    return redirect(url_for("admin_phase2_moderation"))


@app.route("/admin/phase2/community-perspectives/<int:perspective_id>/status", methods=["POST"])
def admin_phase2_community_perspective_status(perspective_id):
    gate = phase2h_admin_required()
    if gate:
        return gate

    phase2h_ensure_all_tables()

    new_status = request.form.get("perspective_status", "").strip()
    review_label = request.form.get("review_label", "").strip()

    allowed = {"Pending Review", "Approved", "Community Supported", "Rejected", "Needs Verification", "Debated"}

    if new_status not in allowed:
        return redirect(url_for("admin_phase2_moderation"))

    execute_query(
        """
        UPDATE community_perspectives
        SET perspective_status = :perspective_status,
            review_label = :review_label,
            updated_at = :updated_at
        WHERE id = :perspective_id
        """,
        {
            "perspective_status": new_status,
            "review_label": review_label or "Community Perspective",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "perspective_id": perspective_id,
        },
    )

    return redirect(url_for("admin_phase2_moderation"))


@app.route("/admin/phase2/battle-records/<int:battle_id>/status", methods=["POST"])
def admin_phase2_battle_record_status(battle_id):
    gate = phase2h_admin_required()
    if gate:
        return gate

    phase2h_ensure_all_tables()

    review_status = request.form.get("review_status", "").strip()
    community_input_status = request.form.get("community_input_status", "").strip()
    controversy_score_raw = request.form.get("controversy_score", "0").strip()

    allowed_review = {"Needs Review", "Verified", "Community Supported", "Disputed", "Rejected"}
    allowed_community = {"None", "Community Supported", "Debated", "Needs Context", "Disputed"}

    if review_status not in allowed_review:
        return redirect(url_for("admin_phase2_moderation"))

    if community_input_status not in allowed_community:
        community_input_status = "None"

    try:
        controversy_score = int(controversy_score_raw)
    except Exception:
        controversy_score = 0

    controversy_score = max(0, min(100, controversy_score))

    execute_query(
        """
        UPDATE battle_records
        SET review_status = :review_status,
            community_input_status = :community_input_status,
            controversy_score = :controversy_score,
            updated_at = :updated_at
        WHERE id = :battle_id
        """,
        {
            "review_status": review_status,
            "community_input_status": community_input_status,
            "controversy_score": controversy_score,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "battle_id": battle_id,
        },
    )

    return redirect(url_for("admin_phase2_moderation"))


@app.route("/admin/phase2/calendar-metadata/<int:metadata_id>/visibility", methods=["POST"])
def admin_phase2_calendar_metadata_visibility(metadata_id):
    gate = phase2h_admin_required()
    if gate:
        return gate

    phase2h_ensure_all_tables()

    visibility_status = request.form.get("visibility_status", "").strip()
    allowed = {"public", "hidden", "needs_review"}

    if visibility_status not in allowed:
        return redirect(url_for("admin_phase2_moderation"))

    execute_query(
        """
        UPDATE calendar_item_metadata
        SET visibility_status = :visibility_status,
            updated_at = :updated_at
        WHERE id = :metadata_id
        """,
        {
            "visibility_status": visibility_status,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "metadata_id": metadata_id,
        },
    )

    return redirect(url_for("admin_phase2_moderation"))


@app.route("/admin/phase2/ask-conversations/<int:conversation_id>/status", methods=["POST"])
def admin_phase2_ask_conversation_status(conversation_id):
    gate = phase2h_admin_required()
    if gate:
        return gate

    phase2h_ensure_all_tables()

    status = request.form.get("status", "").strip()
    allowed = {"open", "answered", "needs_review", "archived"}

    if status not in allowed:
        return redirect(url_for("admin_phase2_moderation"))

    execute_query(
        """
        UPDATE ask_conversations
        SET status = :status,
            updated_at = :updated_at
        WHERE id = :conversation_id
        """,
        {
            "status": status,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "conversation_id": conversation_id,
        },
    )

    return redirect(url_for("admin_phase2_moderation"))


# --- Phase 2I deploy status and release safety ---
def phase2i_admin_required():
    if not current_user_is_admin():
        return redirect(url_for("admin_login"))
    return None


def phase2i_table_exists(table_name):
    with engine.connect() as conn:
        if maintenance_uses_postgres():
            rows = conn.execute(
                text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                    LIMIT 1
                """),
                {"table_name": table_name},
            ).fetchall()
            return bool(rows)

        rows = conn.execute(
            text("""
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name = :table_name
                LIMIT 1
            """),
            {"table_name": table_name},
        ).fetchall()
        return bool(rows)


def phase2i_count_table(table_name):
    allowed_tables = {
        "submissions",
        "archive_users",
        "dancer_profiles",
        "media_items",
        "music_feedback",
        "music_play_events",
        "verification_votes",
        "role_requests",
        "ask_conversations",
        "ask_messages",
        "profile_claims",
        "saved_items",
        "calendar_item_metadata",
        "battle_records",
        "community_perspectives",
        "team_access_grants",
    }

    if table_name not in allowed_tables:
        return None

    try:
        rows = fetch_all(f"SELECT COUNT(*) AS count FROM {table_name}", {})
        return rows[0]["count"] if rows else 0
    except Exception:
        return None


def phase2i_setting_value(key, default=""):
    try:
        rows = fetch_all(
            """
            SELECT value
            FROM site_settings
            WHERE key = :key
            LIMIT 1
            """,
            {"key": key},
        )
        return rows[0]["value"] if rows else default
    except Exception:
        return default


@app.route("/admin/deploy-status")
def admin_deploy_status_phase2i():
    gate = phase2i_admin_required()
    if gate:
        return gate

    try:
        ensure_phase2_ledger_tables()
    except Exception:
        pass

    phase2g_helper = globals().get("ensure_phase2g_community_perspective_columns")
    if callable(phase2g_helper):
        try:
            phase2g_helper()
        except Exception:
            pass

    import os
    import sys

    expected_tables = [
        "submissions",
        "archive_users",
        "dancer_profiles",
        "media_items",
        "music_feedback",
        "music_play_events",
        "verification_votes",
        "role_requests",
        "ask_conversations",
        "ask_messages",
        "profile_claims",
        "saved_items",
        "calendar_item_metadata",
        "battle_records",
        "community_perspectives",
        "team_access_grants",
    ]

    table_status = []
    for table_name in expected_tables:
        exists = phase2i_table_exists(table_name)
        table_status.append(
            {
                "name": table_name,
                "exists": exists,
                "count": phase2i_count_table(table_name) if exists else None,
            }
        )

    env_status = {
        "database_dialect": engine.dialect.name,
        "maintenance_mode": phase2i_setting_value("maintenance_mode", "unknown"),
        "database_url_present": "yes" if os.environ.get("DATABASE_URL") else "no",
        "render": "yes" if os.environ.get("RENDER") else "no",
        "render_service_name": os.environ.get("RENDER_SERVICE_NAME", ""),
        "render_external_url": os.environ.get("RENDER_EXTERNAL_URL", ""),
        "render_git_commit": os.environ.get("RENDER_GIT_COMMIT", ""),
        "render_git_branch": os.environ.get("RENDER_GIT_BRANCH", ""),
        "python_version": sys.version.split()[0],
    }

    recent_submissions = fetch_all(
        """
        SELECT id, submission_type, title, review_status, created_at
        FROM submissions
        ORDER BY created_at DESC, id DESC
        LIMIT 10
        """,
        {},
    )

    return render_template(
        "admin_deploy_status.html",
        env_status=env_status,
        table_status=table_status,
        recent_submissions=recent_submissions,
    )


# --- Render health check hotfix ---
@app.route("/healthz")
def healthz():
    return "ok", 200


# --- Phase 3A Ask Ledger search ---
def phase3a_table_columns(table_name):
    with engine.connect() as conn:
        if maintenance_uses_postgres():
            rows = conn.execute(
                text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = :table_name
                """),
                {"table_name": table_name},
            ).fetchall()
            return {row[0] for row in rows}

        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        return {row[1] for row in rows}


def phase3a_table_exists(table_name):
    with engine.connect() as conn:
        if maintenance_uses_postgres():
            rows = conn.execute(
                text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                    LIMIT 1
                """),
                {"table_name": table_name},
            ).fetchall()
            return bool(rows)

        rows = conn.execute(
            text("""
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = :table_name
                LIMIT 1
            """),
            {"table_name": table_name},
        ).fetchall()
        return bool(rows)


def phase3a_row_to_dict(row):
    try:
        return dict(row._mapping)
    except Exception:
        return dict(row)


def phase3a_fetch_recent_rows(table_name, limit=350):
    allowed = {
        "submissions",
        "dancer_profiles",
        "battle_records",
        "calendar_item_metadata",
        "music_projects",
        "media_items",
        "community_perspectives",
    }

    if table_name not in allowed or not phase3a_table_exists(table_name):
        return []

    columns = phase3a_table_columns(table_name)

    if "updated_at" in columns:
        order_sql = "updated_at DESC"
    elif "created_at" in columns:
        order_sql = "created_at DESC"
    elif "id" in columns:
        order_sql = "id DESC"
    else:
        order_sql = "1"

    try:
        rows = fetch_all(
            f"""
            SELECT *
            FROM {table_name}
            ORDER BY {order_sql}
            LIMIT :limit
            """,
            {"limit": limit},
        )
        return [phase3a_row_to_dict(row) for row in rows]
    except Exception:
        return []


def phase3a_tokens(text_value):
    import re

    stop_words = {
        "the", "and", "for", "with", "from", "that", "this", "what", "who",
        "where", "when", "why", "how", "was", "were", "are", "is", "did",
        "does", "do", "a", "an", "to", "of", "in", "on", "at", "it", "as",
        "about", "tell", "me", "show", "list", "give", "ledger", "litefeet",
    }

    words = re.findall(r"[a-z0-9']{2,}", (text_value or "").lower())
    return [word for word in words if word not in stop_words]


def phase3a_compact_text(value, max_length=260):
    value = str(value or "").strip()

    if len(value) <= max_length:
        return value

    return value[: max_length - 3].rstrip() + "..."


def phase3a_record_title(table_name, row):
    if table_name == "dancer_profiles":
        return row.get("dance_name") or row.get("real_name") or f"Profile #{row.get('id')}"

    if table_name == "battle_records":
        one = row.get("competitor_one") or "Competitor 1"
        two = row.get("competitor_two") or "Competitor 2"
        return f"{one} vs {two}"

    if table_name == "calendar_item_metadata":
        submission_id = row.get("submission_id")
        if submission_id:
            event_rows = fetch_all(
                """
                SELECT title
                FROM submissions
                WHERE id = :submission_id
                LIMIT 1
                """,
                {"submission_id": submission_id},
            )
            if event_rows:
                return event_rows[0]["title"] or f"Calendar item #{submission_id}"
        return f"Calendar metadata #{row.get('id')}"

    if table_name == "community_perspectives":
        return row.get("review_label") or f"Community perspective #{row.get('id')}"

    return (
        row.get("title")
        or row.get("name")
        or row.get("track_title")
        or row.get("project_title")
        or f"{table_name} #{row.get('id')}"
    )


def phase3a_record_status(table_name, row):
    raw_status = (
        row.get("review_status")
        or row.get("perspective_status")
        or row.get("status")
        or row.get("community_input_status")
        or ""
    )

    status = str(raw_status or "").strip()

    lowered = status.lower()

    if "verified" in lowered:
        return "Verified"

    if "community supported" in lowered:
        return "Community Supported"

    if "debated" in lowered or "disputed" in lowered:
        return "Debated"

    if "needs" in lowered or "pending" in lowered:
        return "Needs Verification"

    if status:
        return status

    if table_name in {"submissions", "battle_records", "community_perspectives"}:
        return "Pending Review"

    return "Unknown"


def phase3a_record_type_label(table_name, row):
    labels = {
        "submissions": row.get("submission_type") or "Ledger Submission",
        "dancer_profiles": "Profile",
        "battle_records": "Battle Record",
        "calendar_item_metadata": "Calendar Metadata",
        "music_projects": "Music Project",
        "media_items": "Media Item",
        "community_perspectives": "Community Perspective",
    }

    return labels.get(table_name, "Ledger Record")


def phase3a_record_snippet(table_name, row):
    priority_fields = [
        "bio",
        "details_json",
        "perspective_text",
        "description",
        "event_details",
        "judges_text",
        "winner",
        "official_winner",
        "related_to",
        "team_affiliation",
        "borough",
        "venue_name",
        "calendar_type",
        "artist_name",
        "platform",
        "source_url",
        "url",
    ]

    parts = []

    for field in priority_fields:
        value = row.get(field)
        if value:
            parts.append(str(value))

    if not parts:
        for key, value in row.items():
            if key == "id" or value in (None, ""):
                continue
            parts.append(str(value))
            if len(parts) >= 4:
                break

    return phase3a_compact_text(" | ".join(parts), 320)


def phase3a_record_url(table_name, row):
    try:
        if table_name == "submissions":
            if row.get("submission_type") == "event":
                return url_for("event_detail", event_id=row.get("id"))
            return url_for("verify_submission", submission_id=row.get("id"))

        if table_name == "dancer_profiles":
            if row.get("profile_slug"):
                return url_for("dancer_profile_detail", profile_slug=row.get("profile_slug"))
            return f"/dancers/{row.get('id')}"

        if table_name == "battle_records":
            return url_for("battle_record_detail_phase2", battle_id=row.get("id"))

        if table_name == "calendar_item_metadata" and row.get("submission_id"):
            return url_for("event_detail", event_id=row.get("submission_id"))

        if table_name == "community_perspectives":
            return url_for("community_perspective_detail_phase2g", perspective_id=row.get("id"))

        if table_name in {"music_projects", "media_items"}:
            return url_for("litefeet_music")
    except Exception:
        pass

    return ""


def phase3a_record_source_url(row):
    return row.get("source_url") or row.get("url") or row.get("video_url") or row.get("flyer_url") or ""


def phase3a_search_ledger(question, limit=8):
    ensure_phase2_ledger_tables()

    phase2g_helper = globals().get("ensure_phase2g_community_perspective_columns")
    if callable(phase2g_helper):
        try:
            phase2g_helper()
        except Exception:
            pass

    tokens = phase3a_tokens(question)
    if not tokens:
        return []

    search_tables = [
        "submissions",
        "dancer_profiles",
        "battle_records",
        "calendar_item_metadata",
        "music_projects",
        "media_items",
        "community_perspectives",
    ]

    scored = []

    for table_name in search_tables:
        for row in phase3a_fetch_recent_rows(table_name):
            title = phase3a_record_title(table_name, row)
            snippet = phase3a_record_snippet(table_name, row)

            title_text = title.lower()
            full_text = " ".join(str(value or "") for value in row.values()).lower()

            score = 0

            for token in tokens:
                if token in title_text:
                    score += 8
                if token in full_text:
                    score += 2

            if score <= 0:
                continue

            status = phase3a_record_status(table_name, row)

            if status in {"Verified", "Community Supported"}:
                score += 2

            if status in {"Debated", "Needs Verification", "Pending Review"}:
                score += 1

            scored.append(
                {
                    "score": score,
                    "table": table_name,
                    "id": row.get("id"),
                    "title": title,
                    "type_label": phase3a_record_type_label(table_name, row),
                    "status": status,
                    "snippet": snippet,
                    "url": phase3a_record_url(table_name, row),
                    "source_url": phase3a_record_source_url(row),
                }
            )

    scored.sort(key=lambda item: item["score"], reverse=True)

    unique = []
    seen = set()

    for item in scored:
        key = (item["table"], item["id"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

        if len(unique) >= limit:
            break

    return unique


def phase3a_build_ask_answer(question, results):
    if not results:
        return (
            "I do not have a strong Ledger match for that yet.\n\n"
            "Status: Unknown / Needs Verification\n\n"
            "What this means: the Ledger does not currently have enough structured records, source links, "
            "or community perspectives connected to answer this confidently. This should be treated as an open research item."
        )

    verified_count = sum(1 for item in results if item["status"] in {"Verified", "Community Supported"})
    debated_count = sum(1 for item in results if item["status"] in {"Debated", "Needs Verification", "Pending Review"})

    lines = [
        "Here is what I found in the Ledger:",
        "",
        f"Question: {question}",
        "",
        f"Strong / supported matches: {verified_count}",
        f"Needs context / review matches: {debated_count}",
        "",
    ]

    for index, item in enumerate(results, start=1):
        lines.append(f"{index}. {item['title']}")
        lines.append(f"   Type: {item['type_label']}")
        lines.append(f"   Ledger status: {item['status']}")

        if item["snippet"]:
            lines.append(f"   Context: {item['snippet']}")

        if item["url"]:
            lines.append(f"   Ledger link: {item['url']}")

        if item["source_url"]:
            lines.append(f"   Source/proof: {item['source_url']}")

        lines.append("")

    lines.append(
        "Read this as a Ledger search summary, not a final historical ruling. "
        "Verified and Community Supported records carry more weight. Debated, Pending Review, "
        "or Needs Verification records should be checked with sources or community confirmation."
    )

    return "\n".join(lines)


def phase3a_insert_dynamic(table_name, values):
    columns = phase3a_table_columns(table_name)
    clean_values = {key: value for key, value in values.items() if key in columns}

    if not clean_values:
        return None

    helper = (
        globals().get("phase2g_insert_and_get_id")
        or globals().get("phase2_safe_insert_and_get_id")
        or globals().get("phase2_insert_and_get_id")
        or globals().get("ledger_insert_and_get_id")
    )

    if callable(helper):
        return helper(table_name, clean_values)

    columns_sql = ", ".join(clean_values.keys())
    values_sql = ", ".join(f":{key}" for key in clean_values.keys())

    with engine.begin() as conn:
        if maintenance_uses_postgres():
            result = conn.execute(
                text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql}) RETURNING id"),
                clean_values,
            )
            return result.scalar()

        result = conn.execute(
            text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql})"),
            clean_values,
        )
        return result.lastrowid


def phase3a_insert_ask_message(conversation_id, role, message_text, source_summary=""):
    now_value = datetime.now().isoformat(timespec="seconds")

    return phase3a_insert_dynamic(
        "ask_messages",
        {
            "conversation_id": conversation_id,
            "sender": role,
            "role": role,
            "message_role": role,
            "sender_type": role,
            "message_text": message_text,
            "content": message_text,
            "body": message_text,
            "source_summary": source_summary,
            "created_at": now_value,
            "updated_at": now_value,
        },
    )


@app.route("/ask/search", methods=["POST"])
def ask_ledger_search_phase3a():
    ensure_phase2_ledger_tables()

    user = current_user()
    is_admin = bool(session.get("admin_logged_in"))

    if not user and not is_admin:
        return redirect(url_for("account_login", next=url_for("ask_archive")))

    question = request.form.get("question", "").strip()

    if len(question) < 2:
        return redirect(url_for("ask_archive"))

    results = phase3a_search_ledger(question)
    answer = phase3a_build_ask_answer(question, results)

    now_value = datetime.now().isoformat(timespec="seconds")
    visitor_key = ""

    try:
        visitor_key = ask_beta_user_key()
    except Exception:
        visitor_key = session.get("visitor_key", "")

    if isinstance(visitor_key, (tuple, list)):
        visitor_key = next((str(item) for item in visitor_key if item), "")

    visitor_key = str(visitor_key or "")

    conversation_id = phase3a_insert_dynamic(
        "ask_conversations",
        {
            "user_id": user["id"] if user else None,
            "visitor_key": visitor_key,
            "title": phase3a_compact_text(question, 120),
            "status": "answered" if results else "needs_review",
            "created_at": now_value,
            "updated_at": now_value,
        },
    )

    source_summary = json.dumps(results, ensure_ascii=False)

    phase3a_insert_ask_message(conversation_id, "user", question)
    phase3a_insert_ask_message(conversation_id, "assistant", answer, source_summary)

    return redirect(url_for("ask_conversation_detail", conversation_id=conversation_id))


# --- Compatibility alias for older account routes ---
def get_current_user():
    return current_user()


# --- Phase 3A hotfix: dancer profile schema compatibility ---
def phase3a_hotfix_table_columns(conn, table_name):
    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
            """),
            {"table_name": table_name},
        ).fetchall()
        return {row[0] for row in rows}

    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def phase3a_hotfix_table_exists(conn, table_name):
    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                LIMIT 1
            """),
            {"table_name": table_name},
        ).fetchall()
        return bool(rows)

    rows = conn.execute(
        text("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = :table_name
            LIMIT 1
        """),
        {"table_name": table_name},
    ).fetchall()
    return bool(rows)


def phase3a_hotfix_add_column(conn, table_name, column_name, column_type="TEXT"):
    existing = phase3a_hotfix_table_columns(conn, table_name)

    if column_name in existing:
        return

    if maintenance_uses_postgres():
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type}"))
    else:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def ensure_phase3a_profile_columns():
    with engine.begin() as conn:
        if not phase3a_hotfix_table_exists(conn, "dancer_profiles"):
            return

        for column_name in [
            "role_tags",
            "profile_slug",
            "recent_battle",
            "aliases",
            "era",
            "style_notes",
            "signature_moves",
            "battle_history",
            "legacy_notes",
        ]:
            phase3a_hotfix_add_column(conn, "dancer_profiles", column_name, "TEXT")


try:
    ensure_phase3a_profile_columns()
except Exception as exc:
    print(f"Phase 3A profile schema hotfix skipped: {exc}")


# --- Phase 3B Ask ranking and answer quality ---
def phase3b_parse_details_json(value):
    if not value:
        return ""

    try:
        parsed = json.loads(value)
    except Exception:
        return str(value)

    parts = []

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                label = item.get("label") or item.get("name") or ""
                item_value = item.get("value") or item.get("text") or ""
                if item_value:
                    if label:
                        parts.append(f"{label}: {item_value}")
                    else:
                        parts.append(str(item_value))
            elif item:
                parts.append(str(item))

    elif isinstance(parsed, dict):
        for key, item_value in parsed.items():
            if item_value:
                parts.append(f"{key}: {item_value}")

    else:
        parts.append(str(parsed))

    return " | ".join(parts)


def phase3b_normalized_text(value):
    import re

    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9'\s]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def phase3b_status_weight(status):
    status = str(status or "").lower()

    if "verified" in status:
        return 10

    if "community supported" in status:
        return 8

    if "debated" in status or "disputed" in status:
        return 5

    if "needs" in status:
        return 3

    if "pending" in status:
        return 2

    return 1


def phase3b_table_weight(table_name):
    weights = {
        "submissions": 6,
        "dancer_profiles": 8,
        "battle_records": 9,
        "calendar_item_metadata": 6,
        "music_projects": 6,
        "media_items": 5,
        "community_perspectives": 7,
    }

    return weights.get(table_name, 1)


def phase3b_row_search_text(table_name, row):
    values = []

    for key, value in row.items():
        if value in (None, ""):
            continue

        if key == "details_json":
            values.append(phase3b_parse_details_json(value))
        else:
            values.append(str(value))

    if table_name == "calendar_item_metadata" and row.get("submission_id"):
        try:
            event_rows = fetch_all(
                """
                SELECT *
                FROM submissions
                WHERE id = :submission_id
                LIMIT 1
                """,
                {"submission_id": row.get("submission_id")},
            )
            if event_rows:
                event_row = phase3a_row_to_dict(event_rows[0])
                values.extend(str(value or "") for value in event_row.values())
        except Exception:
            pass

    return " ".join(values)


def phase3a_record_url(table_name, row):
    try:
        if table_name == "submissions":
            if row.get("submission_type") == "event":
                return url_for("event_detail", event_id=row.get("id"))
            return url_for("verify_claim_detail", submission_id=row.get("id"))

        if table_name == "dancer_profiles":
            if row.get("profile_slug"):
                return url_for("dancer_profile_detail", profile_slug=row.get("profile_slug"))
            return url_for("dancer_profile_detail_by_id", dancer_id=row.get("id"))

        if table_name == "battle_records":
            return url_for("battle_record_detail_phase2", battle_id=row.get("id"))

        if table_name == "calendar_item_metadata" and row.get("submission_id"):
            return url_for("event_detail", event_id=row.get("submission_id"))

        if table_name == "community_perspectives":
            return url_for("community_perspective_detail_phase2g", perspective_id=row.get("id"))

        if table_name in {"music_projects", "media_items"}:
            if row.get("id") and table_name == "media_items":
                return url_for("music_release_detail", item_id=row.get("id"))
            return url_for("litefeet_music")
    except Exception:
        pass

    return ""


def phase3a_record_snippet(table_name, row):
    priority_fields = [
        "bio",
        "details_json",
        "perspective_text",
        "description",
        "event_details",
        "judges_text",
        "winner",
        "official_winner",
        "related_to",
        "team_affiliation",
        "borough",
        "venue_name",
        "calendar_type",
        "artist_name",
        "platform",
        "source_url",
        "url",
    ]

    parts = []

    for field in priority_fields:
        value = row.get(field)

        if not value:
            continue

        if field == "details_json":
            value = phase3b_parse_details_json(value)

        if value:
            parts.append(str(value))

    if not parts:
        for key, value in row.items():
            if key == "id" or value in (None, ""):
                continue
            parts.append(str(value))
            if len(parts) >= 4:
                break

    return phase3a_compact_text(" | ".join(parts), 420)


def phase3a_search_ledger(question, limit=10):
    ensure_phase2_ledger_tables()

    profile_helper = globals().get("ensure_phase3a_profile_columns")
    if callable(profile_helper):
        try:
            profile_helper()
        except Exception:
            pass

    phase2g_helper = globals().get("ensure_phase2g_community_perspective_columns")
    if callable(phase2g_helper):
        try:
            phase2g_helper()
        except Exception:
            pass

    tokens = phase3a_tokens(question)
    normalized_question = phase3b_normalized_text(question)

    if not tokens:
        return []

    search_tables = [
        "battle_records",
        "dancer_profiles",
        "submissions",
        "community_perspectives",
        "calendar_item_metadata",
        "music_projects",
        "media_items",
    ]

    scored = []

    for table_name in search_tables:
        for row in phase3a_fetch_recent_rows(table_name, limit=500):
            title = phase3a_record_title(table_name, row)
            snippet = phase3a_record_snippet(table_name, row)
            search_text = phase3b_row_search_text(table_name, row)

            normalized_title = phase3b_normalized_text(title)
            normalized_search_text = phase3b_normalized_text(search_text)

            score = 0

            if normalized_question and normalized_question in normalized_title:
                score += 40

            if normalized_question and normalized_question in normalized_search_text:
                score += 25

            matched_tokens = 0

            for token in tokens:
                if token in normalized_title:
                    score += 12
                    matched_tokens += 1
                elif token in normalized_search_text:
                    score += 4
                    matched_tokens += 1

            if matched_tokens == len(tokens):
                score += 18

            if matched_tokens >= max(1, len(tokens) - 1):
                score += 8

            if score <= 0:
                continue

            status = phase3a_record_status(table_name, row)
            score += phase3b_status_weight(status)
            score += phase3b_table_weight(table_name)

            source_url = phase3a_record_source_url(row)

            if source_url:
                score += 3

            scored.append(
                {
                    "score": score,
                    "table": table_name,
                    "id": row.get("id"),
                    "title": title,
                    "type_label": phase3a_record_type_label(table_name, row),
                    "status": status,
                    "snippet": snippet,
                    "url": phase3a_record_url(table_name, row),
                    "source_url": source_url,
                    "matched_tokens": matched_tokens,
                }
            )

    scored.sort(
        key=lambda item: (
            item["score"],
            phase3b_status_weight(item["status"]),
            item["matched_tokens"],
        ),
        reverse=True,
    )

    unique = []
    seen = set()

    for item in scored:
        key = (item["table"], item["id"])

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

        if len(unique) >= limit:
            break

    return unique


def phase3b_group_results(results):
    groups = {
        "Verified / Community Supported": [],
        "Debated / Needs Verification": [],
        "Other Matches": [],
    }

    for item in results:
        status = item.get("status", "")

        if status in {"Verified", "Community Supported"}:
            groups["Verified / Community Supported"].append(item)
        elif status in {"Debated", "Needs Verification", "Pending Review"}:
            groups["Debated / Needs Verification"].append(item)
        else:
            groups["Other Matches"].append(item)

    return groups


def phase3a_build_ask_answer(question, results):
    if not results:
        return (
            "I could not find a strong Ledger match for that yet.\n\n"
            "Ledger status: Unknown / Needs Verification\n\n"
            "What this means: the Ledger does not currently have enough structured records, source links, "
            "or community perspectives connected to answer this confidently.\n\n"
            "Best next step: submit a source, flyer, video, correction, or community perspective so this can become a reviewable Ledger record."
        )

    groups = phase3b_group_results(results)

    strong_count = len(groups["Verified / Community Supported"])
    review_count = len(groups["Debated / Needs Verification"])

    lines = [
        "Ledger Search Result",
        "",
        f"Question: {question}",
        "",
        f"Supported matches: {strong_count}",
        f"Needs review/context matches: {review_count}",
        "",
    ]

    for group_name, group_items in groups.items():
        if not group_items:
            continue

        lines.append(group_name)
        lines.append("-" * len(group_name))

        for index, item in enumerate(group_items, start=1):
            lines.append(f"{index}. {item['title']}")
            lines.append(f"   Type: {item['type_label']}")
            lines.append(f"   Status: {item['status']}")

            if item["snippet"]:
                lines.append(f"   Context: {item['snippet']}")

            if item["url"]:
                lines.append(f"   Ledger record: {item['url']}")

            if item["source_url"]:
                lines.append(f"   Source/proof: {item['source_url']}")

            lines.append("")

    lines.append("How to read this:")
    lines.append(
        "Verified and Community Supported records carry the most weight. "
        "Debated, Pending Review, and Needs Verification records are included as context, "
        "but should not be treated as final until reviewed."
    )

    return "\n".join(lines)


# --- Phase 3C Ask source cards ---
def phase3c_table_columns(conn, table_name):
    if "ledger_table_columns" in globals():
        return ledger_table_columns(conn, table_name)

    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
            """),
            {"table_name": table_name},
        ).fetchall()
        return {row[0] for row in rows}

    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def phase3c_add_column_if_missing(conn, table_name, column_name, column_sql):
    existing_columns = phase3c_table_columns(conn, table_name)

    if column_name in existing_columns:
        return

    if maintenance_uses_postgres():
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_sql}"))
    else:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def ensure_phase3c_ask_source_columns():
    ensure_phase2_ledger_tables()

    with engine.begin() as conn:
        phase3c_add_column_if_missing(conn, "ask_messages", "source_summary", "TEXT")


def phase3c_safe_json_loads(value, fallback=None):
    if fallback is None:
        fallback = []

    if not value:
        return fallback

    try:
        parsed = json.loads(value)
    except Exception:
        return fallback

    return parsed


def phase3c_status_class(status):
    status = str(status or "").lower()

    if "verified" in status:
        return "verified"

    if "community supported" in status:
        return "community-supported"

    if "debated" in status or "disputed" in status:
        return "debated"

    if "needs" in status or "pending" in status:
        return "needs-review"

    return "unknown"


def ask_source_cards_for_conversation(conversation_id):
    ensure_phase3c_ask_source_columns()

    rows = fetch_all(
        """
        SELECT *
        FROM ask_messages
        WHERE conversation_id = :conversation_id
        ORDER BY id DESC
        """,
        {"conversation_id": conversation_id},
    )

    source_cards = []

    for row in rows:
        row_dict = phase3a_row_to_dict(row) if "phase3a_row_to_dict" in globals() else dict(row._mapping)

        source_summary = row_dict.get("source_summary")
        parsed = phase3c_safe_json_loads(source_summary, [])

        if not isinstance(parsed, list):
            continue

        for item in parsed:
            if not isinstance(item, dict):
                continue

            source_cards.append(
                {
                    "title": item.get("title") or "Ledger record",
                    "type_label": item.get("type_label") or item.get("table") or "Ledger Record",
                    "status": item.get("status") or "Unknown",
                    "status_class": phase3c_status_class(item.get("status")),
                    "snippet": item.get("snippet") or "",
                    "url": item.get("url") or "",
                    "source_url": item.get("source_url") or "",
                    "score": item.get("score") or 0,
                }
            )

        if source_cards:
            break

    return source_cards


@app.context_processor
def inject_phase3c_ask_source_helpers():
    return {
        "ask_source_cards_for_conversation": ask_source_cards_for_conversation,
        "phase3c_status_class": phase3c_status_class,
    }


try:
    ensure_phase3c_ask_source_columns()
except Exception as exc:
    print(f"Phase 3C Ask source-card schema setup skipped: {exc}")


# --- Phase 3D Ask filter controls ---
def phase3d_allowed_scopes():
    return {
        "all": {
            "label": "All Ledger",
            "tables": [
                "battle_records",
                "dancer_profiles",
                "submissions",
                "community_perspectives",
                "calendar_item_metadata",
                "music_projects",
                "media_items",
            ],
        },
        "battles": {
            "label": "Battles",
            "tables": [
                "battle_records",
                "submissions",
                "community_perspectives",
                "media_items",
            ],
        },
        "profiles": {
            "label": "Profiles / People",
            "tables": [
                "dancer_profiles",
                "community_perspectives",
                "submissions",
                "media_items",
            ],
        },
        "calendar": {
            "label": "Calendar",
            "tables": [
                "calendar_item_metadata",
                "submissions",
                "community_perspectives",
            ],
        },
        "music": {
            "label": "Music",
            "tables": [
                "music_projects",
                "media_items",
                "submissions",
                "community_perspectives",
            ],
        },
        "community": {
            "label": "Community Context",
            "tables": [
                "community_perspectives",
                "submissions",
                "dancer_profiles",
                "battle_records",
            ],
        },
        "review": {
            "label": "Verification / Review",
            "tables": [
                "submissions",
                "community_perspectives",
                "battle_records",
                "calendar_item_metadata",
            ],
        },
    }


def phase3d_current_scope(default="all"):
    try:
        selected = request.form.get("ask_scope") or request.args.get("ask_scope") or default
    except Exception:
        selected = default

    selected = str(selected or default).strip().lower()

    if selected not in phase3d_allowed_scopes():
        selected = default

    return selected


def phase3d_scope_label(scope):
    scopes = phase3d_allowed_scopes()
    return scopes.get(scope, scopes["all"])["label"]


def phase3d_scope_tables(scope):
    scopes = phase3d_allowed_scopes()
    return scopes.get(scope, scopes["all"])["tables"]


@app.context_processor
def inject_phase3d_ask_filter_options():
    scopes = phase3d_allowed_scopes()

    return {
        "ask_scope_options": [
            {"value": key, "label": value["label"]}
            for key, value in scopes.items()
        ],
        "phase3d_current_scope": phase3d_current_scope,
        "phase3d_scope_label": phase3d_scope_label,
    }


def phase3a_search_ledger(question, limit=10):
    ensure_phase2_ledger_tables()

    profile_helper = globals().get("ensure_phase3a_profile_columns")
    if callable(profile_helper):
        try:
            profile_helper()
        except Exception:
            pass

    phase2g_helper = globals().get("ensure_phase2g_community_perspective_columns")
    if callable(phase2g_helper):
        try:
            phase2g_helper()
        except Exception:
            pass

    phase3c_helper = globals().get("ensure_phase3c_ask_source_columns")
    if callable(phase3c_helper):
        try:
            phase3c_helper()
        except Exception:
            pass

    tokens = phase3a_tokens(question)
    normalized_question = phase3b_normalized_text(question) if "phase3b_normalized_text" in globals() else " ".join(tokens)
    selected_scope = phase3d_current_scope()
    search_tables = phase3d_scope_tables(selected_scope)

    if not tokens:
        return []

    scored = []

    for table_name in search_tables:
        for row in phase3a_fetch_recent_rows(table_name, limit=500):
            title = phase3a_record_title(table_name, row)
            snippet = phase3a_record_snippet(table_name, row)

            if "phase3b_row_search_text" in globals():
                search_text = phase3b_row_search_text(table_name, row)
            else:
                search_text = " ".join(str(value or "") for value in row.values())

            normalized_title = phase3b_normalized_text(title) if "phase3b_normalized_text" in globals() else title.lower()
            normalized_search_text = phase3b_normalized_text(search_text) if "phase3b_normalized_text" in globals() else search_text.lower()

            score = 0

            if normalized_question and normalized_question in normalized_title:
                score += 40

            if normalized_question and normalized_question in normalized_search_text:
                score += 25

            matched_tokens = 0

            for token in tokens:
                if token in normalized_title:
                    score += 12
                    matched_tokens += 1
                elif token in normalized_search_text:
                    score += 4
                    matched_tokens += 1

            if matched_tokens == len(tokens):
                score += 18

            if matched_tokens >= max(1, len(tokens) - 1):
                score += 8

            if score <= 0:
                continue

            status = phase3a_record_status(table_name, row)

            if "phase3b_status_weight" in globals():
                score += phase3b_status_weight(status)

            if "phase3b_table_weight" in globals():
                score += phase3b_table_weight(table_name)

            source_url = phase3a_record_source_url(row)

            if source_url:
                score += 3

            scored.append(
                {
                    "score": score,
                    "scope": selected_scope,
                    "scope_label": phase3d_scope_label(selected_scope),
                    "table": table_name,
                    "id": row.get("id"),
                    "title": title,
                    "type_label": phase3a_record_type_label(table_name, row),
                    "status": status,
                    "snippet": snippet,
                    "url": phase3a_record_url(table_name, row),
                    "source_url": source_url,
                    "matched_tokens": matched_tokens,
                }
            )

    scored.sort(
        key=lambda item: (
            item["score"],
            phase3b_status_weight(item["status"]) if "phase3b_status_weight" in globals() else 0,
            item["matched_tokens"],
        ),
        reverse=True,
    )

    unique = []
    seen = set()

    for item in scored:
        key = (item["table"], item["id"])

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

        if len(unique) >= limit:
            break

    return unique


def phase3a_build_ask_answer(question, results):
    selected_scope = phase3d_current_scope()
    scope_label = phase3d_scope_label(selected_scope)

    if not results:
        return (
            "I could not find a strong Ledger match for that yet.\n\n"
            f"Search scope: {scope_label}\n"
            "Ledger status: Unknown / Needs Verification\n\n"
            "What this means: the Ledger does not currently have enough structured records, source links, "
            "or community perspectives connected to answer this confidently.\n\n"
            "Best next step: submit a source, flyer, video, correction, or community perspective so this can become a reviewable Ledger record."
        )

    if "phase3b_group_results" in globals():
        groups = phase3b_group_results(results)
    else:
        groups = {
            "Ledger Matches": results,
        }

    strong_count = len(groups.get("Verified / Community Supported", []))
    review_count = len(groups.get("Debated / Needs Verification", []))

    lines = [
        "Ledger Search Result",
        "",
        f"Question: {question}",
        f"Search scope: {scope_label}",
        "",
        f"Supported matches: {strong_count}",
        f"Needs review/context matches: {review_count}",
        "",
    ]

    for group_name, group_items in groups.items():
        if not group_items:
            continue

        lines.append(group_name)
        lines.append("-" * len(group_name))

        for index, item in enumerate(group_items, start=1):
            lines.append(f"{index}. {item['title']}")
            lines.append(f"   Type: {item['type_label']}")
            lines.append(f"   Status: {item['status']}")

            if item.get("scope_label"):
                lines.append(f"   Scope: {item['scope_label']}")

            if item["snippet"]:
                lines.append(f"   Context: {item['snippet']}")

            if item["url"]:
                lines.append(f"   Ledger record: {item['url']}")

            if item["source_url"]:
                lines.append(f"   Source/proof: {item['source_url']}")

            lines.append("")

    lines.append("How to read this:")
    lines.append(
        "Verified and Community Supported records carry the most weight. "
        "Debated, Pending Review, and Needs Verification records are included as context, "
        "but should not be treated as final until reviewed."
    )

    return "\n".join(lines)


# --- Phase 3E Ask feedback ---
def ensure_phase3e_ask_feedback_table():
    with engine.begin() as conn:
        if maintenance_uses_postgres():
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS ask_feedback (
                    id SERIAL PRIMARY KEY,
                    conversation_id INTEGER,
                    message_id INTEGER,
                    user_id INTEGER,
                    visitor_key TEXT,
                    rating_label TEXT,
                    feedback_text TEXT,
                    created_at TEXT
                )
                """)
            )
        else:
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS ask_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER,
                    message_id INTEGER,
                    user_id INTEGER,
                    visitor_key TEXT,
                    rating_label TEXT,
                    feedback_text TEXT,
                    created_at TEXT
                )
                """)
            )


def phase3e_insert_feedback(values):
    ensure_phase3e_ask_feedback_table()

    columns = list(values.keys())
    columns_sql = ", ".join(columns)
    values_sql = ", ".join(f":{column}" for column in columns)

    with engine.begin() as conn:
        if maintenance_uses_postgres():
            result = conn.execute(
                text(f"INSERT INTO ask_feedback ({columns_sql}) VALUES ({values_sql}) RETURNING id"),
                values,
            )
            return result.scalar()

        result = conn.execute(
            text(f"INSERT INTO ask_feedback ({columns_sql}) VALUES ({values_sql})"),
            values,
        )
        return result.lastrowid


def phase3e_visitor_key():
    key = ""

    try:
        key = ask_beta_user_key()
    except Exception:
        key = session.get("visitor_key", "")

    if isinstance(key, (tuple, list)):
        key = next((str(item) for item in key if item), "")

    return str(key or "")


def fetch_ask_feedback_for_conversation(conversation_id):
    ensure_phase3e_ask_feedback_table()

    return fetch_all(
        """
        SELECT *
        FROM ask_feedback
        WHERE conversation_id = :conversation_id
        ORDER BY created_at DESC, id DESC
        """,
        {"conversation_id": conversation_id},
    )


def fetch_latest_assistant_message_id(conversation_id):
    ensure_phase2_ledger_tables()

    columns = set()

    try:
        with engine.connect() as conn:
            if "ledger_table_columns" in globals():
                columns = ledger_table_columns(conn, "ask_messages")
            elif maintenance_uses_postgres():
                rows = conn.execute(
                    text("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = 'ask_messages'
                    """)
                ).fetchall()
                columns = {row[0] for row in rows}
            else:
                rows = conn.execute(text("PRAGMA table_info(ask_messages)")).fetchall()
                columns = {row[1] for row in rows}
    except Exception:
        columns = set()

    role_clauses = []

    for column_name in ["sender", "role", "message_role", "sender_type"]:
        if column_name in columns:
            role_clauses.append(f"{column_name} = 'assistant'")

    if role_clauses:
        role_sql = " OR ".join(role_clauses)
        query = f"""
            SELECT id
            FROM ask_messages
            WHERE conversation_id = :conversation_id
              AND ({role_sql})
            ORDER BY id DESC
            LIMIT 1
        """
    else:
        query = """
            SELECT id
            FROM ask_messages
            WHERE conversation_id = :conversation_id
            ORDER BY id DESC
            LIMIT 1
        """

    rows = fetch_all(query, {"conversation_id": conversation_id})
    return rows[0]["id"] if rows else None


@app.context_processor
def inject_phase3e_ask_feedback_helpers():
    return {
        "ask_feedback_for_conversation": fetch_ask_feedback_for_conversation,
        "latest_assistant_message_id": fetch_latest_assistant_message_id,
    }


@app.route("/ask/conversations/<int:conversation_id>/feedback", methods=["POST"])
def submit_ask_feedback_phase3e(conversation_id):
    ensure_phase3e_ask_feedback_table()

    conversation = None

    if "fetch_ask_conversation" in globals():
        try:
            conversation = fetch_ask_conversation(conversation_id)
        except Exception:
            conversation = None

    if not conversation:
        rows = fetch_all(
            """
            SELECT *
            FROM ask_conversations
            WHERE id = :conversation_id
            LIMIT 1
            """,
            {"conversation_id": conversation_id},
        )
        conversation = rows[0] if rows else None

    if not conversation:
        return redirect(url_for("ask_archive"))

    user = current_user()
    is_admin = bool(session.get("admin_logged_in"))

    can_view = is_admin

    if "can_view_ask_conversation" in globals():
        try:
            can_view = can_view or bool(can_view_ask_conversation(conversation))
        except Exception:
            can_view = can_view or bool(user)
    else:
        can_view = can_view or bool(user)

    if not can_view:
        return redirect(url_for("account_login", next=url_for("ask_conversation_detail", conversation_id=conversation_id)))

    rating_label = request.form.get("rating_label", "").strip()
    feedback_text = request.form.get("feedback_text", "").strip()
    message_id = request.form.get("message_id", "").strip()

    allowed = {
        "Helpful",
        "Wrong",
        "Missing Context",
        "Needs Review",
    }

    if rating_label not in allowed:
        rating_label = "Needs Review"

    try:
        message_id_value = int(message_id) if message_id else None
    except Exception:
        message_id_value = None

    if not message_id_value:
        message_id_value = fetch_latest_assistant_message_id(conversation_id)

    phase3e_insert_feedback(
        {
            "conversation_id": conversation_id,
            "message_id": message_id_value,
            "user_id": user["id"] if user else None,
            "visitor_key": phase3e_visitor_key(),
            "rating_label": rating_label,
            "feedback_text": feedback_text,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    )

    return redirect(url_for("ask_conversation_detail", conversation_id=conversation_id))


try:
    ensure_phase3e_ask_feedback_table()
except Exception as exc:
    print(f"Phase 3E Ask feedback setup skipped: {exc}")


# --- Phase 3F admin Ask feedback review ---
def phase3f_table_columns(conn, table_name):
    if "ledger_table_columns" in globals():
        return ledger_table_columns(conn, table_name)

    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
            """),
            {"table_name": table_name},
        ).fetchall()
        return {row[0] for row in rows}

    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def phase3f_add_column_if_missing(conn, table_name, column_name, column_sql):
    existing_columns = phase3f_table_columns(conn, table_name)

    if column_name in existing_columns:
        return

    if maintenance_uses_postgres():
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_sql}"))
    else:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def ensure_phase3f_ask_feedback_admin_columns():
    ensure_phase3e_ask_feedback_table()

    with engine.begin() as conn:
        phase3f_add_column_if_missing(conn, "ask_feedback", "feedback_status", "TEXT")
        phase3f_add_column_if_missing(conn, "ask_feedback", "admin_note", "TEXT")
        phase3f_add_column_if_missing(conn, "ask_feedback", "updated_at", "TEXT")


def phase3f_admin_required():
    if not current_user_is_admin():
        return redirect(url_for("admin_login"))
    return None


@app.route("/admin/ask-feedback")
def admin_ask_feedback_phase3f():
    gate = phase3f_admin_required()
    if gate:
        return gate

    ensure_phase3f_ask_feedback_admin_columns()

    feedback_rows = fetch_all(
        """
        SELECT ask_feedback.*,
               ask_conversations.title AS conversation_title,
               ask_conversations.status AS conversation_status,
               ask_conversations.created_at AS conversation_created_at,
               archive_users.display_name AS user_display_name,
               archive_users.email AS user_email
        FROM ask_feedback
        LEFT JOIN ask_conversations
          ON ask_feedback.conversation_id = ask_conversations.id
        LEFT JOIN archive_users
          ON ask_feedback.user_id = archive_users.id
        ORDER BY
            COALESCE(ask_feedback.updated_at, ask_feedback.created_at, '') DESC,
            ask_feedback.id DESC
        LIMIT 200
        """,
        {},
    )

    feedback_counts = fetch_all(
        """
        SELECT
            COALESCE(feedback_status, 'New') AS feedback_status,
            COUNT(*) AS count
        FROM ask_feedback
        GROUP BY COALESCE(feedback_status, 'New')
        ORDER BY count DESC
        """,
        {},
    )

    rating_counts = fetch_all(
        """
        SELECT
            COALESCE(rating_label, 'Unknown') AS rating_label,
            COUNT(*) AS count
        FROM ask_feedback
        GROUP BY COALESCE(rating_label, 'Unknown')
        ORDER BY count DESC
        """,
        {},
    )

    return render_template(
        "admin_ask_feedback.html",
        feedback_rows=feedback_rows,
        feedback_counts=feedback_counts,
        rating_counts=rating_counts,
    )


@app.route("/admin/ask-feedback/<int:feedback_id>/status", methods=["POST"])
def admin_ask_feedback_status_phase3f(feedback_id):
    gate = phase3f_admin_required()
    if gate:
        return gate

    ensure_phase3f_ask_feedback_admin_columns()

    feedback_status = request.form.get("feedback_status", "").strip()
    admin_note = request.form.get("admin_note", "").strip()

    allowed = {
        "New",
        "Reviewed",
        "Needs Fix",
        "Needs Context",
        "Converted to Review",
        "Archived",
        "Dismissed",
    }

    if feedback_status not in allowed:
        feedback_status = "New"

    execute_query(
        """
        UPDATE ask_feedback
        SET feedback_status = :feedback_status,
            admin_note = :admin_note,
            updated_at = :updated_at
        WHERE id = :feedback_id
        """,
        {
            "feedback_status": feedback_status,
            "admin_note": admin_note,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "feedback_id": feedback_id,
        },
    )

    return redirect(url_for("admin_ask_feedback_phase3f"))


try:
    ensure_phase3f_ask_feedback_admin_columns()
except Exception as exc:
    print(f"Phase 3F Ask feedback admin setup skipped: {exc}")


# --- Phase 3G + 4A + 4B batch ---
def phase3g4_admin_required():
    if not current_user_is_admin():
        return redirect(url_for("admin_login"))
    return None


def phase3g4_table_exists(conn, table_name):
    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                LIMIT 1
            """),
            {"table_name": table_name},
        ).fetchall()
        return bool(rows)

    rows = conn.execute(
        text("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name = :table_name
            LIMIT 1
        """),
        {"table_name": table_name},
    ).fetchall()
    return bool(rows)


def phase3g4_table_columns(conn, table_name):
    if "ledger_table_columns" in globals():
        return ledger_table_columns(conn, table_name)

    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
            """),
            {"table_name": table_name},
        ).fetchall()
        return {row[0] for row in rows}

    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def phase3g4_add_column_if_missing(conn, table_name, column_name, column_sql):
    if not phase3g4_table_exists(conn, table_name):
        return

    columns = phase3g4_table_columns(conn, table_name)

    if column_name in columns:
        return

    if maintenance_uses_postgres():
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_sql}"))
    else:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def ensure_phase4a_profile_claim_link_columns():
    ensure_phase2_ledger_tables()

    with engine.begin() as conn:
        if phase3g4_table_exists(conn, "archive_users"):
            phase3g4_add_column_if_missing(conn, "archive_users", "linked_profile_type", "TEXT")
            phase3g4_add_column_if_missing(conn, "archive_users", "linked_profile_id", "INTEGER")
            phase3g4_add_column_if_missing(conn, "archive_users", "profile_claim_status", "TEXT")
            phase3g4_add_column_if_missing(conn, "archive_users", "profile_claimed_at", "TEXT")
            phase3g4_add_column_if_missing(conn, "archive_users", "profile_edit_status", "TEXT")

        if phase3g4_table_exists(conn, "dancer_profiles"):
            phase3g4_add_column_if_missing(conn, "dancer_profiles", "claimed_by_user_id", "INTEGER")
            phase3g4_add_column_if_missing(conn, "dancer_profiles", "claimed_at", "TEXT")
            phase3g4_add_column_if_missing(conn, "dancer_profiles", "edit_access_status", "TEXT")


def phase3g4_insert_dynamic(table_name, values):
    with engine.begin() as conn:
        columns = phase3g4_table_columns(conn, table_name)
        clean_values = {key: value for key, value in values.items() if key in columns}

        if not clean_values:
            return None

        columns_sql = ", ".join(clean_values.keys())
        values_sql = ", ".join(f":{key}" for key in clean_values.keys())

        if maintenance_uses_postgres():
            result = conn.execute(
                text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql}) RETURNING id"),
                clean_values,
            )
            return result.scalar()

        result = conn.execute(
            text(f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql})"),
            clean_values,
        )
        return result.lastrowid


def phase3g4_update_dynamic(table_name, values, where_clause, where_params):
    with engine.begin() as conn:
        columns = phase3g4_table_columns(conn, table_name)
        clean_values = {key: value for key, value in values.items() if key in columns}

        if not clean_values:
            return

        set_sql = ", ".join(f"{key} = :{key}" for key in clean_values.keys())
        params = dict(clean_values)
        params.update(where_params)

        conn.execute(
            text(f"UPDATE {table_name} SET {set_sql} WHERE {where_clause}"),
            params,
        )


@app.route("/admin/ask-feedback/<int:feedback_id>/convert-to-review", methods=["POST"])
def admin_ask_feedback_convert_phase3g(feedback_id):
    gate = phase3g4_admin_required()
    if gate:
        return gate

    ensure_phase3f_ask_feedback_admin_columns()
    ensure_phase2g_community_perspective_columns()

    rows = fetch_all(
        """
        SELECT ask_feedback.*,
               ask_conversations.title AS conversation_title,
               ask_conversations.status AS conversation_status
        FROM ask_feedback
        LEFT JOIN ask_conversations
          ON ask_feedback.conversation_id = ask_conversations.id
        WHERE ask_feedback.id = :feedback_id
        LIMIT 1
        """,
        {"feedback_id": feedback_id},
    )

    if not rows:
        return redirect(url_for("admin_ask_feedback_phase3f"))

    feedback = rows[0]
    now_value = datetime.now().isoformat(timespec="seconds")

    review_label = request.form.get("review_label", "").strip()
    if not review_label:
        review_label = f"Ask Feedback: {feedback['rating_label'] or 'Needs Review'}"

    perspective_text = "\n".join(
        part for part in [
            f"Ask feedback rating: {feedback['rating_label'] or 'Needs Review'}",
            f"Conversation: {feedback['conversation_title'] or 'Untitled Ask conversation'}",
            f"Feedback: {feedback['feedback_text'] or 'No extra note provided.'}",
            f"Admin note: {request.form.get('admin_note', '').strip()}",
        ]
        if part
    )

    perspective_id = phase3g4_insert_dynamic(
        "community_perspectives",
        {
            "related_type": "ask_feedback",
            "related_id": feedback_id,
            "submission_id": None,
            "user_id": feedback["user_id"],
            "perspective_text": perspective_text,
            "source_url": "",
            "perspective_status": "Pending Review",
            "review_label": review_label,
            "submitter_name": "Ask Feedback",
            "submitter_contact": "",
            "anonymous_input": 0,
            "created_at": now_value,
            "updated_at": now_value,
        },
    )

    phase3g4_update_dynamic(
        "ask_feedback",
        {
            "feedback_status": "Converted to Review",
            "admin_note": f"Converted to community perspective #{perspective_id}" if perspective_id else "Converted to community perspective",
            "updated_at": now_value,
        },
        "id = :feedback_id",
        {"feedback_id": feedback_id},
    )

    return redirect(url_for("admin_ask_feedback_phase3f"))


@app.route("/admin/phase4/profile-claims/<int:claim_id>/approve-link", methods=["POST"])
def admin_phase4_approve_profile_claim_link(claim_id):
    gate = phase3g4_admin_required()
    if gate:
        return gate

    ensure_phase4a_profile_claim_link_columns()

    rows = fetch_all(
        """
        SELECT *
        FROM profile_claims
        WHERE id = :claim_id
        LIMIT 1
        """,
        {"claim_id": claim_id},
    )

    if not rows:
        return redirect(url_for("admin_phase2_moderation"))

    claim = rows[0]
    now_value = datetime.now().isoformat(timespec="seconds")

    user_id = claim["user_id"]
    profile_id = claim["profile_id"]
    profile_type = claim["profile_type"] or "dancer"

    if not user_id or not profile_id:
        return redirect(url_for("admin_phase2_moderation"))

    phase3g4_update_dynamic(
        "profile_claims",
        {
            "claim_status": "Approved",
            "reviewed_at": now_value,
            "updated_at": now_value,
        },
        "id = :claim_id",
        {"claim_id": claim_id},
    )

    if profile_type == "dancer":
        phase3g4_update_dynamic(
            "dancer_profiles",
            {
                "user_id": user_id,
                "claimed_by_user_id": user_id,
                "claimed_at": now_value,
                "edit_access_status": "Approved",
            },
            "id = :profile_id",
            {"profile_id": profile_id},
        )

    phase3g4_update_dynamic(
        "archive_users",
        {
            "linked_profile_type": profile_type,
            "linked_profile_id": profile_id,
            "profile_claim_status": "Approved",
            "profile_claimed_at": now_value,
            "profile_edit_status": "Approved",
        },
        "id = :user_id",
        {"user_id": user_id},
    )

    return redirect(url_for("admin_phase2_moderation"))


@app.route("/producers")
def producers_legacy_alias_phase4b():
    return redirect(url_for("producers"))


@app.route("/teams")
def teams_legacy_alias_phase4b():
    return redirect(url_for("teams"))


try:
    ensure_phase4a_profile_claim_link_columns()
except Exception as exc:
    print(f"Phase 4A profile claim link setup skipped: {exc}")


# --- Phase 4C + 4D + 4E profile owner batch ---
def phase4c_admin_required():
    if not current_user_is_admin():
        return redirect(url_for("admin_login"))
    return None


def phase4c_table_exists(conn, table_name):
    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                LIMIT 1
            """),
            {"table_name": table_name},
        ).fetchall()
        return bool(rows)

    rows = conn.execute(
        text("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = :table_name
            LIMIT 1
        """),
        {"table_name": table_name},
    ).fetchall()
    return bool(rows)


def phase4c_table_columns(conn, table_name):
    if "ledger_table_columns" in globals():
        return ledger_table_columns(conn, table_name)

    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
            """),
            {"table_name": table_name},
        ).fetchall()
        return {row[0] for row in rows}

    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def phase4c_add_column_if_missing(conn, table_name, column_name, column_sql):
    if not phase4c_table_exists(conn, table_name):
        return

    columns = phase4c_table_columns(conn, table_name)

    if column_name in columns:
        return

    if maintenance_uses_postgres():
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_sql}"))
    else:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def ensure_phase4c_profile_owner_tables():
    ensure_phase4a_profile_claim_link_columns()

    phase3a_profile_helper = globals().get("ensure_phase3a_profile_columns")
    if callable(phase3a_profile_helper):
        try:
            phase3a_profile_helper()
        except Exception:
            pass

    with engine.begin() as conn:
        if maintenance_uses_postgres():
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS profile_edit_logs (
                    id SERIAL PRIMARY KEY,
                    profile_type TEXT,
                    profile_id INTEGER,
                    user_id INTEGER,
                    edit_action TEXT,
                    old_values_json TEXT,
                    new_values_json TEXT,
                    edit_status TEXT,
                    admin_note TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """)
            )
        else:
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS profile_edit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_type TEXT,
                    profile_id INTEGER,
                    user_id INTEGER,
                    edit_action TEXT,
                    old_values_json TEXT,
                    new_values_json TEXT,
                    edit_status TEXT,
                    admin_note TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """)
            )

        phase4c_add_column_if_missing(conn, "profile_edit_logs", "profile_type", "TEXT")
        phase4c_add_column_if_missing(conn, "profile_edit_logs", "profile_id", "INTEGER")
        phase4c_add_column_if_missing(conn, "profile_edit_logs", "user_id", "INTEGER")
        phase4c_add_column_if_missing(conn, "profile_edit_logs", "edit_action", "TEXT")
        phase4c_add_column_if_missing(conn, "profile_edit_logs", "old_values_json", "TEXT")
        phase4c_add_column_if_missing(conn, "profile_edit_logs", "new_values_json", "TEXT")
        phase4c_add_column_if_missing(conn, "profile_edit_logs", "edit_status", "TEXT")
        phase4c_add_column_if_missing(conn, "profile_edit_logs", "admin_note", "TEXT")
        phase4c_add_column_if_missing(conn, "profile_edit_logs", "created_at", "TEXT")
        phase4c_add_column_if_missing(conn, "profile_edit_logs", "updated_at", "TEXT")


def phase4c_row_to_dict(row):
    try:
        return dict(row._mapping)
    except Exception:
        return dict(row)


def phase4c_allowed_profile_fields():
    return {
        "dance_name": "Dance name",
        "real_name": "Real name",
        "team_affiliation": "Team affiliation",
        "borough_scene": "Borough / scene",
        "bio": "Bio",
        "source_url": "Source / reference link",
        "role_tags": "Role tags",
        "aliases": "Aliases",
        "era": "Era",
        "style_notes": "Style notes",
        "signature_moves": "Signature moves",
        "recent_battle": "Recent battle",
        "battle_history": "Battle history",
        "legacy_notes": "Legacy notes",
    }


def phase4c_fetch_profile_by_id(profile_id):
    rows = fetch_all(
        """
        SELECT *
        FROM dancer_profiles
        WHERE id = :profile_id
        LIMIT 1
        """,
        {"profile_id": profile_id},
    )
    return rows[0] if rows else None


def phase4c_current_user_linked_profile():
    ensure_phase4c_profile_owner_tables()

    user = current_user()

    if not user:
        return None

    user_id = user["id"]

    linked_profile_id = None
    linked_profile_type = "dancer"

    try:
        linked_profile_id = user["linked_profile_id"]
    except Exception:
        linked_profile_id = None

    try:
        linked_profile_type = user["linked_profile_type"] or "dancer"
    except Exception:
        linked_profile_type = "dancer"

    if linked_profile_id and linked_profile_type == "dancer":
        profile = phase4c_fetch_profile_by_id(linked_profile_id)
        if profile:
            return profile

    rows = fetch_all(
        """
        SELECT *
        FROM dancer_profiles
        WHERE user_id = :user_id
           OR claimed_by_user_id = :user_id
        ORDER BY id ASC
        LIMIT 1
        """,
        {"user_id": user_id},
    )

    return rows[0] if rows else None


def phase4c_user_can_edit_profile(profile_id):
    if current_user_is_admin():
        return True

    user = current_user()

    if not user:
        return False

    profile = phase4c_fetch_profile_by_id(profile_id)

    if not profile:
        return False

    user_id = user["id"]

    approved_user_link = False

    try:
        approved_user_link = (
            int(user["linked_profile_id"] or 0) == int(profile_id)
            and str(user["profile_edit_status"] or "").lower() == "approved"
        )
    except Exception:
        approved_user_link = False

    approved_profile_link = False

    try:
        approved_profile_link = (
            int(profile["claimed_by_user_id"] or profile["user_id"] or 0) == int(user_id)
            and str(profile["edit_access_status"] or "").lower() == "approved"
        )
    except Exception:
        approved_profile_link = False

    direct_owner_match = False

    try:
        direct_owner_match = int(profile["user_id"] or 0) == int(user_id)
    except Exception:
        direct_owner_match = False

    return approved_user_link or approved_profile_link or direct_owner_match


def phase4c_insert_profile_edit_log(profile_id, user_id, old_values, new_values, edit_action="owner_update"):
    ensure_phase4c_profile_owner_tables()

    now_value = datetime.now().isoformat(timespec="seconds")

    with engine.begin() as conn:
        columns = phase4c_table_columns(conn, "profile_edit_logs")
        values = {
            "profile_type": "dancer",
            "profile_id": profile_id,
            "user_id": user_id,
            "edit_action": edit_action,
            "old_values_json": json.dumps(old_values, ensure_ascii=False),
            "new_values_json": json.dumps(new_values, ensure_ascii=False),
            "edit_status": "Logged",
            "admin_note": "",
            "created_at": now_value,
            "updated_at": now_value,
        }

        clean_values = {key: value for key, value in values.items() if key in columns}

        columns_sql = ", ".join(clean_values.keys())
        values_sql = ", ".join(f":{key}" for key in clean_values.keys())

        if maintenance_uses_postgres():
            conn.execute(
                text(f"INSERT INTO profile_edit_logs ({columns_sql}) VALUES ({values_sql})"),
                clean_values,
            )
        else:
            conn.execute(
                text(f"INSERT INTO profile_edit_logs ({columns_sql}) VALUES ({values_sql})"),
                clean_values,
            )


def phase4c_update_profile(profile_id, values):
    ensure_phase4c_profile_owner_tables()

    with engine.begin() as conn:
        columns = phase4c_table_columns(conn, "dancer_profiles")
        allowed = phase4c_allowed_profile_fields()
        clean_values = {
            key: value
            for key, value in values.items()
            if key in allowed and key in columns
        }

        if not clean_values:
            return

        clean_values["profile_id"] = profile_id

        set_sql = ", ".join(f"{key} = :{key}" for key in clean_values.keys() if key != "profile_id")
        conn.execute(
            text(f"UPDATE dancer_profiles SET {set_sql} WHERE id = :profile_id"),
            clean_values,
        )


@app.context_processor
def inject_phase4c_profile_owner_helpers():
    return {
        "phase4c_current_user_linked_profile": phase4c_current_user_linked_profile,
        "phase4c_user_can_edit_profile": phase4c_user_can_edit_profile,
        "phase4c_allowed_profile_fields": phase4c_allowed_profile_fields,
    }


@app.route("/account/profile-editor", methods=["GET", "POST"])
def account_profile_editor_phase4c():
    ensure_phase4c_profile_owner_tables()

    user = current_user()

    if not user:
        return redirect(url_for("account_login", next=url_for("account_profile_editor_phase4c")))

    profile = phase4c_current_user_linked_profile()

    if not profile:
        return render_template(
            "profile_owner_editor.html",
            profile=None,
            allowed_fields=phase4c_allowed_profile_fields(),
            saved=False,
            denied=False,
        )

    if not phase4c_user_can_edit_profile(profile["id"]):
        return render_template(
            "profile_owner_editor.html",
            profile=profile,
            allowed_fields=phase4c_allowed_profile_fields(),
            saved=False,
            denied=True,
        )

    saved = False

    if request.method == "POST":
        old_values = {}
        new_values = {}

        for field_name in phase4c_allowed_profile_fields():
            old_values[field_name] = profile[field_name] if field_name in profile.keys() else ""
            new_values[field_name] = request.form.get(field_name, "").strip()

        phase4c_update_profile(profile["id"], new_values)
        phase4c_insert_profile_edit_log(profile["id"], user["id"], old_values, new_values)

        return redirect(url_for("account_profile_editor_phase4c", saved="1"))

    saved = request.args.get("saved") == "1"
    profile = phase4c_current_user_linked_profile()

    return render_template(
        "profile_owner_editor.html",
        profile=profile,
        allowed_fields=phase4c_allowed_profile_fields(),
        saved=saved,
        denied=False,
    )


@app.route("/admin/profile-corrections")
def admin_profile_corrections_phase4e():
    gate = phase4c_admin_required()
    if gate:
        return gate

    ensure_phase4c_profile_owner_tables()

    edit_logs = fetch_all(
        """
        SELECT profile_edit_logs.*,
               dancer_profiles.dance_name,
               dancer_profiles.real_name,
               archive_users.display_name,
               archive_users.email
        FROM profile_edit_logs
        LEFT JOIN dancer_profiles
          ON profile_edit_logs.profile_id = dancer_profiles.id
        LEFT JOIN archive_users
          ON profile_edit_logs.user_id = archive_users.id
        ORDER BY profile_edit_logs.id DESC
        LIMIT 150
        """,
        {},
    )

    profile_claims = []
    dancer_suggestions = []
    dancer_flowers = []

    try:
        profile_claims = fetch_all(
            """
            SELECT *
            FROM profile_claims
            ORDER BY id DESC
            LIMIT 50
            """,
            {},
        )
    except Exception:
        profile_claims = []

    try:
        dancer_suggestions = fetch_all(
            """
            SELECT dancer_suggestions.*,
                   dancer_profiles.dance_name
            FROM dancer_suggestions
            LEFT JOIN dancer_profiles
              ON dancer_suggestions.dancer_id = dancer_profiles.id
            ORDER BY dancer_suggestions.id DESC
            LIMIT 50
            """,
            {},
        )
    except Exception:
        dancer_suggestions = []

    try:
        dancer_flowers = fetch_all(
            """
            SELECT dancer_flowers.*,
                   dancer_profiles.dance_name
            FROM dancer_flowers
            LEFT JOIN dancer_profiles
              ON dancer_flowers.dancer_id = dancer_profiles.id
            ORDER BY dancer_flowers.id DESC
            LIMIT 50
            """,
            {},
        )
    except Exception:
        dancer_flowers = []

    return render_template(
        "admin_profile_corrections.html",
        edit_logs=edit_logs,
        profile_claims=profile_claims,
        dancer_suggestions=dancer_suggestions,
        dancer_flowers=dancer_flowers,
    )


@app.route("/admin/profile-edit-logs/<int:log_id>/status", methods=["POST"])
def admin_profile_edit_log_status_phase4e(log_id):
    gate = phase4c_admin_required()
    if gate:
        return gate

    ensure_phase4c_profile_owner_tables()

    edit_status = request.form.get("edit_status", "").strip()
    admin_note = request.form.get("admin_note", "").strip()

    allowed = {
        "Logged",
        "Reviewed",
        "Needs Follow-up",
        "Approved",
        "Archived",
        "Dismissed",
    }

    if edit_status not in allowed:
        edit_status = "Logged"

    execute_query(
        """
        UPDATE profile_edit_logs
        SET edit_status = :edit_status,
            admin_note = :admin_note,
            updated_at = :updated_at
        WHERE id = :log_id
        """,
        {
            "edit_status": edit_status,
            "admin_note": admin_note,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "log_id": log_id,
        },
    )

    return redirect(url_for("admin_profile_corrections_phase4e"))


try:
    ensure_phase4c_profile_owner_tables()
except Exception as exc:
    print(f"Phase 4C profile owner setup skipped: {exc}")


# --- Phase 5A + 5B + 5C calendar batch ---
def phase5_admin_required():
    if not current_user_is_admin():
        return redirect(url_for("admin_login"))
    return None


def phase5_table_exists(conn, table_name):
    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                LIMIT 1
            """),
            {"table_name": table_name},
        ).fetchall()
        return bool(rows)

    rows = conn.execute(
        text("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = :table_name
            LIMIT 1
        """),
        {"table_name": table_name},
    ).fetchall()
    return bool(rows)


def phase5_table_columns(conn, table_name):
    if "ledger_table_columns" in globals():
        return ledger_table_columns(conn, table_name)

    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
            """),
            {"table_name": table_name},
        ).fetchall()
        return {row[0] for row in rows}

    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def phase5_add_column_if_missing(conn, table_name, column_name, column_sql):
    if not phase5_table_exists(conn, table_name):
        return

    columns = phase5_table_columns(conn, table_name)

    if column_name in columns:
        return

    if maintenance_uses_postgres():
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_sql}"))
    else:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def ensure_phase5_calendar_tables():
    ensure_phase2_ledger_tables()

    with engine.begin() as conn:
        if maintenance_uses_postgres():
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS calendar_item_metadata (
                    id SERIAL PRIMARY KEY,
                    submission_id INTEGER,
                    calendar_type TEXT,
                    item_type TEXT,
                    visibility_status TEXT,
                    review_status TEXT,
                    start_datetime TEXT,
                    end_datetime TEXT,
                    venue_name TEXT,
                    borough TEXT,
                    ticket_url TEXT,
                    rsvp_url TEXT,
                    flyer_url TEXT,
                    recurrence_rule TEXT,
                    recurrence_label TEXT,
                    admin_note TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """)
            )
        else:
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS calendar_item_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submission_id INTEGER,
                    calendar_type TEXT,
                    item_type TEXT,
                    visibility_status TEXT,
                    review_status TEXT,
                    start_datetime TEXT,
                    end_datetime TEXT,
                    venue_name TEXT,
                    borough TEXT,
                    ticket_url TEXT,
                    rsvp_url TEXT,
                    flyer_url TEXT,
                    recurrence_rule TEXT,
                    recurrence_label TEXT,
                    admin_note TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """)
            )

        for column_name, column_sql in [
            ("submission_id", "INTEGER"),
            ("calendar_type", "TEXT"),
            ("item_type", "TEXT"),
            ("visibility_status", "TEXT"),
            ("review_status", "TEXT"),
            ("start_datetime", "TEXT"),
            ("end_datetime", "TEXT"),
            ("venue_name", "TEXT"),
            ("borough", "TEXT"),
            ("ticket_url", "TEXT"),
            ("rsvp_url", "TEXT"),
            ("flyer_url", "TEXT"),
            ("recurrence_rule", "TEXT"),
            ("recurrence_label", "TEXT"),
            ("admin_note", "TEXT"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT"),
        ]:
            phase5_add_column_if_missing(conn, "calendar_item_metadata", column_name, column_sql)


def phase5_row_to_dict(row):
    try:
        return dict(row._mapping)
    except Exception:
        return dict(row)


def phase5_get_event_detail(event, label):
    helper = globals().get("get_detail_value")

    if callable(helper):
        try:
            return helper(event, label)
        except Exception:
            try:
                return helper(event.get("details_json"), label)
            except Exception:
                pass

    return ""


def phase5_calendar_metadata_for_event(event_id):
    ensure_phase5_calendar_tables()

    rows = fetch_all(
        """
        SELECT *
        FROM calendar_item_metadata
        WHERE submission_id = :event_id
        ORDER BY id DESC
        LIMIT 1
        """,
        {"event_id": event_id},
    )

    return rows[0] if rows else None


def phase5_calendar_type_for_event(event):
    event_id = event["id"] if "id" in event.keys() else None
    metadata = phase5_calendar_metadata_for_event(event_id) if event_id else None

    for key in ["calendar_type", "item_type"]:
        if metadata and key in metadata.keys() and metadata[key]:
            return str(metadata[key]).strip()

    title = str(event["title"] if "title" in event.keys() and event["title"] else "").lower()
    related = str(event["related_to"] if "related_to" in event.keys() and event["related_to"] else "").lower()
    details = str(event["details_json"] if "details_json" in event.keys() and event["details_json"] else "").lower()
    merged = f"{title} {related} {details}"

    if "battle" in merged or "body bag" in merged:
        return "battle"
    if "class" in merged or "workshop" in merged:
        return "class"
    if "cypher" in merged:
        return "cypher"
    if "release" in merged or "music" in merged:
        return "music release"
    if "team" in merged:
        return "team event"
    if "practice" in merged:
        return "practice"
    if "performance" in merged or "showcase" in merged:
        return "performance"

    return "event"


def phase5_calendar_badges_for_event(event):
    event_id = event["id"] if "id" in event.keys() else None
    metadata = phase5_calendar_metadata_for_event(event_id) if event_id else None

    badges = []

    calendar_type = phase5_calendar_type_for_event(event)
    if calendar_type:
        badges.append(calendar_type.title())

    if metadata:
        for key, label in [
            ("borough", None),
            ("venue_name", None),
            ("visibility_status", None),
            ("review_status", None),
            ("recurrence_label", None),
        ]:
            if key in metadata.keys() and metadata[key]:
                badges.append(label or str(metadata[key]).strip())

        if "recurrence_rule" in metadata.keys() and metadata["recurrence_rule"]:
            badges.append("Recurring")

    if "review_status" in event.keys() and event["review_status"]:
        badges.append(str(event["review_status"]).strip())

    clean_badges = []
    seen = set()

    for badge in badges:
        badge = str(badge or "").strip()
        if not badge:
            continue

        key = badge.lower()
        if key in seen:
            continue

        seen.add(key)
        clean_badges.append(badge)

    return clean_badges[:6]


def phase5_calendar_filter_options():
    return [
        {"value": "all", "label": "All"},
        {"value": "battle", "label": "Battles"},
        {"value": "class", "label": "Classes"},
        {"value": "cypher", "label": "Cyphers"},
        {"value": "workshop", "label": "Workshops"},
        {"value": "practice", "label": "Practice"},
        {"value": "performance", "label": "Performances"},
        {"value": "music release", "label": "Music Releases"},
        {"value": "team event", "label": "Team Events"},
        {"value": "community event", "label": "Community Events"},
        {"value": "other", "label": "Other"},
    ]


def phase5_calendar_view_options():
    return [
        {"value": "cards", "label": "Cards"},
        {"value": "list", "label": "List"},
        {"value": "compact", "label": "Compact"},
    ]


def phase5_calendar_selected_type():
    selected = request.args.get("type", "all").strip().lower()
    allowed = {item["value"] for item in phase5_calendar_filter_options()}

    if selected not in allowed:
        selected = "all"

    return selected


def phase5_calendar_selected_view():
    selected = request.args.get("view", "cards").strip().lower()
    allowed = {item["value"] for item in phase5_calendar_view_options()}

    if selected not in allowed:
        selected = "cards"

    return selected


def phase5_calendar_item_matches_filter(event, selected_type=None):
    selected_type = selected_type or phase5_calendar_selected_type()

    if selected_type == "all":
        return True

    event_type = phase5_calendar_type_for_event(event).strip().lower()

    if selected_type == event_type:
        return True

    if selected_type == "workshop" and "workshop" in event_type:
        return True

    if selected_type == "community event" and event_type in {"event", "community event"}:
        return True

    if selected_type == "other" and event_type in {"event", "other"}:
        return True

    return False


@app.context_processor
def inject_phase5_calendar_helpers():
    return {
        "phase5_calendar_metadata_for_event": phase5_calendar_metadata_for_event,
        "phase5_calendar_type_for_event": phase5_calendar_type_for_event,
        "phase5_calendar_badges_for_event": phase5_calendar_badges_for_event,
        "phase5_calendar_filter_options": phase5_calendar_filter_options,
        "phase5_calendar_view_options": phase5_calendar_view_options,
        "phase5_calendar_selected_type": phase5_calendar_selected_type,
        "phase5_calendar_selected_view": phase5_calendar_selected_view,
        "phase5_calendar_item_matches_filter": phase5_calendar_item_matches_filter,
        "phase5_get_event_detail": phase5_get_event_detail,
    }


@app.route("/admin/calendar-review")
def admin_calendar_review_phase5c():
    gate = phase5_admin_required()
    if gate:
        return gate

    ensure_phase5_calendar_tables()

    metadata_rows = fetch_all(
        """
        SELECT calendar_item_metadata.*,
               submissions.title AS event_title,
               submissions.review_status AS event_review_status,
               submissions.created_at AS event_created_at
        FROM calendar_item_metadata
        LEFT JOIN submissions
          ON calendar_item_metadata.submission_id = submissions.id
        ORDER BY
            COALESCE(calendar_item_metadata.updated_at, calendar_item_metadata.created_at, '') DESC,
            calendar_item_metadata.id DESC
        LIMIT 200
        """,
        {},
    )

    event_rows = fetch_all(
        """
        SELECT *
        FROM submissions
        WHERE submission_type = 'event'
        ORDER BY id DESC
        LIMIT 100
        """,
        {},
    )

    status_counts = fetch_all(
        """
        SELECT
            COALESCE(visibility_status, 'Unset') AS visibility_status,
            COUNT(*) AS count
        FROM calendar_item_metadata
        GROUP BY COALESCE(visibility_status, 'Unset')
        ORDER BY count DESC
        """,
        {},
    )

    type_counts = fetch_all(
        """
        SELECT
            COALESCE(calendar_type, item_type, 'event') AS calendar_type,
            COUNT(*) AS count
        FROM calendar_item_metadata
        GROUP BY COALESCE(calendar_type, item_type, 'event')
        ORDER BY count DESC
        """,
        {},
    )

    return render_template(
        "admin_calendar_review.html",
        metadata_rows=metadata_rows,
        event_rows=event_rows,
        status_counts=status_counts,
        type_counts=type_counts,
    )


@app.route("/admin/calendar-review/<int:metadata_id>/status", methods=["POST"])
def admin_calendar_review_status_phase5c(metadata_id):
    gate = phase5_admin_required()
    if gate:
        return gate

    ensure_phase5_calendar_tables()

    allowed_visibility = {
        "Visible",
        "Hidden",
        "Needs Review",
        "Draft",
        "Archived",
    }

    allowed_review = {
        "Pending Review",
        "Verified",
        "Community Supported",
        "Needs Verification",
        "Disputed",
        "Archived",
    }

    visibility_status = request.form.get("visibility_status", "").strip()
    review_status = request.form.get("review_status", "").strip()
    calendar_type = request.form.get("calendar_type", "").strip()
    admin_note = request.form.get("admin_note", "").strip()

    if visibility_status not in allowed_visibility:
        visibility_status = "Needs Review"

    if review_status not in allowed_review:
        review_status = "Pending Review"

    execute_query(
        """
        UPDATE calendar_item_metadata
        SET visibility_status = :visibility_status,
            review_status = :review_status,
            calendar_type = :calendar_type,
            admin_note = :admin_note,
            updated_at = :updated_at
        WHERE id = :metadata_id
        """,
        {
            "visibility_status": visibility_status,
            "review_status": review_status,
            "calendar_type": calendar_type,
            "admin_note": admin_note,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "metadata_id": metadata_id,
        },
    )

    return redirect(url_for("admin_calendar_review_phase5c"))


try:
    ensure_phase5_calendar_tables()
except Exception as exc:
    print(f"Phase 5 calendar setup skipped: {exc}")


# --- Phase 5D + 5E + 5F calendar finish batch ---
def phase5d_recurrence_options():
    return [
        {"value": "", "label": "One-time event"},
        {"value": "weekly", "label": "Weekly"},
        {"value": "biweekly", "label": "Every 2 weeks"},
        {"value": "monthly", "label": "Monthly"},
        {"value": "custom", "label": "Custom / needs review"},
    ]


def phase5d_recurrence_label(value):
    labels = {
        "": "One-time event",
        "weekly": "Weekly",
        "biweekly": "Every 2 weeks",
        "monthly": "Monthly",
        "custom": "Custom / needs review",
    }

    return labels.get(str(value or "").strip().lower(), str(value or "").strip())


def phase5d_calendar_metadata_summary(event):
    metadata = phase5_calendar_metadata_for_event(event["id"])

    if not metadata:
        return {
            "calendar_type": phase5_calendar_type_for_event(event),
            "visibility_status": "",
            "review_status": event["review_status"] if "review_status" in event.keys() else "",
            "start_datetime": phase5_get_event_detail(event, "Event Date"),
            "end_datetime": phase5_get_event_detail(event, "Event Time"),
            "venue_name": phase5_get_event_detail(event, "Event Location"),
            "borough": "",
            "ticket_url": "",
            "rsvp_url": "",
            "flyer_url": "",
            "recurrence_rule": "",
            "recurrence_label": "",
            "admin_note": "",
        }

    return {
        "calendar_type": metadata["calendar_type"] if "calendar_type" in metadata.keys() else "",
        "visibility_status": metadata["visibility_status"] if "visibility_status" in metadata.keys() else "",
        "review_status": metadata["review_status"] if "review_status" in metadata.keys() else "",
        "start_datetime": metadata["start_datetime"] if "start_datetime" in metadata.keys() else "",
        "end_datetime": metadata["end_datetime"] if "end_datetime" in metadata.keys() else "",
        "venue_name": metadata["venue_name"] if "venue_name" in metadata.keys() else "",
        "borough": metadata["borough"] if "borough" in metadata.keys() else "",
        "ticket_url": metadata["ticket_url"] if "ticket_url" in metadata.keys() else "",
        "rsvp_url": metadata["rsvp_url"] if "rsvp_url" in metadata.keys() else "",
        "flyer_url": metadata["flyer_url"] if "flyer_url" in metadata.keys() else "",
        "recurrence_rule": metadata["recurrence_rule"] if "recurrence_rule" in metadata.keys() else "",
        "recurrence_label": metadata["recurrence_label"] if "recurrence_label" in metadata.keys() else "",
        "admin_note": metadata["admin_note"] if "admin_note" in metadata.keys() else "",
    }


@app.context_processor
def inject_phase5d_calendar_finish_helpers():
    return {
        "phase5d_recurrence_options": phase5d_recurrence_options,
        "phase5d_recurrence_label": phase5d_recurrence_label,
        "phase5d_calendar_metadata_summary": phase5d_calendar_metadata_summary,
    }


def phase5d_upsert_calendar_metadata_for_submission(submission_id, form):
    ensure_phase5_calendar_tables()

    now_value = datetime.now().isoformat(timespec="seconds")

    calendar_type = form.get("calendar_type", "").strip()
    recurrence_rule = form.get("recurrence_rule", "").strip()
    recurrence_label = form.get("recurrence_label", "").strip()

    if not recurrence_label:
        recurrence_label = phase5d_recurrence_label(recurrence_rule)

    values = {
        "submission_id": submission_id,
        "calendar_type": calendar_type,
        "item_type": calendar_type,
        "visibility_status": form.get("visibility_status", "Needs Review").strip() or "Needs Review",
        "review_status": form.get("review_status", "Pending Review").strip() or "Pending Review",
        "start_datetime": form.get("start_datetime", "").strip(),
        "end_datetime": form.get("end_datetime", "").strip(),
        "venue_name": form.get("venue_name", "").strip(),
        "borough": form.get("borough", "").strip(),
        "ticket_url": form.get("ticket_url", "").strip(),
        "rsvp_url": form.get("rsvp_url", "").strip(),
        "flyer_url": form.get("flyer_url", "").strip(),
        "recurrence_rule": recurrence_rule,
        "recurrence_label": recurrence_label,
        "admin_note": form.get("admin_note", "").strip(),
        "updated_at": now_value,
    }

    existing = fetch_all(
        """
        SELECT id
        FROM calendar_item_metadata
        WHERE submission_id = :submission_id
        ORDER BY id DESC
        LIMIT 1
        """,
        {"submission_id": submission_id},
    )

    if existing:
        metadata_id = existing[0]["id"]

        allowed_keys = list(values.keys())
        set_sql = ", ".join(f"{key} = :{key}" for key in allowed_keys if key != "submission_id")

        execute_query(
            f"""
            UPDATE calendar_item_metadata
            SET {set_sql}
            WHERE id = :metadata_id
            """,
            {
                **values,
                "metadata_id": metadata_id,
            },
        )

        return metadata_id

    values["created_at"] = now_value

    with engine.begin() as conn:
        columns = phase5_table_columns(conn, "calendar_item_metadata")
        clean_values = {key: value for key, value in values.items() if key in columns}

        columns_sql = ", ".join(clean_values.keys())
        values_sql = ", ".join(f":{key}" for key in clean_values.keys())

        if maintenance_uses_postgres():
            result = conn.execute(
                text(f"INSERT INTO calendar_item_metadata ({columns_sql}) VALUES ({values_sql}) RETURNING id"),
                clean_values,
            )
            return result.scalar()

        result = conn.execute(
            text(f"INSERT INTO calendar_item_metadata ({columns_sql}) VALUES ({values_sql})"),
            clean_values,
        )
        return result.lastrowid


@app.route("/admin/calendar-review/<int:metadata_id>/recurrence", methods=["POST"])
def admin_calendar_recurrence_phase5d(metadata_id):
    gate = phase5_admin_required()
    if gate:
        return gate

    ensure_phase5_calendar_tables()

    recurrence_rule = request.form.get("recurrence_rule", "").strip()
    recurrence_label = request.form.get("recurrence_label", "").strip()

    if not recurrence_label:
        recurrence_label = phase5d_recurrence_label(recurrence_rule)

    execute_query(
        """
        UPDATE calendar_item_metadata
        SET recurrence_rule = :recurrence_rule,
            recurrence_label = :recurrence_label,
            updated_at = :updated_at
        WHERE id = :metadata_id
        """,
        {
            "recurrence_rule": recurrence_rule,
            "recurrence_label": recurrence_label,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "metadata_id": metadata_id,
        },
    )

    return redirect(url_for("admin_calendar_review_phase5c"))


# --- Phase 6A + 6B + 6C music batch ---
def phase6_admin_required():
    if not current_user_is_admin():
        return redirect(url_for("admin_login"))
    return None


def phase6_table_exists(conn, table_name):
    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                LIMIT 1
            """),
            {"table_name": table_name},
        ).fetchall()
        return bool(rows)

    rows = conn.execute(
        text("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = :table_name
            LIMIT 1
        """),
        {"table_name": table_name},
    ).fetchall()
    return bool(rows)


def phase6_table_columns(conn, table_name):
    if "ledger_table_columns" in globals():
        return ledger_table_columns(conn, table_name)

    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
            """),
            {"table_name": table_name},
        ).fetchall()
        return {row[0] for row in rows}

    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def phase6_add_column_if_missing(conn, table_name, column_name, column_sql):
    if not phase6_table_exists(conn, table_name):
        return

    columns = phase6_table_columns(conn, table_name)

    if column_name in columns:
        return

    if maintenance_uses_postgres():
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_sql}"))
    else:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def ensure_phase6_music_feedback_tables():
    with engine.begin() as conn:
        if maintenance_uses_postgres():
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS music_feedback (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER,
                    media_item_id INTEGER,
                    release_id INTEGER,
                    project_id INTEGER,
                    user_id INTEGER,
                    rating_category TEXT,
                    rating_value INTEGER,
                    reaction_label TEXT,
                    feedback_text TEXT,
                    feedback_status TEXT,
                    admin_note TEXT,
                    visitor_key TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """)
            )
        else:
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS music_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER,
                    media_item_id INTEGER,
                    release_id INTEGER,
                    project_id INTEGER,
                    user_id INTEGER,
                    rating_category TEXT,
                    rating_value INTEGER,
                    reaction_label TEXT,
                    feedback_text TEXT,
                    feedback_status TEXT,
                    admin_note TEXT,
                    visitor_key TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """)
            )

        for column_name, column_sql in [
            ("item_id", "INTEGER"),
            ("media_item_id", "INTEGER"),
            ("release_id", "INTEGER"),
            ("project_id", "INTEGER"),
            ("user_id", "INTEGER"),
            ("rating_category", "TEXT"),
            ("rating_value", "INTEGER"),
            ("reaction_label", "TEXT"),
            ("feedback_text", "TEXT"),
            ("feedback_status", "TEXT"),
            ("admin_note", "TEXT"),
            ("visitor_key", "TEXT"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT"),
        ]:
            phase6_add_column_if_missing(conn, "music_feedback", column_name, column_sql)


def phase6_row_to_dict(row):
    try:
        return dict(row._mapping)
    except Exception:
        return dict(row)


def phase6_value(row, *keys, default=""):
    if not row:
        return default

    for key in keys:
        try:
            if key in row.keys() and row[key] not in (None, ""):
                return row[key]
        except Exception:
            pass

        try:
            value = row.get(key)
            if value not in (None, ""):
                return value
        except Exception:
            pass

    return default


def phase6_music_title(item):
    return phase6_value(item, "title", "track_title", "project_title", "name", default="Untitled Release")


def phase6_music_artist(item):
    return phase6_value(item, "artist_or_creator", "artist_name", "artist", "creator", "producer", "producer_name", default="Unknown Artist")


def phase6_music_platform(item):
    platform = phase6_value(item, "platform", "source_platform", "media_platform", default="")
    url = str(phase6_music_url(item) or "").lower()

    if platform:
        return platform

    if "soundcloud" in url:
        return "SoundCloud"
    if "youtube" in url or "youtu.be" in url:
        return "YouTube"
    if "spotify" in url:
        return "Spotify"
    if "apple" in url:
        return "Apple Music"

    return "Ledger"


def phase6_music_url(item):
    return phase6_value(item, "url", "source_url", "video_url", "audio_url", "link", default="")


def phase6_music_date(item):
    return phase6_value(item, "release_date", "date", "created_at", "updated_at", default="")


def phase6_music_description(item):
    return phase6_value(item, "description", "notes", "details", "caption", default="")


def phase6_music_type(item):
    raw = str(phase6_value(item, "media_type", "release_type", "type", "category", default="")).lower()
    title = str(phase6_music_title(item) or "").lower()
    merged = f"{raw} {title}"

    if "project" in merged or "album" in merged or "ep" in merged or "tape" in merged:
        return "project"
    if "battle" in merged:
        return "battle track"
    if "video" in merged or "youtube" in str(phase6_music_url(item)).lower():
        return "video"
    if "playlist" in merged:
        return "playlist"
    if "producer" in merged or "beat" in merged:
        return "producer"
    if "track" in merged or "song" in merged or raw:
        return raw or "track"

    return "track"


def phase6_music_filter_options():
    return [
        {"value": "all", "label": "All Music"},
        {"value": "track", "label": "Tracks"},
        {"value": "project", "label": "Projects"},
        {"value": "battle track", "label": "Battle Tracks"},
        {"value": "producer", "label": "Producer / Beat"},
        {"value": "video", "label": "Videos"},
        {"value": "playlist", "label": "Playlists"},
    ]


def phase6_music_platform_options():
    return [
        {"value": "all", "label": "All Platforms"},
        {"value": "SoundCloud", "label": "SoundCloud"},
        {"value": "YouTube", "label": "YouTube"},
        {"value": "Spotify", "label": "Spotify"},
        {"value": "Apple Music", "label": "Apple Music"},
        {"value": "Ledger", "label": "Ledger"},
    ]


def phase6_selected_music_type():
    selected = request.args.get("type", "all").strip().lower()
    allowed = {item["value"] for item in phase6_music_filter_options()}

    if selected not in allowed:
        selected = "all"

    return selected


def phase6_selected_platform():
    selected = request.args.get("platform", "all").strip()
    allowed = {item["value"] for item in phase6_music_platform_options()}

    if selected not in allowed:
        selected = "all"

    return selected


def phase6_music_search_query():
    return request.args.get("q", "").strip()


def phase6_fetch_music_releases(limit=250):
    with engine.connect() as conn:
        if not phase6_table_exists(conn, "media_items"):
            return []

    try:
        rows = fetch_all(
            """
            SELECT *
            FROM media_items
            ORDER BY
                COALESCE(created_at, updated_at, '') DESC,
                id DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )
        return rows
    except Exception:
        return []


def phase6_fetch_music_projects(limit=100):
    with engine.connect() as conn:
        if not phase6_table_exists(conn, "music_projects"):
            return []

    try:
        rows = fetch_all(
            """
            SELECT *
            FROM music_projects
            ORDER BY
                COALESCE(created_at, updated_at, '') DESC,
                id DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )
        return rows
    except Exception:
        return []


def phase6_music_item_matches(item, selected_type=None, selected_platform=None, query=None):
    selected_type = selected_type or phase6_selected_music_type()
    selected_platform = selected_platform or phase6_selected_platform()
    query = query if query is not None else phase6_music_search_query()

    item_type = str(phase6_music_type(item) or "").lower()
    platform = str(phase6_music_platform(item) or "")

    if selected_type != "all" and selected_type != item_type:
        if selected_type == "track" and item_type in {"song", "single", "audio"}:
            pass
        else:
            return False

    if selected_platform != "all" and selected_platform.lower() != platform.lower():
        return False

    if query:
        merged = " ".join(
            str(value or "")
            for value in [
                phase6_music_title(item),
                phase6_music_artist(item),
                phase6_music_platform(item),
                phase6_music_description(item),
                phase6_music_url(item),
            ]
        ).lower()

        if query.lower() not in merged:
            return False

    return True


def phase6_music_feedback_counts(item_id):
    ensure_phase6_music_feedback_tables()

    try:
        rows = fetch_all(
            """
            SELECT
                COALESCE(reaction_label, rating_category, 'Feedback') AS label,
                COUNT(*) AS count
            FROM music_feedback
            WHERE item_id = :item_id
               OR media_item_id = :item_id
               OR release_id = :item_id
            GROUP BY COALESCE(reaction_label, rating_category, 'Feedback')
            ORDER BY count DESC
            """,
            {"item_id": item_id},
        )
        return rows
    except Exception:
        return []


def phase6_insert_music_feedback(values):
    ensure_phase6_music_feedback_tables()

    now_value = datetime.now().isoformat(timespec="seconds")
    values.setdefault("created_at", now_value)
    values.setdefault("updated_at", now_value)
    values.setdefault("feedback_status", "New")

    with engine.begin() as conn:
        columns = phase6_table_columns(conn, "music_feedback")
        clean_values = {key: value for key, value in values.items() if key in columns}

        if not clean_values:
            return None

        columns_sql = ", ".join(clean_values.keys())
        values_sql = ", ".join(f":{key}" for key in clean_values.keys())

        if maintenance_uses_postgres():
            result = conn.execute(
                text(f"INSERT INTO music_feedback ({columns_sql}) VALUES ({values_sql}) RETURNING id"),
                clean_values,
            )
            return result.scalar()

        result = conn.execute(
            text(f"INSERT INTO music_feedback ({columns_sql}) VALUES ({values_sql})"),
            clean_values,
        )
        return result.lastrowid


def phase6_fetch_admin_music_feedback(limit=200):
    ensure_phase6_music_feedback_tables()

    try:
        rows = fetch_all(
            """
            SELECT music_feedback.*,
                   media_items.title AS release_title,
                   media_items.artist_or_creator AS release_artist,
                   media_items.url AS release_url,
                   archive_users.display_name AS user_display_name,
                   archive_users.email AS user_email
            FROM music_feedback
            LEFT JOIN media_items
              ON music_feedback.item_id = media_items.id
              OR music_feedback.media_item_id = media_items.id
              OR music_feedback.release_id = media_items.id
            LEFT JOIN archive_users
              ON music_feedback.user_id = archive_users.id
            ORDER BY
                COALESCE(music_feedback.updated_at, music_feedback.created_at, '') DESC,
                music_feedback.id DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )
        return rows
    except Exception:
        return fetch_all(
            """
            SELECT *
            FROM music_feedback
            ORDER BY id DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )


@app.context_processor
def inject_phase6_music_helpers():
    return {
        "phase6_value": phase6_value,
        "phase6_music_title": phase6_music_title,
        "phase6_music_artist": phase6_music_artist,
        "phase6_music_platform": phase6_music_platform,
        "phase6_music_url": phase6_music_url,
        "phase6_music_date": phase6_music_date,
        "phase6_music_description": phase6_music_description,
        "phase6_music_type": phase6_music_type,
        "phase6_music_filter_options": phase6_music_filter_options,
        "phase6_music_platform_options": phase6_music_platform_options,
        "phase6_selected_music_type": phase6_selected_music_type,
        "phase6_selected_platform": phase6_selected_platform,
        "phase6_music_search_query": phase6_music_search_query,
        "phase6_fetch_music_releases": phase6_fetch_music_releases,
        "phase6_fetch_music_projects": phase6_fetch_music_projects,
        "phase6_music_item_matches": phase6_music_item_matches,
        "phase6_music_feedback_counts": phase6_music_feedback_counts,
    }


@app.route("/music/releases/<int:item_id>/feedback", methods=["POST"])
def submit_music_feedback_phase6(item_id):
    ensure_phase6_music_feedback_tables()

    user = current_user()

    reaction_label = request.form.get("reaction_label", "").strip()
    rating_category = request.form.get("rating_category", "").strip()
    feedback_text = request.form.get("feedback_text", "").strip()
    rating_value_raw = request.form.get("rating_value", "").strip()

    try:
        rating_value = int(rating_value_raw) if rating_value_raw else None
    except Exception:
        rating_value = None

    if rating_value is not None:
        rating_value = max(1, min(10, rating_value))

    phase6_insert_music_feedback(
        {
            "item_id": item_id,
            "media_item_id": item_id,
            "release_id": item_id,
            "project_id": None,
            "user_id": user["id"] if user else None,
            "rating_category": rating_category or "General",
            "rating_value": rating_value,
            "reaction_label": reaction_label or "Feedback",
            "feedback_text": feedback_text,
            "visitor_key": session.get("visitor_key", ""),
            "feedback_status": "New",
        }
    )

    return redirect(url_for("music_release_detail", item_id=item_id))


@app.route("/admin/music-feedback")
def admin_music_feedback_phase6c():
    gate = phase6_admin_required()
    if gate:
        return gate

    ensure_phase6_music_feedback_tables()

    feedback_rows = phase6_fetch_admin_music_feedback()

    status_counts = fetch_all(
        """
        SELECT COALESCE(feedback_status, 'New') AS feedback_status,
               COUNT(*) AS count
        FROM music_feedback
        GROUP BY COALESCE(feedback_status, 'New')
        ORDER BY count DESC
        """,
        {},
    )

    reaction_counts = fetch_all(
        """
        SELECT COALESCE(reaction_label, rating_category, 'Feedback') AS reaction_label,
               COUNT(*) AS count
        FROM music_feedback
        GROUP BY COALESCE(reaction_label, rating_category, 'Feedback')
        ORDER BY count DESC
        """,
        {},
    )

    return render_template(
        "admin_music_feedback.html",
        feedback_rows=feedback_rows,
        status_counts=status_counts,
        reaction_counts=reaction_counts,
    )


@app.route("/admin/music-feedback/<int:feedback_id>/status", methods=["POST"])
def admin_music_feedback_status_phase6c(feedback_id):
    gate = phase6_admin_required()
    if gate:
        return gate

    ensure_phase6_music_feedback_tables()

    feedback_status = request.form.get("feedback_status", "").strip()
    admin_note = request.form.get("admin_note", "").strip()

    allowed = {
        "New",
        "Reviewed",
        "Needs Follow-up",
        "Needs Source",
        "Added to Review",
        "Archived",
        "Dismissed",
    }

    if feedback_status not in allowed:
        feedback_status = "New"

    execute_query(
        """
        UPDATE music_feedback
        SET feedback_status = :feedback_status,
            admin_note = :admin_note,
            updated_at = :updated_at
        WHERE id = :feedback_id
        """,
        {
            "feedback_status": feedback_status,
            "admin_note": admin_note,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "feedback_id": feedback_id,
        },
    )

    return redirect(url_for("admin_music_feedback_phase6c"))


try:
    ensure_phase6_music_feedback_tables()
except Exception as exc:
    print(f"Phase 6 music feedback setup skipped: {exc}")


# --- Phase 6D + 6E + 6F music finish batch ---
def phase6d_table_exists(conn, table_name):
    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                LIMIT 1
            """),
            {"table_name": table_name},
        ).fetchall()
        return bool(rows)

    rows = conn.execute(
        text("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = :table_name
            LIMIT 1
        """),
        {"table_name": table_name},
    ).fetchall()
    return bool(rows)


def phase6d_table_columns(conn, table_name):
    if "ledger_table_columns" in globals():
        return ledger_table_columns(conn, table_name)

    if maintenance_uses_postgres():
        rows = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
            """),
            {"table_name": table_name},
        ).fetchall()
        return {row[0] for row in rows}

    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def phase6d_add_column_if_missing(conn, table_name, column_name, column_sql):
    if not phase6d_table_exists(conn, table_name):
        return

    columns = phase6d_table_columns(conn, table_name)

    if column_name in columns:
        return

    if maintenance_uses_postgres():
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_sql}"))
    else:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def ensure_phase6d_music_project_columns():
    with engine.begin() as conn:
        if phase6d_table_exists(conn, "music_projects"):
            for column_name, column_sql in [
                ("project_type", "TEXT"),
                ("artist_name", "TEXT"),
                ("producer_name", "TEXT"),
                ("release_date", "TEXT"),
                ("platform", "TEXT"),
                ("source_url", "TEXT"),
                ("cover_url", "TEXT"),
                ("description", "TEXT"),
                ("review_status", "TEXT"),
                ("created_at", "TEXT"),
                ("updated_at", "TEXT"),
            ]:
                phase6d_add_column_if_missing(conn, "music_projects", column_name, column_sql)

        if phase6d_table_exists(conn, "media_items"):
            for column_name, column_sql in [
                ("project_id", "INTEGER"),
                ("release_type", "TEXT"),
                ("artist_name", "TEXT"),
                ("producer_name", "TEXT"),
                ("release_date", "TEXT"),
                ("platform", "TEXT"),
                ("review_status", "TEXT"),
            ]:
                phase6d_add_column_if_missing(conn, "media_items", column_name, column_sql)


def phase6d_row_to_dict(row):
    try:
        return dict(row._mapping)
    except Exception:
        return dict(row)


def phase6d_fetch_project(project_id):
    ensure_phase6d_music_project_columns()

    rows = fetch_all(
        """
        SELECT *
        FROM music_projects
        WHERE id = :project_id
        LIMIT 1
        """,
        {"project_id": project_id},
    )

    return rows[0] if rows else None


def phase6d_project_title(project):
    return phase6_value(project, "title", "project_title", "name", default="Untitled Project")


def phase6d_project_artist(project):
    return phase6_value(project, "artist_name", "artist", "producer_name", "creator", default="Unknown Artist")


def phase6d_project_url(project):
    return phase6_value(project, "source_url", "url", "link", default="")


def phase6d_project_description(project):
    return phase6_value(project, "description", "notes", "details", default="")


def phase6d_project_tracks(project_id):
    ensure_phase6d_music_project_columns()

    with engine.connect() as conn:
        if not phase6d_table_exists(conn, "media_items"):
            return []

        columns = phase6d_table_columns(conn, "media_items")

    if "project_id" in columns:
        try:
            return fetch_all(
                """
                SELECT *
                FROM media_items
                WHERE project_id = :project_id
                ORDER BY id ASC
                LIMIT 100
                """,
                {"project_id": project_id},
            )
        except Exception:
            return []

    return []


def phase6d_music_matches_name(item, name):
    if not name:
        return False

    needle = str(name or "").strip().lower()

    if not needle:
        return False

    merged = " ".join(
        str(value or "")
        for value in [
            phase6_music_title(item),
            phase6_music_artist(item),
            phase6_value(item, "producer_name", "producer", "creator", "artist_name"),
            phase6_music_description(item),
        ]
    ).lower()

    return needle in merged


def phase6d_music_for_profile(profile, limit=8):
    if not profile:
        return []

    names = []

    for key in ["dance_name", "real_name", "producer_name", "artist_name"]:
        try:
            value = profile[key]
        except Exception:
            value = ""

        if value:
            names.append(str(value).strip())

    names = [name for name in names if name]

    if not names:
        return []

    matches = []

    for item in phase6_fetch_music_releases(limit=300):
        for name in names:
            if phase6d_music_matches_name(item, name):
                matches.append(item)
                break

        if len(matches) >= limit:
            break

    return matches


def phase6d_projects_for_profile(profile, limit=6):
    if not profile:
        return []

    names = []

    for key in ["dance_name", "real_name", "producer_name", "artist_name"]:
        try:
            value = profile[key]
        except Exception:
            value = ""

        if value:
            names.append(str(value).strip())

    if not names:
        return []

    matches = []

    for project in phase6_fetch_music_projects(limit=200):
        merged = " ".join(
            str(value or "")
            for value in [
                phase6d_project_title(project),
                phase6d_project_artist(project),
                phase6d_project_description(project),
            ]
        ).lower()

        for name in names:
            if name.lower() in merged:
                matches.append(project)
                break

        if len(matches) >= limit:
            break

    return matches


def phase6d_fetch_producers(limit=250):
    with engine.connect() as conn:
        if not phase6d_table_exists(conn, "dancer_profiles"):
            return []

        columns = phase6d_table_columns(conn, "dancer_profiles")

    role_sql = ""

    if "role_tags" in columns:
        role_sql = "OR LOWER(COALESCE(role_tags, '')) LIKE '%producer%'"

    try:
        return fetch_all(
            f"""
            SELECT *
            FROM dancer_profiles
            WHERE LOWER(COALESCE(dance_name, '')) LIKE '%producer%'
               OR LOWER(COALESCE(team_affiliation, '')) LIKE '%producer%'
               OR LOWER(COALESCE(bio, '')) LIKE '%producer%'
               {role_sql}
            ORDER BY LOWER(COALESCE(dance_name, real_name, '')) ASC
            LIMIT :limit
            """,
            {"limit": limit},
        )
    except Exception:
        return []


def phase6d_producer_music_count(profile):
    return len(phase6d_music_for_profile(profile, limit=50)) + len(phase6d_projects_for_profile(profile, limit=50))


@app.context_processor
def inject_phase6d_music_finish_helpers():
    return {
        "phase6d_fetch_project": phase6d_fetch_project,
        "phase6d_project_title": phase6d_project_title,
        "phase6d_project_artist": phase6d_project_artist,
        "phase6d_project_url": phase6d_project_url,
        "phase6d_project_description": phase6d_project_description,
        "phase6d_project_tracks": phase6d_project_tracks,
        "phase6d_music_for_profile": phase6d_music_for_profile,
        "phase6d_projects_for_profile": phase6d_projects_for_profile,
        "phase6d_fetch_producers": phase6d_fetch_producers,
        "phase6d_producer_music_count": phase6d_producer_music_count,
    }


@app.route("/litefeet-music/projects/<int:project_id>")
def music_project_detail_phase6e(project_id):
    ensure_phase6d_music_project_columns()

    project = phase6d_fetch_project(project_id)

    if not project:
        return redirect(url_for("litefeet_music"))

    tracks = phase6d_project_tracks(project_id)

    return render_template(
        "music_project_detail.html",
        project=project,
        tracks=tracks,
    )


try:
    ensure_phase6d_music_project_columns()
except Exception as exc:
    print(f"Phase 6D music project setup skipped: {exc}")
