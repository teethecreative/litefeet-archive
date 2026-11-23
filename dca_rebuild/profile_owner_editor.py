"""Owner-managed presentation for modern LiteFeet Vault public profiles.

Presentation is independent from the preserved archive and public award index.
Only verified, explicitly approved profile owners can propose changes. Nothing
goes public until an administrator approves a pending edit.
"""
from datetime import datetime
import json
import re
import secrets
from urllib.parse import urlsplit

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from dca_rebuild.models import Base
from dca_rebuild.email_verification import verified_nominator_hash
from dca_rebuild.profile_wall import VaultProfileWallOwner, _owner_for, _profile_for_path

FIELD_LIMITS = {
    "status_line": 140,
    "about_me": 1600,
    "dance_style": 360,
    "interests": 400,
    "influences": 400,
    "photo_url": 1200,
}
FIELDS = tuple(FIELD_LIMITS)


class VaultProfilePresentation(Base):
    __tablename__ = "vault_profile_presentations"
    id = Column(Integer, primary_key=True)
    profile_href = Column(String(280), nullable=False, unique=True, index=True)
    status_line = Column(String(140), nullable=False, default="")
    about_me = Column(Text, nullable=False, default="")
    dance_style = Column(Text, nullable=False, default="")
    interests = Column(Text, nullable=False, default="")
    influences = Column(Text, nullable=False, default="")
    photo_url = Column(String(1200), nullable=False, default="")
    featured_json = Column(Text, nullable=False, default="[]")
    approved_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class VaultProfileEditRequest(Base):
    __tablename__ = "vault_profile_edit_requests"
    id = Column(Integer, primary_key=True)
    profile_href = Column(String(280), nullable=False, index=True)
    claimant_hash = Column(String(64), nullable=False, index=True)
    proposed_json = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    admin_note = Column(Text, nullable=True)


class VaultProfileEditAudit(Base):
    __tablename__ = "vault_profile_edit_audit"
    id = Column(Integer, primary_key=True)
    edit_id = Column(Integer, ForeignKey("vault_profile_edit_requests.id"), nullable=False, index=True)
    action = Column(String(24), nullable=False)
    actor = Column(String(24), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


def _photo_url(value):
    """Only direct HTTPS image URLs, never script/data/blob/local URLs."""
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) > FIELD_LIMITS["photo_url"] or any(ord(c) < 32 for c in value):
        raise ValueError("Photo link is too long or contains invalid characters.")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or
            parsed.username or parsed.password or parsed.port is not None or
            not re.search(r"\.(?:png|jpe?g|webp|gif)$", parsed.path, re.I)):
        raise ValueError("Use a direct HTTPS image link ending in .jpg, .jpeg, .png, .webp, or .gif.")
    return value


def _clean_fields(data, path, resolve_profile):
    """Validate only presentation fields, never archives/awards/role data."""
    out = {}
    for name, max_len in FIELD_LIMITS.items():
        value = str(data.get(name) or "").strip()
        if len(value) > max_len:
            raise ValueError(name.replace("_", " ").title() + " is too long.")
        if any(ord(c) < 32 and c not in "\n\t\r" for c in value):
            raise ValueError("Unsupported characters in profile fields.")
        out[name] = value
    out["photo_url"] = _photo_url(out["photo_url"])

    featured = str(data.get("featured_connections") or "").strip()
    lines = [v.strip() for v in featured.splitlines() if v.strip()]
    if len(lines) > 8:
        raise ValueError("Choose no more than eight featured profiles.")
    if len(set(lines)) != len(lines):
        raise ValueError("Remove duplicate featured profiles.")
    for link in lines:
        if link == path or not link.startswith("/people/") and not link.startswith("/archive/records/"):
            raise ValueError("Featured connections must be other Vault profile paths.")
        if not resolve_profile(link):
            raise ValueError("One of the featured connections is not a published Vault profile.")
    out["featured_connections"] = lines
    return out


def _blank():
    return {**{name: "" for name in FIELDS}, "featured_connections": []}


