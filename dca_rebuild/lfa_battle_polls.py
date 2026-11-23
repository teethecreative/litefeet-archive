"""2026 LiteFeet Awards Battle Day community verdicts.

Opinion voting is independent of the official archive and of Dancer's Choice
Awards nominations. Admins publish filmed matchups; verified visitors may
choose either side or a tie, once per matchup, with no automatic poll expiry.
"""
from datetime import datetime
from urllib.parse import parse_qs, urlsplit
import re
import secrets

from flask import abort, flash, redirect, request, session, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from dca_rebuild.email_verification import verified_nominator_hash
from dca_rebuild.models import LFABattlePoll, VaultBattleVote


EDITION = 2026
CSRF_KEY = "lfv_lfa_battle_csrf"
CHOICES = {"a", "b", "t"}
KEY_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def youtube_link(value):
    """Only accept actual YouTube video URLs; no generic event/source links."""
    value = (value or "").strip()
    if len(value) > 500:
        return None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
            return None
        if host in {"youtu.be", "www.youtu.be"}:
            return value if re.fullmatch(r"/[A-Za-z0-9_-]{11}/?", parsed.path) else None
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if parsed.path == "/watch":
                video = parse_qs(parsed.query).get("v", [""])[0]
                return value if re.fullmatch(r"[A-Za-z0-9_-]{11}", video) else None
            if re.fullmatch(r"/(shorts|live|embed)/[A-Za-z0-9_-]{11}/?", parsed.path):
                return value
    except ValueError:
        pass
    return None


def list_battle_polls(factory, viewer_hash=None, is_admin=False):
    with factory() as db:
        query = db.query(LFABattlePoll).filter_by(year=EDITION)
        if not is_admin:
            query = query.filter_by(published=True)
        polls = query.order_by(LFABattlePoll.created_at, LFABattlePoll.battle_key).all()
        keys = [row.battle_key for row in polls]
        counts = {}
        already_voted = set()
        if keys:
            counts = {
                (key, choice): count
                for key, choice, count in db.query(
                    VaultBattleVote.battle_key, VaultBattleVote.choice,
                    func.count(VaultBattleVote.id)
                ).filter(VaultBattleVote.battle_key.in_(keys))
                .group_by(VaultBattleVote.battle_key, VaultBattleVote.choice).all()
            }
            if viewer_hash:
                already_voted = {
                    row.battle_key for row in db.query(VaultBattleVote.battle_key)
                    .filter(VaultBattleVote.battle_key.in_(keys),
                            VaultBattleVote.voter_hash == viewer_hash).all()
                }
        output = []
        for poll in polls:
            tally = {choice: counts.get((poll.battle_key, choice), 0)
                     for choice in ("a", "b", "t")}
            total = sum(tally.values())
            percentages = {choice: round(tally[choice] * 100 / total) if total else 0
                           for choice in ("a", "b", "t")}
            output.append(dict(
                battle_key=poll.battle_key, side_a=poll.side_a, side_b=poll.side_b,
                youtube_url=poll.youtube_url, published=poll.published,
                already_voted=poll.battle_key in already_voted,
                votes_a=tally["a"], votes_b=tally["b"], votes_tie=tally["t"],
                percent_a=percentages["a"], percent_b=percentages["b"],
                percent_tie=percentages["t"], total_votes=total,
            ))
        return output


def _csrf():
    return session.setdefault(CSRF_KEY, secrets.token_urlsafe(32))


def _check_csrf():
    supplied = request.form.get("csrf_token") or ""
    expected = session.get(CSRF_KEY) or ""
    if not expected or not secrets.compare_digest(expected, supplied):
        abort(400, "This voting form expired. Refresh the page and try again.")


def _names():
    a = " ".join((request.form.get("side_a") or "").split())
    b = " ".join((request.form.get("side_b") or "").split())
    if not a or not b or len(a) > 120 or len(b) > 120 or a.casefold() == b.casefold():
        abort(400, "Enter two different battle participants, 120 characters or fewer.")
    return a, b


