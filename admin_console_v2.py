"""Focused admin attention inbox, development workflow, and visitor snapshot.

Registered from app.py after the existing application routes. No historical tables are
modified. All dynamic source identifiers below are hard-coded, never user supplied.
"""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from hmac import compare_digest
import secrets
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import inspect, text

PAGE_SIZE = 10
NY = ZoneInfo("America/New_York")
OPEN_DEVELOPMENT = ("Needs Review", "Needs Work")
DEV_STATUSES = ("Needs Review", "Needs Work", "Planned", "Active", "Done", "Not Planned")
DEV_CATEGORIES = ("Bug", "Feature Request", "Design", "Accessibility", "Other")
ATTENTION_SOURCES = (
    dict(section="Submissions", table="submissions", label="Submission",
         condition="COALESCE(review_status, 'Pending Review') IN ('Pending Review', 'Needs Verification', 'Needs Review')",
         required=("review_status",), status=("review_status",), title=("title", "name", "submission_type"),
         link="/admin/submissions"),
    dict(section="People & Teams", table="profile_claims", label="Profile claim",
         condition="COALESCE(claim_status, 'Pending Review') IN ('Pending Review', 'Needs Review')",
         required=("claim_status",), status=("claim_status",), title=("profile_name", "requested_name", "claim_name"),
         link="/admin/phase2"),
    dict(section="People & Teams", table="profile_edit_logs", label="Profile edit",
         condition="COALESCE(edit_status, 'Logged') IN ('Logged', 'Needs Follow-up')",
         required=("edit_status",), status=("edit_status",), title=("edit_action", "change_summary"),
         link="/admin/profile-corrections"),
    dict(section="People & Teams", table="team_records", label="Team record",
         condition="COALESCE(review_status, 'Pending Review') IN ('Pending Review', 'Needs Verification', 'Disputed')",
         required=("review_status",), status=("review_status",), title=("team_name", "title", "name"),
         link="/admin/phase2"),
    dict(section="Battles & Events", table="calendar_item_metadata", label="Calendar entry",
         condition="COALESCE(visibility_status, 'Needs Review') IN ('Needs Review', 'Draft') OR COALESCE(review_status, 'Pending Review') IN ('Pending Review', 'Needs Verification')",
         required=("visibility_status", "review_status"), status=("review_status", "visibility_status"),
         title=("event_title", "title", "event_name"), link="/admin/calendar-review"),
    dict(section="Battles & Events", table="battle_records", label="Battle record",
         condition="COALESCE(review_status, 'Pending Review') IN ('Pending Review', 'Needs Verification', 'Disputed')",
         required=("review_status",), status=("review_status",), title=("title", "battle_name", "matchup"),
         link="/admin/phase2"),
    dict(section="Awards", table="award_records", label="Award record",
         condition="COALESCE(review_status, 'Pending Review') IN ('Pending Review', 'Needs Verification', 'Disputed')",
         required=("review_status",), status=("review_status",), title=("award_name", "category", "title"),
         link="/admin/phase2"),
    dict(section="Music & Media", table="music_feedback", label="Music feedback",
         condition="COALESCE(feedback_status, 'New') IN ('New', 'Needs Follow-up', 'Needs Source')",
         required=("feedback_status",), status=("feedback_status",), title=("feedback_text", "reaction_label", "rating_category"),
         link="/admin/music-feedback"),
    dict(section="Community", table="community_perspectives", label="Community context",
         condition="COALESCE(perspective_status, 'Pending Review') IN ('Pending Review', 'Needs Review')",
         required=("perspective_status",), status=("perspective_status",), title=("review_label", "related_type", "title"),
         link="/admin/phase2"),
    dict(section="Community", table="ask_feedback", label="Ask feedback",
         condition="COALESCE(feedback_status, 'New') IN ('New', 'Needs Fix', 'Needs Context')",
         required=("feedback_status",), status=("feedback_status",), title=("feedback_text", "rating_label"),
         link="/admin/ask-feedback"),
    dict(section="Development", table="lfv_development_items", label="Development feedback",
         condition="status IN ('Needs Review', 'Needs Work')",
         required=("status",), status=("status",), title=("title",),
         link="/admin/development"),
)
SECTIONS = ("All sections", "Submissions", "People & Teams", "Battles & Events",
            "Awards", "Music & Media", "Community", "Development")


def _page(value):
    try:
        return max(1, min(500, int(value)))
    except (ValueError, TypeError):
        return 1


def _dt(value):
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _display_date(value):
    d = _dt(value)
    if d is None:
        return "Date unavailable"
    return d.astimezone(NY).strftime("%b %-d, %Y · %-I:%M %p ET")


