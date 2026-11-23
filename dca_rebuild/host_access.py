"""Invite-only host accounts and two source-grouped battle-result workspaces."""
from datetime import datetime, timedelta
import hashlib
import hmac
import re
import secrets

from flask import abort, flash, make_response, redirect, render_template, request, session, url_for
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from dca_rebuild.archive_catalog import all_records, find_record
from dca_rebuild.battle_polls import matchups, find_matchup, OCCURRENCE, RESULTS
from dca_rebuild.models import (
    VaultBattleOutcome, VaultBattleOutcomeHistory, VaultHostAccount,
    VaultHostInvitation, VaultHostClaimChallenge, VaultHostBattleAudit,
)
from dca_rebuild.email_verification import (
    _digest, _normalize, _secret, _send_email, EmailDeliveryError,
    start_site_session, logout_site_session_at_midnight,
)

HOSTS = (
    ("hypeituptv", "HypeItUpTV", (("ty-shotz", "Ty Shotz"), ("lil-spank", "Lil Spank"))),
    ("body-bag", "Body Bag", (("chris-gz", "Chris Gz"), ("sns", "SNS"))),
)
HOST_LABELS = {slug: title for slug, title, _ in HOSTS}
MEMBERS = {(host, person): name for host, _, people in HOSTS for person, name in people}
INVITE_LIFETIME = timedelta(days=14)
CODE_LIFETIME = timedelta(minutes=10)


def csrf(name):
    return session.setdefault(name, secrets.token_urlsafe(32))


def check_csrf(name):
    expected = session.get(name)
    if not expected or not hmac.compare_digest(expected, request.form.get("csrf_token", "")):
        abort(400, "Invalid form token")


def events_for_host(host):
    if host not in HOST_LABELS:
        abort(404)
    name = HOST_LABELS[host].casefold()
    return [row for row in all_records() if row.get("record_type") == "event"
            and (row.get("presenter") or "").casefold() == name]


def roster_only(section):
    return "initial advertised team roster" in str(section or "").casefold()


def host_queue(factory, host):
    records = events_for_host(host)
    all_keys = [battle["key"] for record in records for group in matchups(record)
                if not roster_only(group["section"]) for battle in group["items"]]
    with factory() as db:
        outcomes = {row.battle_key: (row.occurred, row.result, row.source_note or "")
                    for row in db.query(VaultBattleOutcome).filter(
                        VaultBattleOutcome.battle_key.in_(all_keys)).all()} if all_keys else {}
    groups = []
    pending = complete = 0
    for record in records:
        sections = []
        waiting = done = 0
        roster_count = 0
        for section in matchups(record):
            if roster_only(section["section"]):
                roster_count += len(section["items"])
                continue
            rows = []
            for battle in section["items"]:
                occurred, result, note = outcomes.get(battle["key"], ("unconfirmed", "unknown", ""))
                resolved = occurred == "did_not_happen" or (occurred == "happened" and result != "unknown")
                rows.append({**battle, "occurred": occurred, "result": result,
                             "source_note": note, "resolved": resolved})
                if resolved:
                    done += 1
                else:
                    waiting += 1
            if rows:
                sections.append({"name": section["section"], "rows": rows})
        pending += waiting
        complete += done
        groups.append({"slug": record["slug"], "title": record["title"],
                       "date_label": record["date_label"], "sections": sections,
                       "pending": waiting, "complete": done, "roster_count": roster_count})
    return {"name": HOST_LABELS[host], "key": host, "events": groups,
            "event_count": len(groups), "pending": pending, "complete": complete}


def invitation(factory, token):
    if not re.fullmatch(r"[A-Za-z0-9_-]{35,120}", token or ""):
        abort(404)
    digest = hashlib.sha256(token.encode()).hexdigest()
    with factory() as db:
        row = db.query(VaultHostInvitation).filter_by(token_hash=digest).first()
        if not row or row.status != "pending" or row.expires_at <= datetime.utcnow():
            abort(410, "This invitation has expired or has been claimed")
        if (row.host_key, row.person_key) not in MEMBERS:
            abort(403)
        return row.id, row.host_key, row.person_key