def _return_to_battles():
    return redirect(url_for("lfa_home") + "#battles", code=303)


def install_lfa_battle_polls(app, factory, admin_login_required):
    @app.context_processor
    def lfa_battle_poll_context():
        if request.endpoint not in ("lfa_home", "lfa_year"):
            return {}
        if request.endpoint == "lfa_year" and (request.view_args or {}).get("year") != EDITION:
            return {}
        admin = bool(session.get("ledger_admin_authenticated"))
        verified = verified_nominator_hash()
        return {
            "lfa_battle_polls": list_battle_polls(factory, verified, admin),
            "lfa_battle_poll_admin": admin,
            "lfa_battle_poll_verified": bool(verified),
            "lfa_battle_poll_csrf": _csrf(),
        }

    @app.post("/awards/litefeet-awards/2026/battles/<battle_key>/vote",
              endpoint="lfa_battle_vote")
    def vote(battle_key):
        if not KEY_PATTERN.fullmatch(battle_key):
            abort(404)
        _check_csrf()
        who = verified_nominator_hash()
        if not who:
            abort(403, "Verify your email before voting.")
        choice = (request.form.get("choice") or "").strip()
        if choice not in CHOICES:
            abort(400, "Choose one dancer or Tie.")
        with factory.begin() as db:
            poll = db.get(LFABattlePoll, battle_key)
            if not poll or poll.year != EDITION or not poll.published:
                abort(404)
            if db.query(VaultBattleVote.id).filter_by(
                battle_key=battle_key, voter_hash=who
            ).first():
                abort(409, "You have already voted on this matchup.")
            db.add(VaultBattleVote(
                battle_key=battle_key, voter_hash=who, choice=choice))
            try:
                db.flush()
            except IntegrityError:
                abort(409, "You have already voted on this matchup.")
        flash("Your vote is recorded as a community opinion, not an official result.",
              "lfa_battle")
        return redirect(url_for("lfa_home") + "#lfa-battle-" + battle_key[:12], code=303)

    @app.post("/admin/awards/litefeet-awards/2026/battles",
              endpoint="lfa_battle_admin_create")
    @admin_login_required
    def create_poll():
        _check_csrf()
        a, b = _names()
        link = youtube_link(request.form.get("youtube_url"))
        if not link:
            abort(400, "An individual YouTube battle video is required.")
        with factory.begin() as db:
            db.add(LFABattlePoll(
                battle_key=secrets.token_hex(32), year=EDITION,
                side_a=a, side_b=b, youtube_url=link, published=True))
        flash("Battle poll published. Official results are unchanged.", "lfa_battle")
        return _return_to_battles()

    @app.post("/admin/awards/litefeet-awards/2026/battles/<battle_key>/edit",
              endpoint="lfa_battle_admin_edit")
    @admin_login_required
    def edit_poll(battle_key):
        if not KEY_PATTERN.fullmatch(battle_key):
            abort(404)
        _check_csrf()
        a, b = _names()
        link = youtube_link(request.form.get("youtube_url"))
        if not link:
            abort(400, "A YouTube battle video is required.")
        status = (request.form.get("visibility") or "").strip()
        if status not in {"published", "hidden"}:
            abort(400)
        with factory.begin() as db:
            poll = db.get(LFABattlePoll, battle_key)
            if not poll or poll.year != EDITION:
                abort(404)
            if (poll.side_a != a or poll.side_b != b) and db.query(VaultBattleVote.id).filter_by(
                battle_key=battle_key
            ).first():
                abort(409, "Participant names cannot be changed once votes exist; hide this matchup and add a corrected one.")
            poll.side_a, poll.side_b, poll.youtube_url = a, b, link
            poll.published = status == "published"
            poll.updated_at = datetime.utcnow()
        flash("Battle poll updated; existing votes were preserved.", "lfa_battle")
        return _return_to_battles()
