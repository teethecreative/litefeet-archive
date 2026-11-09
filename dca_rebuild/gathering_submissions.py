"""Community gathering submissions: battles, labs, sessions, classes and more.

All user submissions are pending until reviewed by an administrator. No flyer
or account is required, and user contact details never appear on the calendar.
"""
from datetime import datetime, date, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import secrets

from flask import abort, redirect, render_template, request, session, url_for, flash
from sqlalchemy import or_, func
from dca_rebuild.models import VaultGatheringSubmission, VaultGatheringReviewHistory, VaultGatheringOccurrenceOverride

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
RECURRENCE_CHOICES = (("none", "Does not repeat"), ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly"), ("yearly", "Yearly"))
VALID_RECURRENCE = {key for key, _ in RECURRENCE_CHOICES}


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
            return render_template("vault_submit.html", submission_types=GATHERING_TYPES, recurrence_choices=RECURRENCE_CHOICES, submit_csrf=csrf_token())

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
        hosts = trim(request.form, "hosts", 400)
        address = trim(request.form, "address", 350)
        is_virtual = bool(request.form.get("virtual"))
        repeat = trim(request.form, "recurrence_rule", 16) or "none"
        weekday_values = request.form.getlist("recurrence_weekdays")
        repeat_until = trim(request.form, "recurrence_until", 10)
        try:
            parsed_day = date.fromisoformat(day)
            if parsed_day < datetime.now(ZoneInfo("America/New_York")).date():
                raise ValueError("PLEASE ENTER A CURRENT OR FUTURE DATE.")
            if repeat not in VALID_RECURRENCE:
                raise ValueError("SELECT A VALID REPEAT SCHEDULE.")
            if repeat != "none" and end_day:
                raise ValueError("FOR REPEATING EVENTS, USE REPEAT UNTIL INSTEAD OF END DATE.")
            if repeat_until:
                until = date.fromisoformat(repeat_until)
                if repeat == "none":
                    raise ValueError("REPEAT UNTIL REQUIRES A REPEATING EVENT.")
                if until < parsed_day:
                    raise ValueError("REPEAT UNTIL CANNOT PRECEDE THE FIRST EVENT.")
            if any(day not in {str(i) for i in range(7)} for day in weekday_values):
                raise ValueError("SELECT VALID RECURRING DAYS.")
            if repeat == "weekly" and not weekday_values:
                weekday_values = [str(parsed_day.weekday())]
            if repeat != "weekly" and weekday_values:
                raise ValueError("RECURRING WEEKDAYS REQUIRE A WEEKLY SCHEDULE.")
            if repeat == "weekly" and str(parsed_day.weekday()) not in weekday_values:
                raise ValueError("FIRST DATE MUST MATCH ONE OF THE SELECTED WEEKDAYS.")
            if end_day and date.fromisoformat(end_day) < parsed_day:
                raise ValueError("THE END DATE CANNOT PRECEDE THE START DATE.")
            for time_text in (start, end):
                if time_text:
                    datetime.strptime(time_text, "%H:%M")
            link = parse_http_url(trim(request.form, "link", 1200))
            if not start or not end:
                raise ValueError("START AND END TIMES ARE REQUIRED.")
            if end <= start:
                raise ValueError("END TIME MUST BE AFTER START TIME.")
            if not hosts:
                raise ValueError("ENTER THE EVENT HOST OR ORGANIZER.")
            if not address:
                raise ValueError("ENTER A STREET ADDRESS OR, FOR A VIRTUAL EVENT, A MEETING LINK OR JOINING INSTRUCTIONS.")
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
                recurrence_rule=repeat,
                recurrence_weekdays=",".join(sorted(set(weekday_values), key=int)) if repeat == "weekly" else None,
                recurrence_until=repeat_until or None,
                start_time=start or None,
                end_time=end or None,
                venue=trim(request.form, "venue", 240) or None,
                address=address,
                city=trim(request.form, "city", 120) or None,
                virtual=is_virtual,
                link=link or None,
                hosts=hosts,
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

    def admin_csrf():
        if "lfv_gathering_admin_csrf" not in session:
            session["lfv_gathering_admin_csrf"] = secrets.token_urlsafe(32)
        return session["lfv_gathering_admin_csrf"]

    def verify_admin_csrf():
        token = session.get("lfv_gathering_admin_csrf")
        if not token or not secrets.compare_digest(str(token), str(request.form.get("csrf_token") or "")):
            abort(400)

    def log_action(db, item, action, summary=""):
        db.add(VaultGatheringReviewHistory(
            submission_id=item.id, action=action, change_summary=summary[:2000]))

    def nearby_duplicate_ids(db, item):
        # Flag for human review; never automatically merge or delete records.
        if not item.start_date or not item.title:
            return []
        rows = db.query(VaultGatheringSubmission).filter(
            VaultGatheringSubmission.id != item.id,
            VaultGatheringSubmission.start_date == item.start_date,
            VaultGatheringSubmission.status != "rejected",
        ).all()
        key = " ".join(item.title.casefold().split())
        return [row.id for row in rows if " ".join(row.title.casefold().split()) == key]

    def admin_form_fields(form, existing):
        """Validate every editable public field before committing any changes."""
        values = {
            "title": trim(form, "title", 240),
            "gathering_type": trim(form, "gathering_type", 40),
            "description": trim(form, "description", 3000) or None,
            "start_date": trim(form, "start_date", 10),
            "end_date": trim(form, "end_date", 10) or None,
            "start_time": trim(form, "start_time", 5),
            "end_time": trim(form, "end_time", 5),
            "recurrence_rule": trim(form, "recurrence_rule", 16) or "none",
            "recurrence_until": trim(form, "recurrence_until", 10) or None,
            "venue": trim(form, "venue", 240) or None,
            "address": trim(form, "address", 350),
            "city": trim(form, "city", 120) or None,
            "virtual": bool(form.get("virtual")),
            "hosts": trim(form, "hosts", 400),
            "admission": trim(form, "admission", 160) or None,
            "link": parse_http_url(trim(form, "link", 1200)) or None,
            "contact_name": trim(form, "contact_name", 160) or None,
            "contact_email": trim(form, "contact_email", 255).lower() or None,
            "additional_notes": trim(form, "additional_notes", 2000) or None,
        }
        if not values["title"] or len(values["title"]) < 3:
            raise ValueError("Event title must be at least three characters.")
        if values["gathering_type"] not in VALID_TYPES:
            raise ValueError("Choose a valid event type.")
        day = date.fromisoformat(values["start_date"])
        if values["end_date"] and date.fromisoformat(values["end_date"]) < day:
            raise ValueError("End date must not precede start date.")
        if values["recurrence_rule"] not in VALID_RECURRENCE:
            raise ValueError("Choose a valid repeat schedule.")
        if values["recurrence_rule"] != "none" and values["end_date"]:
            raise ValueError("Use Repeat Until instead of End Date for repeating events.")
        if values["recurrence_until"] and (values["recurrence_rule"] == "none" or date.fromisoformat(values["recurrence_until"]) < day):
            raise ValueError("Repeat Until must be on or after the start of a repeating event.")
        if not values["start_time"] or not values["end_time"]:
            raise ValueError("Start and end times are required.")
        for key in ("start_time", "end_time"):
            datetime.strptime(values[key], "%H:%M")
        if values["end_time"] <= values["start_time"]:
            raise ValueError("End time must be after start time.")
        if not values["hosts"] or not values["address"]:
            raise ValueError("Host and street address or virtual joining instructions are required.")
        if values["contact_email"] and ("@" not in values["contact_email"] or "." not in values["contact_email"].split("@")[-1]):
            raise ValueError("Enter a valid email or leave it empty.")
        days = form.getlist("recurrence_weekdays")
        if any(d not in {str(i) for i in range(7)} for d in days):
            raise ValueError("Invalid repeat weekdays.")
        if values["recurrence_rule"] == "weekly":
            if not days:
                days = [str(day.weekday())]
            if str(day.weekday()) not in days:
                raise ValueError("Start date must match one of the repeat weekdays.")
            values["recurrence_weekdays"] = ",".join(sorted(set(days), key=int))
        else:
            if days:
                raise ValueError("Weekday selections require a weekly repeat schedule.")
            values["recurrence_weekdays"] = None
        return values

    @app.get("/admin/gatherings", endpoint="admin_vault_gatherings")
    @ns["admin_login_required"]
    def admin_gatherings():
        status = (request.args.get("status") or "all").lower()
        kind = (request.args.get("type") or "all").lower()
        q = (request.args.get("q") or "").strip()[:120]
        if status not in {"all", "pending", "approved", "rejected", "unpublished"}:
            abort(400)
        if kind != "all" and kind not in VALID_TYPES:
            abort(400)
        try:
            page = int(request.args.get("page", 1))
            if page < 1:
                raise ValueError()
        except (TypeError, ValueError):
            abort(400)
        per_page = 20
        with ns["SessionLocal"]() as db:
            query = db.query(VaultGatheringSubmission)
            if status != "all":
                query = query.filter(VaultGatheringSubmission.status == status)
            if kind != "all":
                query = query.filter(VaultGatheringSubmission.gathering_type == kind)
            if q:
                pattern = "%" + q.replace("%", r"\%").replace("_", r"\_") + "%"
                query = query.filter(or_(
                    VaultGatheringSubmission.title.ilike(pattern, escape="\\"),
                    VaultGatheringSubmission.hosts.ilike(pattern, escape="\\"),
                ))
            total = query.count()
            rows = query.order_by(
                VaultGatheringSubmission.created_at.asc(),
                VaultGatheringSubmission.id.asc()
            ).offset((page - 1) * per_page).limit(per_page).all()
            submissions = [
                dict(id=x.id, title=x.title, gathering_type=x.gathering_type,
                     date=x.start_date, end_date=x.end_date,
                     start_time=x.start_time, end_time=x.end_time,
                     hosts=x.hosts, venue=x.venue, virtual=x.virtual,
                     status=x.status, received=x.created_at,
                     duplicate_ids=nearby_duplicate_ids(db, x))
                for x in rows
            ]
            status_counts = dict(db.query(
                VaultGatheringSubmission.status,
                func.count(VaultGatheringSubmission.id)
            ).group_by(VaultGatheringSubmission.status).all())
        return render_template(
            "admin_vault_gatherings.html", submissions=submissions,
            moderation_csrf=admin_csrf(), status_counts=status_counts,
            selected_status=status, selected_type=kind, search_term=q,
            submission_types=GATHERING_TYPES, page=page, total=total,
            per_page=per_page, pages=(total + per_page - 1) // per_page)

    @app.route("/admin/gatherings/<int:submission_id>", methods=["GET", "POST"],
               endpoint="admin_vault_gathering_edit")
    @ns["admin_login_required"]
    def admin_edit(submission_id):
        if request.method == "POST":
            verify_admin_csrf()
            try:
                with ns["SessionLocal"].begin() as db:
                    item = db.get(VaultGatheringSubmission, submission_id)
                    if item is None:
                        abort(404)
                    values = admin_form_fields(request.form, item)
                    changed = [key for key, value in values.items() if getattr(item, key) != value]
                    for key, value in values.items():
                        setattr(item, key, value)
                    if changed:
                        log_action(db, item, "edit", "Fields changed: " + ", ".join(changed))
            except (ValueError, TypeError) as exc:
                flash("Couldn't save: " + str(exc))
                return redirect(url_for("admin_vault_gathering_edit", submission_id=submission_id), code=303)
            flash("Event details saved.")
            return redirect(url_for("admin_vault_gathering_edit", submission_id=submission_id), code=303)
        with ns["SessionLocal"]() as db:
            item = db.get(VaultGatheringSubmission, submission_id)
            if item is None:
                abort(404)
            values = {name: getattr(item, name) for name in (
                "id", "title", "gathering_type", "description", "start_date", "end_date",
                "start_time", "end_time", "recurrence_rule", "recurrence_weekdays",
                "recurrence_until", "venue", "address", "city", "virtual", "hosts",
                "admission", "link", "contact_name", "contact_email",
                "additional_notes", "status", "created_at", "reviewed_at"
            )}
            duplicate_ids = nearby_duplicate_ids(db, item)
            history = db.query(VaultGatheringReviewHistory).filter_by(
                submission_id=submission_id).order_by(
                    VaultGatheringReviewHistory.created_at.desc(),
                    VaultGatheringReviewHistory.id.desc()).all()
            overrides = db.query(VaultGatheringOccurrenceOverride).filter_by(
                submission_id=submission_id).order_by(
                    VaultGatheringOccurrenceOverride.occurrence_date.asc()).all()
            history = [dict(action=h.action, summary=h.change_summary, at=h.created_at) for h in history]
            overrides = [dict(date=o.occurrence_date, reason=o.reason) for o in overrides if o.is_cancelled]
        return render_template(
            "admin_vault_gathering_edit.html", item=values, history=history,
            overrides=overrides, duplicate_ids=duplicate_ids,
            submission_types=GATHERING_TYPES, recurrence_choices=RECURRENCE_CHOICES,
            moderation_csrf=admin_csrf())

    @app.post("/admin/gatherings/<int:submission_id>/<decision>",
              endpoint="admin_vault_gathering_decision")
    @ns["admin_login_required"]
    def decide(submission_id, decision):
        verify_admin_csrf()
        status_for_action = {
            "approve": "approved",
            "reject": "rejected",
            "unpublish": "unpublished",
            "restore": "approved",
            "reconsider": "pending",
        }
        if decision not in status_for_action:
            abort(400)
        allowed_from = {
            "approve": {"pending", "rejected", "unpublished"},
            "reject": {"pending", "approved", "unpublished"},
            "unpublish": {"approved"},
            "restore": {"unpublished"},
            "reconsider": {"rejected", "unpublished"},
        }
        with ns["SessionLocal"].begin() as db:
            item = db.get(VaultGatheringSubmission, submission_id)
            if item is None:
                abort(404)
            if item.status not in allowed_from[decision]:
                abort(400)
            item.status = status_for_action[decision]
            item.reviewed_at = datetime.utcnow()
            log_action(db, item, decision, "Status set to " + item.status)
        flash("Event status updated.")
        return redirect(url_for("admin_vault_gathering_edit", submission_id=submission_id), code=303)

    @app.post("/admin/gatherings/<int:submission_id>/occurrences",
              endpoint="admin_vault_gathering_occurrence")
    @ns["admin_login_required"]
    def occurrence(submission_id):
        verify_admin_csrf()
        action = request.form.get("action") or ""
        if action not in {"cancel", "restore"}:
            abort(400)
        try:
            day = date.fromisoformat(request.form.get("date") or "")
        except ValueError:
            abort(400)
        with ns["SessionLocal"].begin() as db:
            item = db.get(VaultGatheringSubmission, submission_id)
            if item is None:
                abort(404)
            if item.recurrence_rule in (None, "none"):
                abort(400)
            first = date.fromisoformat(item.start_date)
            until = date.fromisoformat(item.recurrence_until) if item.recurrence_until else None
            if day < first or (until and day > until):
                abort(400)
            if item.recurrence_rule == "weekly":
                weekdays = {int(x) for x in (item.recurrence_weekdays or "").split(",") if x}
                if day.weekday() not in (weekdays or {first.weekday()}):
                    abort(400)
            elif item.recurrence_rule == "monthly" and day.day != first.day:
                abort(400)
            elif item.recurrence_rule == "yearly" and (day.month, day.day) != (first.month, first.day):
                abort(400)
            row = db.query(VaultGatheringOccurrenceOverride).filter_by(
                submission_id=item.id, occurrence_date=day.isoformat()).first()
            if action == "cancel":
                if row is None:
                    row = VaultGatheringOccurrenceOverride(
                        submission_id=item.id, occurrence_date=day.isoformat())
                    db.add(row)
                row.is_cancelled = True
                row.reason = trim(request.form, "reason", 500) or None
            elif row is not None:
                row.is_cancelled = False
            log_action(db, item, action + "_occurrence", day.isoformat())
        flash("Occurrence schedule updated.")
        return redirect(url_for("admin_vault_gathering_edit", submission_id=submission_id), code=303)