def active_host(factory):
    logout_site_session_at_midnight()
    account_id = session.get("vault_host_account_id")
    if not isinstance(account_id, int):
        return None
    with factory() as db:
        row = db.get(VaultHostAccount, account_id)
        if row and row.is_active and (row.host_key, row.person_key) in MEMBERS:
            return {"id": row.id, "host_key": row.host_key,
                    "display_name": row.display_name, "person_key": row.person_key}
    session.pop("vault_host_account_id", None)
    return None


def secure_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def save_outcome(db, record, key, occurred, result, source_note, actor_id=None):
    matchup = find_matchup(record, key)
    if occurred not in OCCURRENCE or result not in RESULTS:
        abort(400)
    if occurred != "happened" and result != "unknown":
        abort(400)
    if result in ("a", "b", "tie", "youtube_decide") and len(matchup["contestants"]) != 2:
        abort(400, "Multi-person or non-versus lineups need editorial handling")
    if len(source_note) < 5 or len(source_note) > 500:
        abort(400, "Provide the source or host confirmation")
    row = db.get(VaultBattleOutcome, key)
    old_occurred, old_result = (row.occurred, row.result) if row else (None, None)
    if row:
        row.occurred, row.result, row.source_note = occurred, result, source_note
        row.updated_at = datetime.utcnow()
    else:
        db.add(VaultBattleOutcome(
            battle_key=key, event_slug=record["slug"], lineup_label=matchup["label"][:500],
            occurred=occurred, result=result, source_note=source_note))
    db.add(VaultBattleOutcomeHistory(
        battle_key=key, event_slug=record["slug"],
        previous_occurrence=old_occurred, previous_result=old_result,
        occurred=occurred, result=result, source_note=source_note))
    if actor_id is not None:
        db.add(VaultHostBattleAudit(battle_key=key, event_slug=record["slug"],
                                    actor_account_id=actor_id, occurred=occurred, result=result))


