"""2026 LiteFeet Awards battle voting, linked to actual event and profile pages.

Admins attach filmed battles to a published event using its Add Battle control.
Polls have three options and never overwrite official historical results.
"""
from datetime import date, datetime
from urllib.parse import parse_qs, urlsplit
import re
import secrets

from flask import abort, flash, g, redirect, request, session, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from dca_rebuild.email_verification import verified_nominator_hash
from dca_rebuild.models import LFABattlePoll, VaultBattleVote


EDITION = 2026
CSRF_KEY = "lfv_lfa_battle_csrf"
CHOICES = {"a", "b", "t"}
KEY_PATTERN = re.compile(r"^[a-f0-9]{64}$")
CALENDAR_EVENT = re.compile(r"^/calendar/events/(\d{4}-\d{2}-\d{2})/([a-z0-9-]+)$")
ARCHIVE_EVENT = re.compile(r"^/archive/records/([a-z0-9-]+)$")
PROFILE_PATH = re.compile(r"^/people/[a-z0-9-]+$")


def youtube_link(value):
    """A YouTube battle video is mandatory, even for an admin."""
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


def validate_event_href(value, factory):
    """Resolve an exact published event path; never trust posted event names."""
    value = (value or "").strip()
    match = CALENDAR_EVENT.fullmatch(value)
    if match:
        from dca_rebuild.calendar_pages import _get_event_for_day
        event = _get_event_for_day(match[1], match[2], factory)
        if event["href"] != value:
            abort(404)
        return event["href"], event["title"], int(event["date"][:4])
    match = ARCHIVE_EVENT.fullmatch(value)
    if match:
        from dca_rebuild.archive_catalog import find_record
        event = find_record(match[1])
        if not event or event["record_type"] != "event":
            abort(404)
        return value, event["title"], int(event["date"][:4]) if event.get("date") else EDITION
    abort(400, "Select an existing Vault event.")


def event_options():
    """Admin event selector; an on-the-spot battle still needs its parent event."""
    from dca_rebuild.archive_catalog import all_records
    from dca_rebuild.upcoming_calendar import curated_events, event_slug
    options = []
    seen = set()
    for event in curated_events():
        if not event.get("date"):
            continue
        href = f'/calendar/events/{event["date"]}/{event_slug(event["title"])}'
        options.append(dict(href=href, title=event["title"], date=event["date"]))
        seen.add(href)
    for record in all_records():
        if record.get("record_type") != "event":
            continue
        href = "/archive/records/" + record["slug"]
        if href not in seen:
            options.append(dict(href=href, title=record["title"], date=record.get("date") or ""))
    options.sort(key=lambda event: (
        event["date"] == "2026-11-21" and "litefeet awards" in event["title"].lower(),
        event["date"], event["title"]), reverse=True)
    return options


def list_battle_polls(factory, viewer_hash=None, is_admin=False,
                      event_href=None, participant_name=None):
    with factory() as db:
        query = db.query(LFABattlePoll).filter_by(year=EDITION)
        if event_href:
            query = query.filter(LFABattlePoll.event_href == event_href)
        if not is_admin:
            query = query.filter_by(published=True)
        polls = query.order_by(LFABattlePoll.created_at, LFABattlePoll.battle_key).all()
        if participant_name:
            normalized = " ".join(str(participant_name).split()).casefold()
            polls = [p for p in polls if normalized in (
                " ".join(p.side_a.split()).casefold(),
                " ".join(p.side_b.split()).casefold())]
        keys = [row.battle_key for row in polls]
        counts = {}
        voted = set()
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
                voted = {
                    key for (key,) in db.query(VaultBattleVote.battle_key).filter(
                        VaultBattleVote.battle_key.in_(keys),
                        VaultBattleVote.voter_hash == viewer_hash).all()
                }
        rows = []
        for poll in polls:
            tally = {c: counts.get((poll.battle_key, c), 0) for c in ("a", "b", "t")}
            total = sum(tally.values())
            rows.append(dict(
                battle_key=poll.battle_key, side_a=poll.side_a, side_b=poll.side_b,
                event_href=poll.event_href, event_title=poll.event_title,
                youtube_url=poll.youtube_url, published=poll.published,
                already_voted=poll.battle_key in voted,
                votes_a=tally["a"], votes_b=tally["b"], votes_tie=tally["t"],
                percent_a=round(tally["a"] * 100 / total) if total else 0,
                percent_b=round(tally["b"] * 100 / total) if total else 0,
                percent_tie=round(tally["t"] * 100 / total) if total else 0,
                total_votes=total,
            ))
        return rows


def _csrf():
    return session.setdefault(CSRF_KEY, secrets.token_urlsafe(32))


def _check_csrf():
    expected = session.get(CSRF_KEY) or ""
    if not expected or not secrets.compare_digest(expected, request.form.get("csrf_token") or ""):
        abort(400, "This voting form expired. Refresh and try again.")


