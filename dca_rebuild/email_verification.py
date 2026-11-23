"""Request-only email codes for DCA participation via an existing Resend account.

This confirms mailbox access, not a person's real-world identity. Email codes
are never persisted in plaintext; the nomination history is unchanged.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import hmac
import os
import re
import secrets
import time

import requests
from flask import abort, current_app, flash, make_response, redirect, render_template, request, session, url_for
from sqlalchemy import Column, DateTime, Integer, String

from dca_rebuild.models import (
    Base, DCANominationContact, DCANominationSubmission,
)
from dca_rebuild.nomination_service import insert_for


SESSION_CHALLENGE = "lfv_email_challenge"
SESSION_VERIFIED = "lf9e_verified_hash"
SESSION_VERIFIED_AT = "lf9e_verified_at"
SESSION_CSRF = "lfv_verify_csrf"
VALIDITY = timedelta(minutes=10)
VERIFIED_SECONDS = 7 * 24 * 3600
MAX_ATTEMPTS = 5
MAX_EMAILS_PER_HOUR = 5
MAX_IP_EMAILS_PER_HOUR = 100
RESEND_DELAY = timedelta(seconds=60)


class EmailVerificationCode(Base):
    __tablename__ = "vault_email_verification_codes"
    id = Column(Integer, primary_key=True)
    request_id = Column(String(64), nullable=False, unique=True, index=True)
    email_address = Column(String(254), nullable=False)
    email_hash = Column(String(64), nullable=False, index=True)
    network_hash = Column(String(64), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    requested_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)


def verification_enabled():
    return os.getenv("DCA_2026_VERIFIED_EMAIL_ENABLED") == "true"


def verified_nominator_hash():
    who = session.get(SESSION_VERIFIED)
    verified_at = session.get(SESSION_VERIFIED_AT)
    if (not isinstance(who, str) or len(who) != 64
        or not isinstance(verified_at, int)
        or not 0 <= time.time() - verified_at < VERIFIED_SECONDS):
        return None
    return who


def _secret(app):
    key = app.secret_key
    if not key or str(key) in ("local-dev-secret", "local-dev-salt"):
        raise RuntimeError("Production verification requires a configured application secret")
    return key.encode("utf-8") if isinstance(key, str) else key


def _digest(secret, *values):
    return hmac.new(secret, ":".join(values).encode("utf-8"), hashlib.sha256).hexdigest()


def _normalize(email):
    email = (email or "").strip().casefold()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        abort(400, "Enter a valid email address.")
    return email


def _mask(email):
    local, domain = email.rsplit("@", 1)
    return (local[:1] + "•••@" + domain) if local else "•••@" + domain


class EmailDeliveryError(Exception):
    """Safe classification only: never include provider responses or secrets."""

    def __init__(self, category):
        super().__init__(category)
        self.category = category


def delivery_config_status():
    """Nonsecret configuration health summary for startup and support logs."""
    key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("RESEND_FROM_EMAIL", "").strip()
    mailbox = r"[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+"
    sender_is_bare = bool(re.fullmatch(mailbox, sender))
    sender_is_named = bool(re.fullmatch(
        r"[^<>\r\n]{1,100}\s+<" + mailbox + r">", sender
    ))
    return {
        "api_key_present": bool(key),
        "sender_present": bool(sender),
        "sender_format_valid": sender_is_bare or sender_is_named,
    }

def _send_email(email, code):
    status = delivery_config_status()
    if not status["api_key_present"]:
        raise EmailDeliveryError("missing_api_key")
    if not status["sender_present"]:
        raise EmailDeliveryError("missing_sender")
    if not status["sender_format_valid"]:
        raise EmailDeliveryError("invalid_sender_format")
    key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("RESEND_FROM_EMAIL", "").strip()
    # This message is sent only after the visitor explicitly requests a code.
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            json={
                "from": sender,
                "to": [email],
                "subject": "Your LiteFeet Vault verification code",
                "text": (
                    f"Your LiteFeet Vault verification code is {code}. "
                    "It expires in 10 minutes. If you didn't request it, "
                    "you can ignore this email."
                ),
            },
            headers={"Authorization": "Bearer " + key},
            timeout=10,
        )
    except requests.exceptions.Timeout as exc:
        raise EmailDeliveryError("provider_timeout") from exc
    except requests.exceptions.RequestException as exc:
        raise EmailDeliveryError("provider_connection_error") from exc
    if response.status_code >= 400:
        # HTTP status only, not the provider's response body, mailbox, or API key.
        raise EmailDeliveryError(f"provider_http_{int(response.status_code)}")


def begin_verification(app, session_factory, email, network=""):
    """Send a code and return a redirect. Never authenticate from typed email."""
    email = _normalize(email)
    # Optional staging-only guard: never email anyone outside the intended test.
    allowed_test_email = os.getenv("DCA_VERIFICATION_TEST_RECIPIENT", "").strip().casefold()
    if allowed_test_email and email != allowed_test_email:
        abort(403, "This verification test is restricted.")
    secret = _secret(app)
    now = datetime.utcnow()
    email_hash = _digest(secret, "mail", email)
    network_hash = _digest(secret, "network", network or "unknown")
    session.pop("lf9e_recent_hash", None)
    session.pop("lf9e_reminder_hash", None)
    session.pop(SESSION_VERIFIED, None)
    session.pop(SESSION_VERIFIED_AT, None)
    session.pop(SESSION_CHALLENGE, None)
    session.pop("lf9e_skipped", None)

    with session_factory.begin() as db:
        recent = db.query(EmailVerificationCode).filter(
            EmailVerificationCode.email_hash == email_hash,
            EmailVerificationCode.requested_at >= now - timedelta(hours=1),
        ).count()
        recent_network = db.query(EmailVerificationCode).filter(
            EmailVerificationCode.network_hash == network_hash,
            EmailVerificationCode.requested_at >= now - timedelta(hours=1),
        ).count()
        latest = (
            db.query(EmailVerificationCode)
            .filter(EmailVerificationCode.email_hash == email_hash)
            .order_by(EmailVerificationCode.requested_at.desc())
            .first()
        )
        if (recent >= MAX_EMAILS_PER_HOUR or recent_network >= MAX_IP_EMAILS_PER_HOUR
            or (latest and now - latest.requested_at < RESEND_DELAY)):
            abort(429, "Please wait before requesting another code.")
        code = f"{secrets.randbelow(1_000_000):06d}"
        request_id = secrets.token_urlsafe(24)
        db.add(EmailVerificationCode(
            request_id=request_id,
            email_address=email,
            email_hash=email_hash,
            network_hash=network_hash,
            code_hash=_digest(secret, "code", request_id, code),
            requested_at=now,
            expires_at=now + VALIDITY,
            attempts=0,
        ))

    try:
        _send_email(email, code)
    except Exception as exc:
        # Only emit a preapproved error category, never the exception message.
        category = (exc.category if isinstance(exc, EmailDeliveryError)
                    else "unexpected_delivery_error")
        current_app.logger.error("dca_verification_delivery_failed category=%s", category)
        # A failed send cannot authorize or leave behind a usable challenge.
        with session_factory.begin() as db:
            challenge = db.query(EmailVerificationCode).filter_by(request_id=request_id).first()
            if challenge:
                challenge.used_at = datetime.utcnow()
        flash("We couldn't send a code right now. Please try again shortly.")
        return redirect(url_for("dca_nominations_closed"), code=303)

    session[SESSION_CHALLENGE] = request_id
    session.setdefault(SESSION_CSRF, secrets.token_urlsafe(32))
    return redirect(url_for("dca_verify_email"), code=303)


def install_email_verification(app, session_factory, private_hash):
    status = delivery_config_status()
    app.logger.warning(
        "dca_verification_email_config api_key_present=%s sender_present=%s sender_format_valid=%s",
        status["api_key_present"], status["sender_present"], status["sender_format_valid"],
    )
    bind = session_factory.kw["bind"]
    EmailVerificationCode.__table__.create(bind=bind, checkfirst=True)

    @app.route("/awards/dancers-choice/verify-email", methods=["GET", "POST"])
    def dca_verify_email():
        if not verification_enabled():
            abort(404)
        session.setdefault(SESSION_CSRF, secrets.token_urlsafe(32))
        if request.method == "POST":
            supplied = request.form.get("csrf_token", "")
            if not supplied or not secrets.compare_digest(supplied, session[SESSION_CSRF]):
                abort(400, "This form expired. Refresh and try again.")
            action = request.form.get("action", "verify")
            if action == "send":
                return begin_verification(
                    app, session_factory, request.form.get("email", ""),
                    request.remote_addr or "",
                )
            if action == "resend":
                request_id = session.get(SESSION_CHALLENGE)
                if not request_id:
                    abort(400, "Enter your email to request a code.")
                with session_factory() as db:
                    old = db.query(EmailVerificationCode).filter_by(request_id=request_id).first()
                    if not old or old.used_at:
                        abort(400, "Enter your email to request a new code.")
                    email = old.email_address
                return begin_verification(app, session_factory, email, request.remote_addr or "")
            if action != "verify":
                abort(400, "This action isn't supported.")
            request_id = session.get(SESSION_CHALLENGE)
            code = (request.form.get("code") or "").strip()
            if not request_id or not re.fullmatch(r"[0-9]{6}", code):
                flash("Enter the six-digit code from your email.")
                return redirect(url_for("dca_verify_email"), code=303)

            with session_factory.begin() as db:
                challenge = (
                    db.query(EmailVerificationCode)
                    .filter_by(request_id=request_id)
                    .with_for_update()
                    .first()
                )
                now = datetime.utcnow()
                if (not challenge or challenge.used_at
                    or challenge.expires_at <= now
                    or challenge.attempts >= MAX_ATTEMPTS):
                    flash("Your code expired. Request another one.")
                    return redirect(url_for("dca_verify_email"), code=303)
                challenge.attempts += 1
                valid = hmac.compare_digest(
                    challenge.code_hash, _digest(_secret(app), "code", request_id, code)
                )
                if not valid:
                    if challenge.attempts >= MAX_ATTEMPTS:
                        challenge.used_at = now
                    flash("Incorrect code. Please try again.")
                    return redirect(url_for("dca_verify_email"), code=303)
                challenge.used_at = now
                email = challenge.email_address
                who = private_hash("dca-nomination:" + email)
                # Only a successfully verified mailbox can link historic nomination data.
                db.execute(
                    insert_for(db, DCANominationContact)
                    .values(submitter_hash=who, email_address=email, updated_at=now)
                    .on_conflict_do_update(
                        index_elements=["submitter_hash"],
                        set_={"email_address": email, "updated_at": now},
                    )
                )
                db.query(DCANominationSubmission).filter(
                    DCANominationSubmission.submitter_hash == who,
                    DCANominationSubmission.submitter_email.is_(None),
                ).update({"submitter_email": email}, synchronize_session=False)
            session.pop(SESSION_CHALLENGE, None)
            session[SESSION_VERIFIED] = who
            session[SESSION_VERIFIED_AT] = int(time.time())
            session["lf9e_recent_hash"] = who
            session["lf9e_reminder_hash"] = who
            flash("Email verified. You're ready to nominate.")
            return redirect(url_for("dca_nominations_closed"), code=303)

        request_id = session.get(SESSION_CHALLENGE)
        masked = None
        if request_id:
            with session_factory() as db:
                challenge = db.query(EmailVerificationCode).filter_by(request_id=request_id).first()
                if challenge and not challenge.used_at:
                    masked = _mask(challenge.email_address)
        response = make_response(render_template(
            "dca_verify_email.html",
            csrf_token=session[SESSION_CSRF], masked_email=masked,
        ))
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Referrer-Policy"] = "same-origin"
        return response
