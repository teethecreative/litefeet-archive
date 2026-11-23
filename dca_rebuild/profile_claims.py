"""Moderated ownership claims for modern public Vault profiles.

Email verification proves control of a mailbox, not ownership of a cultural
identity. An administrator must approve every claim. Approved owners receive
the same access used to moderate their public profile Wall.
"""
from datetime import datetime, timedelta
import secrets

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import Column, DateTime, Integer, String, Text

from dca_rebuild.models import Base, DCANominationContact
from dca_rebuild.profile_wall import (
    VaultProfileWallOwner, VaultProfileWallOwnerAudit,
    _mask_email, _profile_for_path,
)
from dca_rebuild.email_verification import verified_nominator_hash


class VaultProfileClaim(Base):
    __tablename__ = "vault_profile_claims"

    id = Column(Integer, primary_key=True)
    profile_href = Column(String(280), nullable=False, index=True)
    claimant_hash = Column(String(64), nullable=False, index=True)
    masked_email = Column(String(254), nullable=False)
    relationship = Column(String(32), nullable=False)
    explanation = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    admin_note = Column(Text, nullable=True)


def install_profile_claims(app, session_factory):
    Base.metadata.create_all(bind=session_factory.kw["bind"],
                             tables=[VaultProfileClaim.__table__])

    def csrf():
        return session.setdefault("vault_profile_claim_csrf", secrets.token_urlsafe(32))

    def require_csrf():
        given = request.form.get("csrf_token", "")
        expected = session.get("vault_profile_claim_csrf", "")
        if not given or not expected or not secrets.compare_digest(given, expected):
            abort(400, "This form expired. Refresh the page and try again.")

    def current_owner(db, profile_href):
        return db.query(VaultProfileWallOwner).filter(
            VaultProfileWallOwner.profile_href == profile_href,
            VaultProfileWallOwner.revoked_at.is_(None),
        ).first()

    @app.context_processor
    def profile_claim_display():
        def status_for(profile):
            path = profile.get("href") if isinstance(profile, dict) else None
            if not path:
                return "unknown"
            who = verified_nominator_hash()
            with session_factory() as db:
                owner = current_owner(db, path)
                if owner:
                    return "owned_by_you" if who and owner.verified_email_hash == who else "claimed"
                if who and db.query(VaultProfileClaim.id).filter_by(
                    profile_href=path, claimant_hash=who, status="pending",
                ).first():
                    return "pending"
            return "unclaimed"
        return {"vault_profile_claim_status": status_for}

    @app.route("/profile-claims", methods=["GET", "POST"], endpoint="vault_profile_claim")
    def claim_profile():
        path = (request.form.get("profile_href") if request.method == "POST"
                else request.args.get("profile")) or ""
        profile = _profile_for_path(path, session_factory)
        if profile is None:
            abort(404)
        who = verified_nominator_hash()
        csrf_token = csrf()

        if request.method == "POST":
            require_csrf()
            if not who:
                flash("Verify your email first, then return here to submit your claim.", "claim")
                return redirect(url_for("vault_profile_claim", profile=path), code=303)
            relationship = (request.form.get("relationship") or "").strip()
            allowed = ("representative",) if profile["is_team"] else ("self",)
            if relationship not in allowed:
                abort(400, "Select a valid relationship to this profile.")
            explanation = " ".join((request.form.get("explanation") or "").split())
            if not 30 <= len(explanation) <= 1500:
                flash("Explain your connection in 30 to 1,500 characters.", "claim")
                return redirect(url_for("vault_profile_claim", profile=path), code=303)

            with session_factory.begin() as db:
                owner = current_owner(db, path)
                if owner and owner.verified_email_hash == who:
                    flash("You already have approved owner access.", "claim")
                elif db.query(VaultProfileClaim.id).filter_by(
                    profile_href=path, claimant_hash=who, status="pending",
                ).first():
                    flash("Your existing claim is awaiting review.", "claim")
                else:
                    recent = db.query(VaultProfileClaim.id).filter(
                        VaultProfileClaim.claimant_hash == who,
                        VaultProfileClaim.created_at >= datetime.utcnow() - timedelta(days=1),
                    ).count()
                    if recent >= 5:
                        abort(429, "Too many claims today. Please try again later.")
                    contact = db.get(DCANominationContact, who)
                    if not contact or not contact.email_address:
                        abort(403, "Verify your email again before claiming a profile.")
                    db.add(VaultProfileClaim(
                        profile_href=path, claimant_hash=who,
                        masked_email=_mask_email(contact.email_address),
                        relationship=relationship, explanation=explanation,
                        status="pending", created_at=datetime.utcnow(),
                    ))
                    flash("Claim submitted for administrator review. Your profile is unchanged.", "claim")
            return redirect(url_for("vault_profile_claim", profile=path), code=303)

        with session_factory() as db:
            owner = current_owner(db, path)
            own_claim = (db.query(VaultProfileClaim)
                         .filter_by(profile_href=path, claimant_hash=who)
                         .order_by(VaultProfileClaim.created_at.desc())
                         .first() if who else None)
            status = ("owned_by_you" if owner and who and
                      owner.verified_email_hash == who else
                      "claimed" if owner else "unclaimed")
            existing_claim = dict(status=own_claim.status,
                                  admin_note=own_claim.admin_note,
                                  created_at=own_claim.created_at) if own_claim else None
        response = render_template(
            "profile_claim_request.html", profile=profile, owner_status=status,
            own_claim=existing_claim, verified=bool(who), csrf_token=csrf_token,
        )
        return response, 200, {"Cache-Control": "private, no-store",
                               "X-Robots-Tag": "noindex, nofollow"}

    @app.get("/admin/profile-claims", endpoint="admin_profile_claims")
    def admin_claims():
        if not session.get("ledger_admin_authenticated"):
            return redirect(url_for("admin_login"))
        view = request.args.get("view", "pending")
        if view not in ("pending", "approved", "rejected", "all"):
            abort(400)
        with session_factory() as db:
            q = db.query(VaultProfileClaim)
            if view != "all":
                q = q.filter_by(status=view)
            rows = q.order_by(VaultProfileClaim.created_at.desc()).limit(200).all()
            claims = [dict(id=x.id, profile_href=x.profile_href,
                           masked_email=x.masked_email, relationship=x.relationship,
                           explanation=x.explanation, status=x.status,
                           created_at=x.created_at, resolved_at=x.resolved_at,
                           admin_note=x.admin_note,
                           conflicting_owner=bool(
                               (owner := current_owner(db, x.profile_href)) and
                               owner.verified_email_hash != x.claimant_hash))
                      for x in rows]
        return render_template("admin_profile_claims.html", claims=claims,
                               view=view, csrf_token=csrf())

    @app.post("/admin/profile-claims/<int:claim_id>/decision",
              endpoint="admin_profile_claim_decision")
    def decide_claim(claim_id):
        if not session.get("ledger_admin_authenticated"):
            abort(403)
        require_csrf()
        decision = request.form.get("decision")
        if decision not in ("approved", "rejected"):
            abort(400)
        note = (request.form.get("admin_note") or "").strip()[:1000]
        now = datetime.utcnow()
        with session_factory.begin() as db:
            claim = db.get(VaultProfileClaim, claim_id)
            if claim is None:
                abort(404)
            if claim.status != "pending":
                flash("This claim has already been resolved.", "claim")
                return redirect(url_for("admin_profile_claims", view="all"), code=303)
            if _profile_for_path(claim.profile_href, session_factory) is None:
                abort(404, "The profile is no longer published.")
            owner = current_owner(db, claim.profile_href)
            if decision == "approved":
                if owner and owner.verified_email_hash != claim.claimant_hash:
                    flash("Another owner is assigned. Review and revoke existing access before approving.", "claim")
                    return redirect(url_for("admin_profile_claims"), code=303)
                if owner is None:
                    inactive = db.query(VaultProfileWallOwner).filter_by(
                        profile_href=claim.profile_href).first()
                    if inactive:
                        inactive.verified_email_hash = claim.claimant_hash
                        inactive.masked_email = claim.masked_email
                        inactive.assigned_at = now
                        inactive.revoked_at = None
                    else:
                        db.add(VaultProfileWallOwner(
                            profile_href=claim.profile_href,
                            verified_email_hash=claim.claimant_hash,
                            masked_email=claim.masked_email, assigned_at=now))
                    db.add(VaultProfileWallOwnerAudit(
                        profile_href=claim.profile_href, action="granted",
                        masked_email=claim.masked_email, created_at=now))
            claim.status = decision
            claim.resolved_at = now
            claim.admin_note = note or None
        flash("Profile claim " + decision + ".", "claim")
        return redirect(url_for("admin_profile_claims"), code=303)
