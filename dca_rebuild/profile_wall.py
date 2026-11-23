"""Public profile Walls: publish only after one authorized review.

A verified email proves mailbox control, not ownership of a dancer identity.
Only a Vault administrator may link a verified mailbox to a public profile.
Moderation is first-decision-wins, with an append-only decision trail and an
explicit, separate admin override path.
"""
from datetime import datetime, timedelta
import re
import secrets

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from dca_rebuild.models import Base


class VaultProfileWallPost(Base):
    __tablename__ = "vault_profile_wall_posts"
    id = Column(Integer, primary_key=True)
    profile_href = Column(String(280), nullable=False, index=True)
    author_name = Column(String(80), nullable=False)
    author_hash = Column(String(64), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="pending", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(24), nullable=True)
    resolver_hash = Column(String(64), nullable=True)


class VaultProfileWallDecision(Base):
    """Never delete earlier actions when an administrator overrides a decision."""
    __tablename__ = "vault_profile_wall_decisions"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("vault_profile_wall_posts.id"), nullable=False, index=True)
    action = Column(String(24), nullable=False)
    actor = Column(String(24), nullable=False)
    actor_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class VaultProfileWallOwner(Base):
    """Explicit approved moderation link; only one current owner per profile."""
    __tablename__ = "vault_profile_wall_owners"
    id = Column(Integer, primary_key=True)
    profile_href = Column(String(280), nullable=False, unique=True, index=True)
    verified_email_hash = Column(String(64), nullable=False, index=True)
    masked_email = Column(String(254), nullable=False)
    assigned_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)


