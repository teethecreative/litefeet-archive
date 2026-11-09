"""Private community interest sign-ups for a proposed LiteFeet record attempt."""
from datetime import datetime, timedelta
import re
import secrets

from flask import abort, redirect, render_template, request, session, url_for
from dca_rebuild.models import WorldRecordInterest

ROLES = (
    ("dancer", "Participate as a dancer"),
    ("choreography", "Help develop the choreography"),
    ("captain", "Become a rehearsal captain"),
    ("space", "Provide a rehearsal space"),
    ("volunteer", "Volunteer, support or partner"),
)
ROLE_VALUES = {role for role, _ in ROLES}
FOLLOW_UP_STATES = {"interested", "contacted", "planning", "inactive"}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _field(name, limit):
    return (request.form.get(name) or "").strip()[:limit]


def _form_token():
    if "vault_world_record_csrf" not in session:
        session["vault_world_record_csrf"] = secrets.token_urlsafe(32)
    return session["vault_world_record_csrf"]


def install_world_record(app, ns):
    @app.route("/world-record", methods=["GET", "POST"], endpoint="vault_world_record")
    def world_record():
        token = _form_token()
        if request.method == "GET":
            return render_template("world_record.html", roles=ROLES, token=token, error=None, values={})
        if request.content_length and request.content_length > 16000:
            abort(413)
        if not secrets.compare_digest(token, request.form.get("csrf_token", "")):
            abort(400)
        if request.form.get("website", ""):
            abort(400)

        role = _field("role", 32)
        name = _field("contact_name", 160)
        email = _field("email", 320).lower()
        guardian = request.form.get("guardian_submission") == "yes"
        contact = request.form.get("contact_permission") == "yes"
        age_confirmed = request.form.get("adult_or_guardian") == "yes"
        error = None
        if role not in ROLE_VALUES:
            error = "Choose how you would like to help."
        elif len(name) < 2 or not EMAIL_RE.fullmatch(email):
            error = "Enter a contact name and a valid email address."
        elif not age_confirmed:
            error = "This form must be completed by an adult or the parent/guardian of a minor."
        elif not contact:
            error = "Please confirm we may contact you about this specific initiative."
        if error:
            return render_template("world_record.html", roles=ROLES, token=token, error=error, values=request.form), 400

        # Limit repeated submissions in this browser without blocking separate roles.
        last = session.get("vault_world_record_last_at")
        if last:
            try:
                if (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds() < 20:
                    return redirect(url_for("vault_world_record_thanks"), code=303)
            except ValueError:
                pass
        with ns["SessionLocal"].begin() as db:
            recent = db.query(WorldRecordInterest.id).filter(
                WorldRecordInterest.email == email,
                WorldRecordInterest.role == role,
                WorldRecordInterest.created_at >= datetime.utcnow() - timedelta(hours=24),
            ).first()
            if not recent:
                db.add(WorldRecordInterest(
                    contact_name=name, email=email, role=role,
                    dance_name=_field("dance_name", 160) or None,
                    team=_field("team", 160) or None,
                    borough=_field("borough", 120) or None,
                    experience=_field("experience", 1200) or None,
                    venue_name=_field("venue_name", 200) or None,
                    venue_capacity=_field("venue_capacity", 80) or None,
                    availability=_field("availability", 300) or None,
                    notes=_field("notes", 1500) or None,
                    guardian_submission=guardian,
                    contact_permission=contact,
                    status="interested",
                ))
        session["vault_world_record_last_at"] = datetime.utcnow().isoformat()
        session.pop("vault_world_record_csrf", None)
        return redirect(url_for("vault_world_record_thanks"), code=303)

    @app.get("/world-record/thanks", endpoint="vault_world_record_thanks")
    def world_record_thanks():
        return render_template("world_record_thanks.html")

    @app.get("/admin/world-record", endpoint="admin_world_record")
    @ns["admin_login_required"]
    def admin_world_record():
        selected_role = request.args.get("role", "")
        if selected_role not in ROLE_VALUES:
            selected_role = ""
        with ns["SessionLocal"]() as db:
            query = db.query(WorldRecordInterest)
            if selected_role:
                query = query.filter_by(role=selected_role)
            entries = query.order_by(WorldRecordInterest.created_at.desc(), WorldRecordInterest.id.desc()).limit(100).all()
            rows = [dict(id=item.id, name=item.contact_name, email=item.email, role=item.role,
                         dance_name=item.dance_name, team=item.team, borough=item.borough,
                         experience=item.experience, venue=item.venue_name, capacity=item.venue_capacity,
                         availability=item.availability, notes=item.notes, status=item.status,
                         guardian=item.guardian_submission, created=item.created_at)
                    for item in entries]
            counts = dict(db.query(WorldRecordInterest.role, __import__("sqlalchemy").func.count(WorldRecordInterest.id)).group_by(WorldRecordInterest.role).all())
            total = db.query(WorldRecordInterest.id).count()
        if "vault_world_admin_csrf" not in session:
            session["vault_world_admin_csrf"] = secrets.token_urlsafe(32)
        return render_template("admin_world_record.html", rows=rows, roles=ROLES,
                               selected_role=selected_role, total=total, counts=counts,
                               csrf_token=session["vault_world_admin_csrf"])

    @app.post("/admin/world-record/<int:interest_id>/status", endpoint="admin_world_record_status")
    @ns["admin_login_required"]
    def admin_world_record_status(interest_id):
        expected = session.get("vault_world_admin_csrf", "")
        if not expected or not secrets.compare_digest(expected, request.form.get("csrf_token", "")):
            abort(400)
        new_status = request.form.get("status", "")
        if new_status not in FOLLOW_UP_STATES:
            abort(400)
        with ns["SessionLocal"].begin() as db:
            record = db.get(WorldRecordInterest, interest_id)
            if record is None:
                abort(404)
            record.status = new_status
        return redirect(url_for("admin_world_record", role=request.form.get("role_filter", "")), code=303)