def install_host_access(app, ns):
    # Resolve SessionLocal at request time; isolated app fixtures and future
    # database reconnections must not retain the startup session factory.
    class FactoryProxy:
        def __call__(self, *args, **kwargs):
            return ns["SessionLocal"](*args, **kwargs)
        def begin(self):
            return ns["SessionLocal"].begin()

    factory = FactoryProxy()
    admin_required = ns["admin_login_required"]

    @app.before_request
    def expire_host_session():
        logout_site_session_at_midnight()

    @app.get("/admin/hosts", endpoint="vault_admin_hosts")
    @admin_required
    def admin_hosts():
        fresh = session.pop("vault_host_fresh_link", None)
        with factory() as db:
            accounts = {(x.host_key, x.person_key): x for x in db.query(VaultHostAccount).all()}
            all_invites = db.query(VaultHostInvitation).order_by(
                VaultHostInvitation.created_at.desc()).all()
            invites = {}
            for x in all_invites:
                invites.setdefault((x.host_key, x.person_key), x)
            cards = []
            for host, label, people in HOSTS:
                people_rows = []
                for person_key, name in people:
                    account, invite = accounts.get((host, person_key)), invites.get((host, person_key))
                    people_rows.append({"key": person_key, "name": name,
                                        "account_id": account.id if account else None,
                                        "display_name": account.display_name if account else None,
                                        "email": account.email if account else None,
                                        "active": bool(account and account.is_active),
                                        "invite_status": invite.status if invite else None})
                cards.append({"key": host, "name": label, "people": people_rows,
                              "queue": host_queue(factory, host)})
        return secure_response(make_response(render_template(
            "admin_host_workspaces.html", hosts=cards, new_link=fresh,
            csrf_token=csrf("vault_host_admin_csrf"))))

    @app.get("/admin/hosts/<host_key>/battles", endpoint="vault_admin_host_queue")
    @admin_required
    def admin_host_queue(host_key):
        view = request.args.get("view", "pending")
        if view not in ("pending", "all"):
            abort(400)
        queue = host_queue(factory, host_key)
        return secure_response(make_response(render_template(
            "admin_host_queue.html", queue=queue, view=view,
            csrf_token=csrf("vault_host_admin_csrf"))))

    @app.post("/admin/hosts/<host_key>/battles/<slug>/<battle_key>/outcome",
              endpoint="vault_admin_host_result")
    @admin_required
    def admin_host_result(host_key, slug, battle_key):
        check_csrf("vault_host_admin_csrf")
        if host_key not in HOST_LABELS:
            abort(404)
        record = find_record(slug)
        if not record or (record.get("presenter") or "").casefold() != HOST_LABELS[host_key].casefold():
            abort(403)
        if any(item["key"] == battle_key for group in matchups(record)
               if roster_only(group["section"]) for item in group["items"]):
            abort(403)
        choice = request.form.get("outcome")
        if choice in ("a", "b", "tie", "youtube_decide", "no_contest"):
            occurred, result = "happened", choice
        elif choice in ("did_not_happen", "postponed", "unconfirmed"):
            occurred, result = choice, "unknown"
        else:
            abort(400)
        note = " ".join((request.form.get("source_note") or "").split())
        if not 5 <= len(note) <= 300:
            abort(400, "Admin changes require a source or explanation")
        with factory.begin() as db:
            save_outcome(db, record, battle_key, occurred, result, note)
        flash("Battle result recorded with archival edit history.")
        return redirect(url_for("vault_admin_host_queue", host_key=host_key) + "#battle-" + battle_key[:12], code=303)

    @app.post("/admin/hosts/invite", endpoint="vault_admin_host_invite")
    @admin_required
    def admin_invite():
        check_csrf("vault_host_admin_csrf")
        host, person = request.form.get("host_key"), request.form.get("person_key")
        if (host, person) not in MEMBERS:
            abort(400)
        token = secrets.token_urlsafe(32)
        with factory.begin() as db:
            account = db.query(VaultHostAccount).filter_by(
                host_key=host, person_key=person, is_active=True).first()
            if account:
                abort(409, "This person already has host access")
            db.query(VaultHostInvitation).filter_by(
                host_key=host, person_key=person, status="pending"
            ).update({"status": "revoked"}, synchronize_session=False)
            db.add(VaultHostInvitation(
                host_key=host, person_key=person,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.utcnow() + INVITE_LIFETIME))
        session["vault_host_fresh_link"] = {
            "person": MEMBERS[(host, person)], "host": HOST_LABELS[host],
            "url": url_for("vault_host_claim", token=token, _external=True),
        }
        flash("Private invitation created. Copy it now; it cannot be displayed again.")
        return redirect(url_for("vault_admin_hosts") + "#invitations", code=303)

    @app.post("/admin/hosts/revoke/<int:account_id>", endpoint="vault_admin_host_revoke")
    @admin_required
    def admin_revoke(account_id):
        check_csrf("vault_host_admin_csrf")
        with factory.begin() as db:
            account = db.get(VaultHostAccount, account_id)
            if not account:
                abort(404)
            account.is_active = False
        flash("Host access revoked.")
        return redirect(url_for("vault_admin_hosts"), code=303)

    @app.route("/hosts/claim/<token>", methods=["GET", "POST"], endpoint="vault_host_claim")
    def claim(token):
        invite_id, host, person = invitation(factory, token)
        csrf("vault_host_claim_csrf")
        stage = "identity"
        notice = ""
        if request.method == "POST":
            check_csrf("vault_host_claim_csrf")
            action = request.form.get("action")
            if action == "send":
                if (request.form.get("host_key"), request.form.get("person_key")) != (host, person):
                    abort(403, "This invite is for a different host/person")
                email = _normalize(request.form.get("email"))
                now = datetime.utcnow()
                code = f"{secrets.randbelow(1000000):06d}"
                with factory.begin() as db:
                    challenge = db.get(VaultHostClaimChallenge, invite_id)
                    if challenge and now - challenge.sent_at < timedelta(seconds=60):
                        abort(429, "Request another code after one minute")
                    code_hash = _digest(_secret(app), "host-claim", str(invite_id), email, code)
                    if challenge:
                        challenge.email, challenge.code_hash, challenge.attempts = email, code_hash, 0
                        challenge.sent_at, challenge.expires_at, challenge.verified_at = now, now + CODE_LIFETIME, None
                    else:
                        db.add(VaultHostClaimChallenge(
                            invitation_id=invite_id, email=email, code_hash=code_hash,
                            sent_at=now, expires_at=now + CODE_LIFETIME))
                    try:
                        _send_email(email, code)
                    except EmailDeliveryError:
                        app.logger.warning("Host verification email delivery failed")
                        abort(503, "Could not send verification email")
                session.pop("vault_host_verified_invite", None)
                session["vault_host_pending_invite"] = invite_id
                stage, notice = "code", "A six-digit code was sent to your email."
            elif action == "verify":
                if session.get("vault_host_pending_invite") != invite_id:
                    abort(403)
                code = (request.form.get("code") or "").strip()
                if not re.fullmatch(r"[0-9]{6}", code):
                    abort(400)
                with factory.begin() as db:
                    challenge = db.query(VaultHostClaimChallenge).filter_by(
                        invitation_id=invite_id).with_for_update().first()
                    if not challenge or challenge.expires_at <= datetime.utcnow() or challenge.attempts >= 5:
                        abort(403, "Code expired or too many attempts")
                    challenge.attempts += 1
                    expected = _digest(_secret(app), "host-claim", str(invite_id), challenge.email, code)
                    if hmac.compare_digest(expected, challenge.code_hash):
                        challenge.verified_at = datetime.utcnow()
                        session["vault_host_verified_invite"] = invite_id
                        stage = "account"
                    else:
                        stage, notice = "code", "Incorrect code. Try again."
            elif action == "create":
                if session.get("vault_host_verified_invite") != invite_id:
                    abort(403, "Verify your email first")
                display = " ".join((request.form.get("display_name") or "").split())
                password = request.form.get("password") or ""
                if not 2 <= len(display) <= 120 or not 12 <= len(password) <= 200:
                    abort(400, "Display name is required; password must be at least 12 characters")
                now = datetime.utcnow()
                with factory.begin() as db:
                    row = db.query(VaultHostInvitation).filter_by(id=invite_id).with_for_update().first()
                    challenge = db.get(VaultHostClaimChallenge, invite_id)
                    if not row or row.status != "pending" or row.expires_at <= now:
                        abort(410)
                    if not challenge or not challenge.verified_at or now - challenge.verified_at > timedelta(minutes=20):
                        abort(403, "Email verification expired; please try again")
                    old = db.query(VaultHostAccount).filter_by(host_key=host, person_key=person).first()
                    if old:
                        if old.is_active or old.email != challenge.email:
                            abort(409, "This identity already has an account; contact the administrator")
                        old.display_name = display
                        old.password_hash = generate_password_hash(password)
                        old.is_active = True
                        account_id = old.id
                    else:
                        account = VaultHostAccount(host_key=host, person_key=person,
                            display_name=display, email=challenge.email,
                            password_hash=generate_password_hash(password))
                        db.add(account)
                        db.flush()
                        account_id = account.id
                    row.status, row.claimed_at = "claimed", now
                session.clear()
                session["vault_host_account_id"] = account_id
                start_site_session(request.form.get("timezone"))
                return redirect(url_for("vault_host_workspace"), code=303)
            else:
                abort(400)
        else:
            if session.get("vault_host_verified_invite") == invite_id:
                with factory() as db:
                    challenge = db.get(VaultHostClaimChallenge, invite_id)
                    if challenge and challenge.verified_at and datetime.utcnow() - challenge.verified_at < timedelta(minutes=20):
                        stage = "account"
            elif session.get("vault_host_pending_invite") == invite_id:
                stage = "code"
        return secure_response(make_response(render_template(
            "host_claim.html", token=token, host_key=host, person_key=person,
            host_name=HOST_LABELS[host], person_name=MEMBERS[(host, person)],
            stage=stage, notice=notice, csrf_token=csrf("vault_host_claim_csrf"))))

    @app.route("/hosts/login", methods=["GET", "POST"], endpoint="vault_host_login")
    def login():
        if active_host(factory):
            return redirect(url_for("vault_host_workspace"), code=303)
        error = None
        if request.method == "POST":
            check_csrf("vault_host_claim_csrf")
            email = _normalize(request.form.get("email"))
            password = request.form.get("password") or ""
            with factory() as db:
                row = db.query(VaultHostAccount).filter_by(email=email, is_active=True).first()
                account_id = row.id if row and check_password_hash(row.password_hash, password) else None
            if account_id:
                session.clear()
                session["vault_host_account_id"] = account_id
                start_site_session(request.form.get("timezone"))
                return redirect(url_for("vault_host_workspace"), code=303)
            error = "Incorrect email or password."
        return secure_response(make_response(render_template(
            "host_login.html", error=error, csrf_token=csrf("vault_host_claim_csrf"))))

    @app.post("/hosts/logout", endpoint="vault_host_logout")
    def logout():
        check_csrf("vault_host_claim_csrf")
        session.clear()
        return redirect(url_for("vault_host_login"), code=303)

    @app.get("/hosts/workspace", endpoint="vault_host_workspace")
    def workspace():
        account = active_host(factory)
        if not account:
            return redirect(url_for("vault_host_login"))
        return secure_response(make_response(render_template(
            "host_workspace.html", account=account,
            queue=host_queue(factory, account["host_key"]),
            csrf_token=csrf("vault_host_claim_csrf"))))

    @app.post("/hosts/workspace/<slug>/<battle_key>/outcome", endpoint="vault_host_result")
    def save_result(slug, battle_key):
        account = active_host(factory)
        if not account:
            abort(403, "Sign in to manage results")
        check_csrf("vault_host_claim_csrf")
        record = find_record(slug)
        if not record or (record.get("presenter") or "").casefold() != HOST_LABELS[account["host_key"]].casefold():
            abort(403, "The battle belongs to another host")
        matchup = find_matchup(record, battle_key)
        if any(row["key"] == battle_key for group in matchups(record)
               if roster_only(group["section"]) for row in group["items"]):
            abort(403, "Team roster is not a matchup")
        choice = request.form.get("outcome")
        if choice in ("a", "b", "tie", "youtube_decide", "no_contest"):
            occurred, result = "happened", choice
        elif choice in ("did_not_happen", "postponed", "unconfirmed"):
            occurred, result = choice, "unknown"
        else:
            abort(400)
        note = " ".join((request.form.get("source_note") or "").split())
        if len(note) > 300:
            abort(400)
        source = "Host confirmation by " + account["display_name"] + " (" + HOST_LABELS[account["host_key"]] + ")"
        if note:
            source += " - " + note
        with factory.begin() as db:
            row = db.get(VaultHostAccount, account["id"])
            if not row or not row.is_active:
                abort(403)
            save_outcome(db, record, battle_key, occurred, result, source, account["id"])
        flash("Battle outcome saved; the promoted lineup is unchanged.")
        return redirect(url_for("vault_host_workspace") + "#battle-" + battle_key[:12], code=303)