class VaultProfileWallOwnerAudit(Base):
    __tablename__ = "vault_profile_wall_owner_audit"
    id = Column(Integer, primary_key=True)
    profile_href = Column(String(280), nullable=False, index=True)
    action = Column(String(20), nullable=False)
    masked_email = Column(String(254), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


def _verified_hash():
    from dca_rebuild.email_verification import verified_nominator_hash
    return verified_nominator_hash()


def _csrf():
    return session.setdefault("vault_profile_wall_csrf", secrets.token_urlsafe(32))


def _require_csrf():
    expected = session.get("vault_profile_wall_csrf", "")
    supplied = request.form.get("csrf_token", "")
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        abort(400, "The form expired. Refresh the page and try again.")


def _owner_for(db, path, who):
    return bool(who and db.query(VaultProfileWallOwner).filter(
        VaultProfileWallOwner.profile_href == path,
        VaultProfileWallOwner.verified_email_hash == who,
        VaultProfileWallOwner.revoked_at.is_(None),
    ).first())


def _profile_for_path(path, session_factory):
    """Resolve only a published, existing profile; never accept arbitrary URLs."""
    if not isinstance(path, str) or len(path) > 280:
        return None
    from dca_rebuild.public_profiles import profile_index
    from dca_rebuild.archive_catalog import all_records
    from dca_rebuild.public_urls import person_by_slug
    from dca_rebuild.archive_catalog import find_record
    profiles = profile_index(session_factory)
    if path.startswith("/people/") and path.count("/") == 2:
        slug = path.removeprefix("/people/")
        record = person_by_slug(slug, all_records())
        profile = profiles.for_archive_record(record["slug"]) if record else profiles.by_slug(slug)
    elif path.startswith("/archive/records/") and path.count("/") == 3:
        slug = path.removeprefix("/archive/records/")
        record = find_record(slug)
        profile = profiles.for_archive_record(slug) if record and record.get("collection") == "people" else None
    else:
        profile = None
    if not profile or profile["href"] != path:
        return None
    return profile


def _mask_email(email):
    local, domain = email.split("@", 1)
    return local[:2] + "***@" + domain


def _decide(db, post, decision, actor, actor_hash=None, override=False):
    """Single atomic UPDATE from pending; a losing concurrent reviewer cannot decide.

    An admin override explicitly targets the previous resolved state. Each
    successful action is logged; the old owner's resolution is not erased.
    """
    if decision not in ("approved", "rejected") or actor not in ("administrator", "profile owner"):
        raise ValueError("Unsupported decision")
    if override and actor != "administrator":
        raise PermissionError("Only an administrator can override a Wall decision")
    if override and post.status == "pending":
        return False
    old_status = post.status
    old_actor = post.resolved_by
    old_at = post.resolved_at
    if not override and old_status != "pending":
        return False
    now = datetime.utcnow()
    q = db.query(VaultProfileWallPost).filter(VaultProfileWallPost.id == post.id)
    if override:
        q = q.filter(VaultProfileWallPost.status == old_status,
                     VaultProfileWallPost.resolved_by == old_actor,
                     VaultProfileWallPost.resolved_at == old_at)
    else:
        q = q.filter(VaultProfileWallPost.status == "pending")
    changed = q.update({
        VaultProfileWallPost.status: decision,
        VaultProfileWallPost.resolved_at: now,
        VaultProfileWallPost.resolved_by: actor,
        VaultProfileWallPost.resolver_hash: actor_hash if actor == "profile owner" else None,
    }, synchronize_session=False)
    if changed != 1:
        return False
    db.add(VaultProfileWallDecision(
        post_id=post.id, action=("override_" if override else "") + decision,
        actor=actor, actor_hash=actor_hash if actor == "profile owner" else None,
        created_at=now,
    ))
    return True


def install_profile_wall(app, session_factory, private_hash, admin_required):
    """Register profile Wall data, public submissions and two independent review UIs."""
    bind = session_factory.kw["bind"]
    Base.metadata.create_all(bind=bind, tables=[
        VaultProfileWallPost.__table__, VaultProfileWallDecision.__table__,
        VaultProfileWallOwner.__table__, VaultProfileWallOwnerAudit.__table__,
    ])

    @app.context_processor
    def wall_context():
        def wall_view(profile):
            path = profile["href"]
            who = _verified_hash()
            admin = bool(session.get("ledger_admin_authenticated"))
            with session_factory() as db:
                approved = db.query(VaultProfileWallPost).filter_by(
                    profile_href=path, status="approved").order_by(
                    VaultProfileWallPost.resolved_at.desc(),
                    VaultProfileWallPost.id.desc()).limit(8).all()
                owner = _owner_for(db, path, who)
                pending = db.query(VaultProfileWallPost).filter_by(
                    profile_href=path, status="pending").count() if (owner or admin) else 0
                # Render data as plain dicts so it survives session closure.
                posts = [dict(author_name=p.author_name, message=p.message,
                              created_at=p.created_at) for p in approved]
            return dict(posts=posts, csrf=_csrf(), can_post=bool(who or admin),
                        can_moderate=bool(owner or admin), is_admin=admin,
                        pending=pending)
        return {"vault_wall_view": wall_view}

    @app.post("/profile-wall/post", endpoint="vault_wall_post")
    def wall_post():
        if request.content_length and request.content_length > 10000:
            abort(413)
        _require_csrf()
        who = _verified_hash()
        is_admin = bool(session.get("ledger_admin_authenticated"))
        if not who and not is_admin:
            abort(403, "Verify your email before posting.")
        path = (request.form.get("profile_href") or "").strip()
        if _profile_for_path(path, session_factory) is None:
            abort(404)
        name = " ".join((request.form.get("author_name") or "").split())
        message = (request.form.get("message") or "").strip()
        if not 2 <= len(name) <= 80 or not 5 <= len(message) <= 2000:
            abort(400, "Enter a display name and a message of 5–2000 characters.")
        if request.form.get("website"):
            abort(400)
        now = datetime.utcnow()
        last = session.get("vault_wall_last_post")
        if last:
            try:
                if (now - datetime.fromisoformat(last)).total_seconds() < 60:
                    abort(429, "Please wait a minute before posting again.")
            except ValueError:
                pass
        with session_factory.begin() as db:
            db.add(VaultProfileWallPost(
                profile_href=path, author_name=name, message=message,
                author_hash=who if who else "administrator", status="pending",
                created_at=now))
        session["vault_wall_last_post"] = now.isoformat()
        flash("Your Wall post was submitted for approval.", "wall")
        return redirect(path + "#wall", code=303)

    @app.get("/my/profile-walls", endpoint="vault_wall_owner_queue")
    def owner_queue():
        who = _verified_hash()
        if not who:
            return redirect(url_for("dca_verify_email") if "dca_verify_email" in app.view_functions
                            else url_for("dca_nominations_closed"))
        with session_factory() as db:
            owners = db.query(VaultProfileWallOwner).filter(
                VaultProfileWallOwner.verified_email_hash == who,
                VaultProfileWallOwner.revoked_at.is_(None)).all()
            paths = [x.profile_href for x in owners]
            posts = db.query(VaultProfileWallPost).filter(
                VaultProfileWallPost.profile_href.in_(paths),
                VaultProfileWallPost.status == "pending").order_by(
                VaultProfileWallPost.created_at.asc()).limit(100).all() if paths else []
            posts = [dict(id=p.id, profile_href=p.profile_href, author_name=p.author_name,
                          message=p.message, created_at=p.created_at) for p in posts]
        return render_template("profile_wall_owner_queue.html",
                               paths=paths, posts=posts, csrf_token=_csrf())

    @app.post("/profile-wall/<int:post_id>/review", endpoint="vault_wall_review")
    def wall_review(post_id):
        _require_csrf()
        decision = (request.form.get("decision") or "").strip()
        if decision not in ("approved", "rejected"):
            abort(400)
        is_admin = bool(session.get("ledger_admin_authenticated"))
        who = _verified_hash() if not is_admin else None
        if not is_admin and not who:
            abort(403)
        with session_factory.begin() as db:
            post = db.get(VaultProfileWallPost, post_id)
            if not post:
                abort(404)
            if not is_admin and not _owner_for(db, post.profile_href, who):
                abort(403)
            ok = _decide(db, post, decision,
                         "administrator" if is_admin else "profile owner", who)
        flash("Wall post " + (decision if ok else "was already resolved by another reviewer") + ".", "wall")
        return redirect(url_for("admin_profile_walls") if is_admin
                        else url_for("vault_wall_owner_queue"), code=303)

    @app.get("/admin/profile-walls", endpoint="admin_profile_walls")
    @admin_required
    def admin_walls():
        view = request.args.get("view", "all")
        if view not in ("all", "pending", "resolved"):
            abort(400)
        with session_factory() as db:
            q = db.query(VaultProfileWallPost)
            if view == "pending":
                q = q.filter(VaultProfileWallPost.status == "pending")
            elif view == "resolved":
                q = q.filter(VaultProfileWallPost.status != "pending")
            rows = q.order_by(VaultProfileWallPost.created_at.desc(),
                              VaultProfileWallPost.id.desc()).limit(150).all()
            ids = [p.id for p in rows]
            logs = db.query(VaultProfileWallDecision).filter(
                VaultProfileWallDecision.post_id.in_(ids)).order_by(
                VaultProfileWallDecision.created_at.asc(),
                VaultProfileWallDecision.id.asc()).all() if ids else []
            log_by_id = {i: [] for i in ids}
            for event in logs:
                log_by_id[event.post_id].append(dict(
                    action=event.action, actor=event.actor, created_at=event.created_at))
            posts = [dict(id=p.id, profile_href=p.profile_href, author_name=p.author_name,
                          message=p.message, status=p.status, created_at=p.created_at,
                          resolved_at=p.resolved_at, resolved_by=p.resolved_by,
                          history=log_by_id[p.id]) for p in rows]
            grants = db.query(VaultProfileWallOwner).filter(
                VaultProfileWallOwner.revoked_at.is_(None)).order_by(
                VaultProfileWallOwner.profile_href.asc()).all()
            grants = [dict(profile_href=g.profile_href, masked_email=g.masked_email,
                           assigned_at=g.assigned_at) for g in grants]
        return render_template("admin_profile_walls.html", posts=posts,
                               grants=grants, view=view, csrf_token=_csrf())

    @app.post("/admin/profile-walls/<int:post_id>/override",
              endpoint="admin_wall_override")
    @admin_required
    def admin_override(post_id):
        _require_csrf()
        decision = request.form.get("decision")
        if decision not in ("approved", "rejected"):
            abort(400)
        with session_factory.begin() as db:
            post = db.get(VaultProfileWallPost, post_id)
            if post is None:
                abort(404)
            ok = _decide(db, post, decision, "administrator", override=True)
        flash("Admin override recorded." if ok else "This post is pending or was changed. Refresh and try again.", "wall")
        return redirect(url_for("admin_profile_walls", view="resolved"), code=303)

    @app.post("/admin/profile-walls/owner-access", endpoint="admin_wall_owner_access")
    @admin_required
    def grant_owner():
        _require_csrf()
        action = request.form.get("action", "grant")
        if action not in ("grant", "revoke"):
            abort(400)
        path = (request.form.get("profile_href") or "").strip()
        if _profile_for_path(path, session_factory) is None:
            abort(404, "Link an existing published profile.")
        email = (request.form.get("owner_email") or "").strip().casefold()
        if action == "grant" and (
            len(email) > 254 or
            not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
            abort(400, "Enter the owner's verified email address.")
        now = datetime.utcnow()
        with session_factory.begin() as db:
            existing = db.query(VaultProfileWallOwner).filter_by(profile_href=path).first()
            if action == "revoke":
                if existing and existing.revoked_at is None:
                    existing.revoked_at = now
                    db.add(VaultProfileWallOwnerAudit(
                        profile_href=path, action="revoked", masked_email=existing.masked_email,
                        created_at=now))
            else:
                label = _mask_email(email)
                hash_value = private_hash("dca-nomination:" + email)
                if existing:
                    existing.verified_email_hash = hash_value
                    existing.masked_email = label
                    existing.assigned_at = now
                    existing.revoked_at = None
                else:
                    db.add(VaultProfileWallOwner(
                        profile_href=path, verified_email_hash=hash_value,
                        masked_email=label, assigned_at=now))
                db.add(VaultProfileWallOwnerAudit(
                    profile_href=path, action="granted", masked_email=label,
                    created_at=now))
        flash("Wall owner access updated.", "wall")
        return redirect(url_for("admin_profile_walls"), code=303)