def _names():
    a = " ".join((request.form.get("side_a") or "").split())
    b = " ".join((request.form.get("side_b") or "").split())
    if not a or not b or len(a) > 120 or len(b) > 120 or a.casefold() == b.casefold():
        abort(400, "Enter two different dancers or teams, 120 characters or fewer.")
    return a, b


def _return_href(target, anchor="community-battle-polls"):
    profile = (request.form.get("return_profile_href") or "").strip()
    if PROFILE_PATH.fullmatch(profile):
        # Only return to a known public profile, never a caller-supplied domain.
        from dca_rebuild.public_profiles import profile_index
        from dca_rebuild.public_urls import person_slug
        index = profile_index(_FACTORY)
        row = index.by_slug(profile.rsplit("/", 1)[-1])
        if row and row["href"] == profile:
            return redirect(profile + "#" + anchor, code=303)
    return redirect(target + "#" + anchor, code=303)


_FACTORY = None


def install_lfa_battle_polls(app, factory, admin_login_required):
    global _FACTORY
    _FACTORY = factory

    @app.context_processor
    def lfa_battle_poll_context():
        endpoint = request.endpoint or ""
        admin = bool(session.get("ledger_admin_authenticated"))
        verified = verified_nominator_hash()
        data = {
            "lfa_battle_poll_admin": admin,
            "lfa_battle_poll_verified": bool(verified),
            "lfa_battle_poll_csrf": _csrf(),
            "lfa_profile_battle_polls": lambda name: list_battle_polls(
                factory, verified, admin, participant_name=name),
            "lfa_battle_event_options": event_options() if admin and endpoint in (
                "vault_clean_person", "vault_archive_record") else [],
        }
        if endpoint in ("lfa_home", "lfa_year"):
            if endpoint != "lfa_year" or (request.view_args or {}).get("year") == EDITION:
                data["lfa_battle_polls"] = list_battle_polls(factory, verified, admin)
        if endpoint == "vault_calendar_event_detail":
            href = request.path
            data["lfa_battle_polls"] = list_battle_polls(factory, verified, admin, event_href=href)
            data["lfa_battle_create_event_href"] = href
        if endpoint == "vault_archive_record":
            from dca_rebuild.archive_catalog import find_record
            slug = (request.view_args or {}).get("slug")
            record = find_record(slug) if slug else None
            if record and record.get("record_type") == "event":
                href = url_for("vault_archive_record", slug=slug)
                data["lfa_battle_polls"] = list_battle_polls(factory, verified, admin, event_href=href)
                data["lfa_battle_create_event_href"] = href
        return data

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
                battle_key=battle_key, voter_hash=who).first():
                abort(409, "You have already voted on this matchup.")
            db.add(VaultBattleVote(
                battle_key=battle_key, voter_hash=who, choice=choice))
            try:
                db.flush()
            except IntegrityError:
                abort(409, "You have already voted on this matchup.")
            event_href = poll.event_href
        flash("Your community vote was recorded; the official result is unchanged.", "lfa_battle")
        return _return_href(event_href)

    @app.post("/admin/awards/litefeet-awards/2026/battles",
              endpoint="lfa_battle_admin_create")
    @admin_login_required
    def create_poll():
        _check_csrf()
        a, b = _names()
        link = youtube_link(request.form.get("youtube_url"))
        if not link:
            abort(400, "The individual YouTube battle link is required.")
        event_href, event_title, year = validate_event_href(request.form.get("event_href"), factory)
        if year != EDITION:
            abort(400, "This poll currently supports 2026 events.")
        with factory.begin() as db:
            db.add(LFABattlePoll(
                battle_key=secrets.token_hex(32), year=year,
                event_href=event_href, event_title=event_title,
                side_a=a, side_b=b, youtube_url=link, published=True))
        flash("Battle added to the event; community voting is open.", "lfa_battle")
        return _return_href(event_href)

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
            abort(400, "The individual YouTube battle link is required.")
        visibility = (request.form.get("visibility") or "").strip()
        if visibility not in {"published", "hidden"}:
            abort(400)
        with factory.begin() as db:
            poll = db.get(LFABattlePoll, battle_key)
            if not poll or poll.year != EDITION:
                abort(404)
            if (poll.side_a != a or poll.side_b != b) and db.query(VaultBattleVote.id).filter_by(
                battle_key=battle_key).first():
                abort(409, "You cannot change a matchup after votes exist. Hide it and add the corrected battle.")
            poll.side_a, poll.side_b, poll.youtube_url = a, b, link
            poll.published = visibility == "published"
            poll.updated_at = datetime.utcnow()
            event_href = poll.event_href
        flash("Battle updated without resetting votes.", "lfa_battle")
        return _return_href(event_href)
