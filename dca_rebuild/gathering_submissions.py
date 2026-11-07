"""Community gathering submissions: battles, labs, sessions, classes and more.

All user submissions are pending until reviewed by an administrator. No flyer
or account is required, and user contact details never appear on the calendar.
"""
from datetime import datetime, date
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import secrets

from flask import abort, redirect, render_template, request, session, url_for, flash
from dca_rebuild.models import VaultGatheringSubmission

GATHERING_TYPES = (
    ("battle", "BATTLE / COMPETITION"),
    ("lab", "LAB / SESSION"),
    ("link_up", "LINK-UP / MEET-UP"),
    ("workshop", "WORKSHOP"),
    ("class", "CLASS"),
    ("event", "EVENT / SHOWCASE"),
    ("community", "COMMUNITY GATHERING"),
    ("other", "OTHER"),
)
VALID_TYPES = {key for key, _ in GATHERING_TYPES}


def trim(form, name, length):
    return (form.get(name) or "").strip()[:length]


def parse_http_url(value):
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "http") or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("ENTER A VALID HTTP OR HTTPS LINK.")
    return value


def csrf_token():
    if "lfv_submit_csrf" not in session:
        session["lfv_submit_csrf"] = secrets.token_urlsafe(32)
    return session["lfv_submit_csrf"]


def install_gathering_submissions(app, ns):
    # Resolve the active session factory per request for isolated test databases.

    @app.route("/submit", methods=["GET", "POST"], endpoint="vault_submit")
    def submit():
        if request.method == "GET":
            return render_template("vault_submit.html", submission_types=GATHERING_TYPES, submit_csrf=csrf_token())

        if not secrets.compare_digest(str(session.get("lfv_submit_csrf", "")), str(request.form.get("csrf_token") or "")) or not session.get("lfv_submit_csrf"):
            abort(400)
        if request.form.get("website"):  # Bot honeypot: appears empty to humans.
            abort(400)
        if request.content_length and request.content_length > 24_000:
            abort(413)

        title = trim(request.form, "title", 240)
        kind = trim(request.form, "gathering_type", 40)
        day = trim(request.form, "start_date", 10)
        end_day = trim(request.form, "end_date", 10)
        start = trim(request.form, "start_time", 5)
        end = trim(request.form, "end_time", 5)
        email = trim(request.form, "contact_email", 255).lower()
        try:
            parsed_day = date.fromisoformat(day)
            if parsed_day < datetime.now(ZoneInfo("America/New_York")).date():
                raise ValueError("PLEASE ENTER A CURRENT OR FUTURE DATE.")
            if end_day and date.fromisoformat(end_day) < parsed_day:
                raise ValueError("THE END DATE CANNOT PRECEDE THE START DATE.")
            for time_text in (start, end):
                if time_text:
                    datetime.strptime(time_text, "%H:%M")
            link = parse_http_url(trim(request.form, "link", 1200))
            if not title or len(title) < 3 or kind not in VALID_TYPES:
                raise ValueError("ADD A NAME AND SELECT THE TYPE OF GATHERING.")
            if email and ("@" not in email or "." not in email.split("@")[-1]):
                raise ValueError("ENTER A VALID EMAIL OR LEAVE IT BLANK.")
        except (ValueError, TypeError) as exc:
            flash(str(exc) if str(exc) else "CHECK YOUR SUBMISSION DETAILS.")
            return redirect(url_for("vault_submit"))

        with ns["SessionLocal"].begin() as db:
            db.add(VaultGatheringSubmission(
                title=title,
                gathering_type=kind,
                description=trim(request.form, "description", 3000) or None,
                start_date=day,
                end_date=end_day or None,
                start_time=start or None,
                end_time=end or None,
                venue=trim(request.form, "venue", 240) or None,
                address=trim(request.form, "address", 350) or None,
                city=trim(request.form, "city", 120) or None,
                virtual=bool(request.form.get("virtual")),
                link=link or None,
                hosts=trim(request.form, "hosts", 400) or None,
                admission=trim(request.form, "admission", 160) or None,
                contact_name=trim(request.form, "contact_name", 160) or None,
                contact_email=email or None,
                additional_notes=trim(request.form, "additional_notes", 2000) or None,
                status="pending",
            ))
        session.pop("lfv_submit_csrf", None)
        return redirect(url_for("vault_submit_success"), code=303)

    @app.get("/submit/thank-you", endpoint="vault_submit_success")
    def success():
        return render_template("vault_submit_success.html")

    @app.get("/admin/gatherings", endpoint="admin_vault_gatherings")
    @ns["admin_login_required"]
    def admin_gatherings():
        with ns["SessionLocal"]() as db:
            submissions = db.query(VaultGatheringSubmission).order_by(
                VaultGatheringSubmission.created_at.desc(),
                VaultGatheringSubmission.id.desc()).limit(200).all()
            items = [
                dict(id=x.id, title=x.title, gathering_type=x.gathering_type,
                     date=x.start_date, end_date=x.end_date, time=x.start_time,
                     venue=x.venue, city=x.city, hosts=x.hosts, admission=x.admission,
                     link=x.link, description=x.description, notes=x.additional_notes,
                     contact=x.contact_email, status=x.status)
                for x in submissions
            ]
        return render_template("admin_vault_gatherings.html", submissions=items,
                               moderation_csrf=admin_csrf())

    def admin_csrf():
        if "lfv_gathering_admin_csrf" not in session:
            session["lfv_gathering_admin_csrf"] = secrets.token_urlsafe(32)
        return session["lfv_gathering_admin_csrf"]

    @app.post("/admin/gatherings/<int:submission_id>/<decision>", endpoint="admin_vault_gathering_decision")
    @ns["admin_login_required"]
    def decide(submission_id, decision):
        token = session.get("lfv_gathering_admin_csrf")
        if not token or not secrets.compare_digest(token, request.form.get("csrf_token") or ""):
            abort(400)
        if decision not in {"approve", "reject"}:
            abort(400)
        with ns["SessionLocal"].begin() as db:
            item = db.get(VaultGatheringSubmission, submission_id)
            if item is None:
                abort(404)
            item.status = "approved" if decision == "approve" else "rejected"
            item.reviewed_at = datetime.utcnow()
        flash("SUBMISSION REVIEW UPDATED.")
        return redirect(url_for("admin_vault_gatherings"), code=303)