def _first(row, keys):
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _csrf_token():
    if not session.get("lfv_admin_csrf"):
        session["lfv_admin_csrf"] = secrets.token_urlsafe(32)
    return session["lfv_admin_csrf"]


def _valid_csrf():
    expected = session.get("lfv_admin_csrf") or ""
    provided = request.form.get("csrf_token", "")
    return bool(expected) and compare_digest(str(expected), str(provided))


def register_admin_console_v2(app, engine, is_admin, site_summary, review_cards):
    def _columns(table):
        try:
            return {col["name"] for col in inspect(engine).get_columns(table)}
        except Exception:
            return set()

    def _query(sql, values=None):
        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), values or {}).mappings().all()]

    def _scalar(sql, values=None):
        with engine.connect() as conn:
            return conn.execute(text(sql), values or {}).scalar()

    def _development_table():
        # Only create a new table. No DROP, no renaming existing data.
        with engine.begin() as conn:
            if engine.dialect.name == "postgresql":
                primary = "BIGSERIAL PRIMARY KEY"
            else:
                primary = "INTEGER PRIMARY KEY AUTOINCREMENT"
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS lfv_development_items (
                    id {primary},
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Other',
                    section_name TEXT,
                    page_url TEXT,
                    contact_email TEXT,
                    source TEXT NOT NULL DEFAULT 'Community',
                    status TEXT NOT NULL DEFAULT 'Needs Review',
                    submitter_key TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """))

    def _visitor_stats():
        cols = _columns("site_visits")
        if not {"created_at", "is_admin"}.issubset(cols):
            return dict(pageviews=0, visitors=0, top_pages=[], low_pages=[], visitor_rows=[], visitor_total=0)
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
        params = {"since": since}
        scope = "is_admin = 0 AND created_at >= :since"
        try:
            views = int(_scalar(f"SELECT COUNT(*) FROM site_visits WHERE {scope}", params) or 0)
            unique = int(_scalar(f"SELECT COUNT(DISTINCT visitor_id) FROM site_visits WHERE {scope}", params) or 0) if "visitor_id" in cols else 0
            top = _query(f"""
                SELECT path, COUNT(*) AS views
                FROM site_visits WHERE {scope} AND path IS NOT NULL AND path != ''
                GROUP BY path ORDER BY views DESC, path ASC LIMIT 10
            """, params)
            low = _query(f"""
                SELECT path, COUNT(*) AS views
                FROM site_visits WHERE {scope} AND path IS NOT NULL AND path != ''
                GROUP BY path ORDER BY views ASC, path ASC LIMIT 10
            """, params)
            return dict(pageviews=views, visitors=unique, top_pages=top, low_pages=low)
        except Exception:
            return dict(pageviews=0, visitors=0, top_pages=[], low_pages=[])

    def _visitor_list(page):
        cols = _columns("site_visits")
        if not {"visitor_id", "created_at", "is_admin"}.issubset(cols):
            return [], 0
        page = _page(page)
        try:
            total = int(_scalar("""
                SELECT COUNT(DISTINCT visitor_id) FROM site_visits
                WHERE is_admin = 0 AND visitor_id IS NOT NULL AND visitor_id != ''
            """) or 0)
            rows = _query("""
                SELECT visitor_id, COUNT(*) AS pageviews, COUNT(DISTINCT path) AS pages,
                       MAX(created_at) AS last_seen,
                       COUNT(DISTINCT user_id) AS known_user_ids, MAX(user_id) AS known_user_id
                FROM site_visits
                WHERE is_admin = 0 AND visitor_id IS NOT NULL AND visitor_id != ''
                GROUP BY visitor_id ORDER BY last_seen DESC, visitor_id ASC
                LIMIT :limit OFFSET :offset
            """, {"limit": PAGE_SIZE, "offset": (page - 1) * PAGE_SIZE})
            users_cols = _columns("archive_users")
            for row in rows:
                key = str(row["visitor_id"])
                row["ref"] = "V-" + key[:10].upper()
                row["email"] = ""
                row["last_seen_label"] = _display_date(row["last_seen"])
                # Only identify an account where a visit is explicitly tied to one account ID.
                # Email typed into an unrelated form is NOT evidence of browser ownership.
                if row.get("known_user_ids") == 1 and {"id", "email"}.issubset(users_cols):
                    user = _query("SELECT email FROM archive_users WHERE id = :id LIMIT 1",
                                  {"id": row["known_user_id"]})
                    row["email"] = (user[0].get("email") or "") if user else ""
            return rows, total
        except Exception:
            return [], 0

    def _attention(section, page, order):
        section = section if section in SECTIONS else "All sections"
        page = _page(page)
        order = order if order in {"oldest", "newest"} else "oldest"
        all_rows = []
        total = 0
        limit = page * PAGE_SIZE
        for source in ATTENTION_SOURCES:
            if section != "All sections" and source["section"] != section:
                continue
            cols = _columns(source["table"])
            if not cols or not set(source["required"]).issubset(cols) or "id" not in cols:
                continue
            try:
                count = int(_scalar(
                    f"SELECT COUNT(*) FROM {source['table']} WHERE {source['condition']}"
                ) or 0)
                total += count
                date_col = "created_at" if "created_at" in cols else ("updated_at" if "updated_at" in cols else "id")
                direction = "ASC" if order == "oldest" else "DESC"
                rows = _query(
                    f"SELECT * FROM {source['table']} WHERE {source['condition']} "
                    f"ORDER BY {date_col} {direction}, id {direction} LIMIT :limit",
                    {"limit": limit}
                )
                for row in rows:
                    title = _first(row, source["title"]) or f"{source['label']} #{row['id']}"
                    status = _first(row, source["status"]) or "Pending Review"
                    date_raw = row.get("created_at") or row.get("updated_at")
                    url = source["link"]
                    if source["table"] == "lfv_development_items":
                        url += f"?item={row['id']}"
                    all_rows.append(dict(id=row["id"], section=source["section"],
                                         title=title[:145], kind=source["label"],
                                         status=status, created_at=date_raw,
                                         date_label=_display_date(date_raw), url=url))
            except Exception:
                # A single legacy table must never take the whole dashboard offline.
                continue
        def key(item):
            date = _dt(item["created_at"])
            return (date is None, date or datetime.max.replace(tzinfo=timezone.utc),
                    item["section"], int(item["id"]))
        all_rows.sort(key=key, reverse=(order == "newest"))
        start = (page - 1) * PAGE_SIZE
        return dict(rows=all_rows[start:start + PAGE_SIZE],
                    total=total, page=page, max_page=max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
                    section=section, order=order)

    def _require_admin():
        if not is_admin():
            return redirect(url_for("admin_login", next=request.path))
        return None

    def _admin_home_v2():
        guard = _require_admin()
        if guard:
            return guard
        try:
            _development_table()
        except Exception:
            pass
        section = request.args.get("section", "All sections")
        order = request.args.get("order", "oldest")
        inbox = _attention(section, request.args.get("page", 1), order)
        visitors_page = _page(request.args.get("visitors_page", 1))
        visitors, visitors_total = _visitor_list(visitors_page)
        performance = request.args.get("performance", "top")
        stats = _visitor_stats()
        _csrf_token()
        return render_template(
            "admin_home.html", inbox=inbox, sections=SECTIONS, stats=stats,
            visitors=visitors, visitors_total=visitors_total, visitors_page=visitors_page,
            visitors_pages=max(1, (visitors_total + PAGE_SIZE - 1) // PAGE_SIZE),
            performance="low" if performance == "low" else "top",
            pending_total=inbox["total"] if inbox["section"] == "All sections" else None,
            development_open=sum(1 for x in inbox["rows"] if x["section"] == "Development"),
        )

    # Override the old overview endpoints without removing legacy review routes.
    app.view_functions["admin_home"] = _admin_home_v2
    if "admin_command_center_phase12" in app.view_functions:
        app.view_functions["admin_command_center_phase12"] = _admin_home_v2

    def _development_page():
        guard = _require_admin()
        if guard:
            return guard
        _development_table()
        status = request.args.get("status", "All")
        if status not in DEV_STATUSES:
            status = "All"
        page = _page(request.args.get("page", "1"))
        where = " WHERE status = :status" if status != "All" else ""
        values = {"status": status} if status != "All" else {}
        total = int(_scalar("SELECT COUNT(*) FROM lfv_development_items" + where, values) or 0)
        values.update(limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
        rows = _query(
            "SELECT * FROM lfv_development_items" + where +
            " ORDER BY created_at ASC, id ASC LIMIT :limit OFFSET :offset", values
        )
        for item in rows:
            item["date_label"] = _display_date(item["created_at"])
        summary = _query("SELECT status, COUNT(*) AS total FROM lfv_development_items GROUP BY status")
        selected = request.args.get("item", "")
        return render_template("admin_development.html", dev_items=rows, dev_total=total,
                               dev_page=page, dev_pages=max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
                               dev_filter=status, dev_statuses=DEV_STATUSES,
                               dev_categories=DEV_CATEGORIES,
                               dev_summary={r["status"]: r["total"] for r in summary},
                               dev_selected=selected, csrf_token=_csrf_token())

    app.add_url_rule("/admin/development", "lfv_admin_development", _development_page,
                     methods=["GET"])

    def _development_create():
        guard = _require_admin()
        if guard:
            return guard
        if not _valid_csrf():
            abort(400)
        _development_table()
        title = request.form.get("title", "").strip()[:140]
        description = request.form.get("description", "").strip()[:4000]
        status = request.form.get("status", "Planned")
        category = request.form.get("category", "Other")
        if not title or not description or status not in DEV_STATUSES or category not in DEV_CATEGORIES:
            flash("Enter a title, description, category and valid status.")
            return redirect("/admin/development")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO lfv_development_items
                (title, description, category, section_name, page_url, contact_email,
                 source, status, created_at, updated_at)
                VALUES (:title, :description, :category, :section_name, :page_url, '',
                        'Internal', :status, :now, :now)
            """), {"title": title, "description": description, "category": category,
                    "section_name": request.form.get("section_name", "").strip()[:80],
                    "page_url": request.form.get("page_url", "").strip()[:500],
                    "status": status, "now": now})
        flash("Development item added.")
        return redirect("/admin/development")

    app.add_url_rule("/admin/development/new", "lfv_development_create",
                     _development_create, methods=["POST"])

    def _development_update(item_id):
        guard = _require_admin()
        if guard:
            return guard
        if not _valid_csrf():
            abort(400)
        _development_table()
        status = request.form.get("status", "")
        if status not in DEV_STATUSES:
            abort(400)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE lfv_development_items
                SET status = :status, updated_at = :updated_at
                WHERE id = :item_id
            """), {"status": status, "updated_at": now, "item_id": item_id})
        flash("Development status updated.")
        return redirect("/admin/development?" + urlencode({
            "status": request.form.get("current_filter", "All"),
            "page": request.form.get("page", "1")
        }))

    app.add_url_rule("/admin/development/<int:item_id>/status", "lfv_development_update",
                     _development_update, methods=["POST"])

    def _feedback_form():
        _development_table()
        if request.method == "GET":
            return render_template("development_feedback.html", csrf_token=_csrf_token(),
                                   submitted=False)
        if not _valid_csrf():
            abort(400)
        if request.form.get("website", "").strip():
            # Honeypot: respond without storing spam.
            return render_template("development_feedback.html", csrf_token=_csrf_token(),
                                   submitted=True)
        title = request.form.get("title", "").strip()[:140]
        message = request.form.get("description", "").strip()[:4000]
        category = request.form.get("category", "Other")
        email = request.form.get("email", "").strip()[:254]
        page_url = request.form.get("page_url", "").strip()[:500]
        if len(title) < 3 or len(message) < 10 or category not in DEV_CATEGORIES:
            return render_template("development_feedback.html", csrf_token=_csrf_token(),
                                   submitted=False, error="Please enter a title and a short description."), 400
        if email and ("@" not in email or " " in email):
            return render_template("development_feedback.html", csrf_token=_csrf_token(),
                                   submitted=False, error="Please enter a valid contact email or leave it blank."), 400
        # Salt before storing a short-lived abuse-control key. Never show this to admins.
        raw_ip = (request.remote_addr or "")[:80]
        secret = str(app.secret_key or "")
        submitter_key = sha256((secret + "|" + raw_ip).encode()).hexdigest()[:32]
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
        recent = int(_scalar("""
            SELECT COUNT(*) FROM lfv_development_items
            WHERE submitter_key = :key AND created_at >= :since
        """, {"key": submitter_key, "since": since}) or 0)
        if recent >= 5:
            return render_template("development_feedback.html", csrf_token=_csrf_token(),
                                   submitted=False, error="Too many submissions. Please try again later."), 429
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO lfv_development_items
                (title, description, category, section_name, page_url, contact_email,
                 source, status, submitter_key, created_at, updated_at)
                VALUES (:title, :description, :category, 'Website',
                        :page_url, :email, 'Community', 'Needs Review', :submitter_key,
                        :created_at, :created_at)
            """), {"title": title, "description": message, "category": category,
                    "page_url": page_url, "email": email,
                    "submitter_key": submitter_key, "created_at": now})
        return render_template("development_feedback.html", csrf_token=_csrf_token(),
                               submitted=True)

    app.add_url_rule("/feedback/development", "lfv_development_feedback",
                     _feedback_form, methods=["GET", "POST"])

    @app.context_processor
    def _admin_v2_context():
        return {"lfv_admin_console_version": "v2"}