def _published(db, path):
    entry = db.query(VaultProfilePresentation).filter_by(profile_href=path).first()
    if not entry:
        return _blank()
    value = {name: getattr(entry, name) or "" for name in FIELDS}
    try:
        value["featured_connections"] = json.loads(entry.featured_json or "[]")
    except (ValueError, TypeError):
        value["featured_connections"] = []
    return value


def _pending(db, path):
    return (db.query(VaultProfileEditRequest)
            .filter_by(profile_href=path, status="pending")
            .order_by(VaultProfileEditRequest.created_at.desc()).first())


def _csrf():
    return session.setdefault("vault_profile_editor_csrf", secrets.token_urlsafe(32))


def _require_csrf():
    expected = session.get("vault_profile_editor_csrf")
    given = request.form.get("csrf_token", "")
    if not expected or not given or not secrets.compare_digest(expected, given):
        abort(400, "This form expired. Reload the page.")


def _active_owner_paths(db, who):
    if not who:
        return []
    return [row.profile_href for row in db.query(VaultProfileWallOwner).filter(
        VaultProfileWallOwner.verified_email_hash == who,
        VaultProfileWallOwner.revoked_at.is_(None)).order_by(
        VaultProfileWallOwner.profile_href.asc()).all()]


def install_profile_owner_editor(app, session_factory, admin_required):
    bind = session_factory.kw["bind"]
    Base.metadata.create_all(bind=bind, tables=[
        VaultProfilePresentation.__table__, VaultProfileEditRequest.__table__,
        VaultProfileEditAudit.__table__,
    ])

    @app.context_processor
    def profile_presentation_context():
        def presentation_for(profile):
            path = profile["href"]
            with session_factory() as db:
                data = _published(db, path)
            # Never let stale or unrecognized paths become arbitrary links.
            links = []
            for href in data.pop("featured_connections", [])[:8]:
                if not isinstance(href, str):
                    continue
                related = _profile_for_path(href, session_factory)
                if related:
                    links.append({"href": href, "name": related["name"]})
            data["connections"] = links
            return data
        return {"vault_profile_presentation": presentation_for}

    @app.get("/my/profile", endpoint="vault_owner_profile_editor")
    def owner_editor():
        who = verified_nominator_hash()
        if not who:
            return redirect(url_for("dca_verify_email"), code=302)
        requested = (request.args.get("profile") or "").strip()
        with session_factory() as db:
            paths = _active_owner_paths(db, who)
            path = requested if requested else (paths[0] if paths else "")
            if requested and requested not in paths:
                abort(403, "You don't have editing access to that profile.")
            if not path:
                values, pending, last = _blank(), None, None
            else:
                values = _published(db, path)
                pending = _pending(db, path)
                last = (db.query(VaultProfileEditRequest)
                        .filter_by(profile_href=path, claimant_hash=who)
                        .order_by(VaultProfileEditRequest.id.desc()).first())
            pending_info = ({"created_at": pending.created_at,
                             "data": json.loads(pending.proposed_json)}
                            if pending else None)
            last_info = ({"status": last.status, "admin_note": last.admin_note,
                          "resolved_at": last.resolved_at} if last else None)
        names = []
        for href in paths:
            profile = _profile_for_path(href, session_factory)
            if profile:
                names.append({"href": href, "name": profile["name"]})
        return render_template("profile_owner_dashboard.html",
                               profiles=names, selected=path, fields=values,
                               pending=pending_info, last=last_info,
                               csrf_token=_csrf()), 200, {
                                   "Cache-Control": "private, no-store",
                                   "X-Robots-Tag": "noindex, nofollow",
                               }

    @app.post("/my/profile/edit", endpoint="vault_owner_profile_submit")
    def submit_profile_edit():
        if request.content_length and request.content_length > 16000:
            abort(413)
        _require_csrf()
        who = verified_nominator_hash()
        if not who:
            abort(403, "Verify your email before editing a profile.")
        path = (request.form.get("profile_href") or "").strip()
        if _profile_for_path(path, session_factory) is None:
            abort(404)
        with session_factory.begin() as db:
            if not _owner_for(db, path, who):
                abort(403, "Only the approved profile owner can edit this page.")
            if _pending(db, path):
                flash("Your previous edits are still awaiting review.", "profile-edit")
                return redirect(url_for("vault_owner_profile_editor", profile=path), code=303)
            try:
                data = _clean_fields(
                    request.form, path,
                    lambda target: _profile_for_path(target, session_factory),
                )
            except ValueError as exc:
                flash(str(exc), "profile-edit")
                return redirect(url_for("vault_owner_profile_editor", profile=path), code=303)
            if data == _published(db, path):
                flash("No changes to submit.", "profile-edit")
                return redirect(url_for("vault_owner_profile_editor", profile=path), code=303)
            entry = VaultProfileEditRequest(
                profile_href=path, claimant_hash=who,
                proposed_json=json.dumps(data, ensure_ascii=False),
                status="pending", created_at=datetime.utcnow(),
            )
            db.add(entry)
            db.flush()
            db.add(VaultProfileEditAudit(
                edit_id=entry.id, action="submitted", actor="profile owner"))
        flash("Profile edits submitted for admin approval. Your public page is unchanged until approved.", "profile-edit")
        return redirect(url_for("vault_owner_profile_editor", profile=path), code=303)

    @app.get("/admin/profile-edits", endpoint="admin_profile_edits")
    @admin_required
    def admin_profile_edits():
        view = request.args.get("view", "pending")
        if view not in ("pending", "approved", "rejected", "all"):
            abort(400)
        with session_factory() as db:
            query = db.query(VaultProfileEditRequest)
            if view != "all":
                query = query.filter_by(status=view)
            rows = query.order_by(VaultProfileEditRequest.created_at.desc(),
                                  VaultProfileEditRequest.id.desc()).limit(200).all()
            items = [dict(
                id=x.id, profile_href=x.profile_href, status=x.status,
                proposed=json.loads(x.proposed_json), created_at=x.created_at,
                resolved_at=x.resolved_at, admin_note=x.admin_note,
                current=_published(db, x.profile_href),
                owner_active=_owner_for(db, x.profile_href, x.claimant_hash),
            ) for x in rows]
        return render_template("admin_profile_edits.html",
                               edits=items, view=view, csrf_token=_csrf())

    @app.post("/admin/profile-edits/<int:edit_id>/decision",
              endpoint="admin_profile_edit_decision")
    @admin_required
    def admin_decide_profile_edit(edit_id):
        _require_csrf()
        action = request.form.get("decision")
        if action not in ("approved", "rejected"):
            abort(400)
        note = (request.form.get("admin_note") or "").strip()[:600]
        now = datetime.utcnow()
        with session_factory.begin() as db:
            entry = db.query(VaultProfileEditRequest).filter(
                VaultProfileEditRequest.id == edit_id).with_for_update().first()
            if entry is None:
                abort(404)
            if entry.status != "pending":
                flash("This edit has already been reviewed.", "profile-edit")
                return redirect(url_for("admin_profile_edits", view="all"), code=303)
            if action == "approved":
                if not _owner_for(db, entry.profile_href, entry.claimant_hash):
                    abort(403, "The claimant no longer has owner access.")
                if _profile_for_path(entry.profile_href, session_factory) is None:
                    abort(404, "The target profile is no longer public.")
                data = json.loads(entry.proposed_json)
                current = db.query(VaultProfilePresentation).filter_by(
                    profile_href=entry.profile_href).first()
                if not current:
                    current = VaultProfilePresentation(profile_href=entry.profile_href)
                    db.add(current)
                for key in FIELDS:
                    setattr(current, key, data[key])
                current.featured_json = json.dumps(data["featured_connections"])
                current.approved_at = now
            entry.status = action
            entry.resolved_at = now
            entry.admin_note = note or None
            db.add(VaultProfileEditAudit(
                edit_id=entry.id, action=action, actor="administrator", created_at=now))
        flash("Profile edit " + action + ".", "profile-edit")
        return redirect(url_for("admin_profile_edits"), code=303)
