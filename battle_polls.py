"""Community opinion polls for documented LiteFeet battles.

These votes are never official historical results. A poll must be explicitly
opened by an administrator for an unjudged, tie, or YouTube Decide battle.
"""
from datetime import datetime
import secrets

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import text


POLL_LABELS = {
    "unjudged": "Unjudged — community opinion",
    "tie": "Official tie — community opinion",
    "youtube_decide": "YouTube Decide — community opinion",
}
CHOICES = ("one", "two", "tie")


def register_battle_polls(app, engine, current_user, is_admin):
    """Register routes and Jinja helpers on the existing Flask application."""

    def ensure_tables():
        primary = "SERIAL PRIMARY KEY" if engine.dialect.name.startswith("postgres") else "INTEGER PRIMARY KEY AUTOINCREMENT"
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS battle_poll_settings (
                    battle_id INTEGER PRIMARY KEY,
                    poll_status TEXT NOT NULL DEFAULT 'closed',
                    updated_at TEXT,
                    updated_by TEXT
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS battle_poll_votes (
                    id {primary},
                    battle_id INTEGER NOT NULL,
                    voter_key TEXT NOT NULL,
                    choice TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (battle_id, voter_key)
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS battle_poll_round_votes (
                    id {primary},
                    battle_id INTEGER NOT NULL,
                    voter_key TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    choice TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (battle_id, voter_key, round_number)
                )
            """))
            # Earlier battle records may predate the round-count field.
            if engine.dialect.name.startswith("postgres"):
                conn.execute(text("ALTER TABLE battle_records ADD COLUMN IF NOT EXISTS round_count INTEGER DEFAULT 1"))
            else:
                existing = {row[1] for row in conn.execute(text("PRAGMA table_info(battle_records)"))}
                if "round_count" not in existing:
                    conn.execute(text("ALTER TABLE battle_records ADD COLUMN round_count INTEGER DEFAULT 1"))

    def csrf():
        if not session.get("battle_poll_csrf"):
            session["battle_poll_csrf"] = secrets.token_urlsafe(32)
        return session["battle_poll_csrf"]

    def csrf_valid():
        submitted = str(request.form.get("csrf_token", ""))
        return bool(submitted and secrets.compare_digest(submitted, str(session.get("battle_poll_csrf", ""))))

    def user_identity():
        try:
            user = current_user()
            if user and user.get("id"):
                return "account:" + str(user["id"])
        except Exception:
            pass
        # Unified admin login also supports an authenticated admin session.
        if session.get("admin_logged_in") and session.get("admin_username"):
            return "admin:" + str(session["admin_username"]).strip().lower()
        return None

    def can_manage():
        try:
            return bool(is_admin())
        except Exception:
            return False

    def battle_by_id(battle_id):
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT * FROM battle_records WHERE id = :battle_id LIMIT 1"),
                {"battle_id": battle_id},
            ).mappings().first()

    def stored_status(battle_id):
        ensure_tables()
        with engine.connect() as conn:
            value = conn.execute(
                text("SELECT poll_status FROM battle_poll_settings WHERE battle_id = :battle_id"),
                {"battle_id": battle_id},
            ).scalar()
        return value if value in POLL_LABELS else "closed"

    def get_battle_poll(battle):
        battle_id = int(battle["id"])
        status = stored_status(battle_id)
        counts = {"one": 0, "two": 0, "tie": 0}
        own_choice = None
        try:
            round_count = max(1, min(20, int(battle.get("round_count") or 1)))
        except (TypeError, ValueError):
            round_count = 1
        round_results = {
            number: {"counts": {"one": 0, "two": 0, "tie": 0}, "own_choice": None}
            for number in range(1, round_count + 1)
        }
        comments = []
        with engine.connect() as conn:
            if status in POLL_LABELS:
                for row in conn.execute(
                    text("SELECT choice, COUNT(*) AS total FROM battle_poll_votes WHERE battle_id = :id GROUP BY choice"),
                    {"id": battle_id},
                ).mappings():
                    if row["choice"] in counts:
                        counts[row["choice"]] = int(row["total"])
                voter_key = user_identity()
                if voter_key:
                    own_choice = conn.execute(
                        text("SELECT choice FROM battle_poll_votes WHERE battle_id = :id AND voter_key = :voter"),
                        {"id": battle_id, "voter": voter_key},
                    ).scalar()
                for row in conn.execute(text("""
                    SELECT round_number, choice, COUNT(*) AS total
                    FROM battle_poll_round_votes WHERE battle_id = :id
                    GROUP BY round_number, choice
                """), {"id": battle_id}).mappings():
                    number = int(row["round_number"])
                    if number in round_results and row["choice"] in CHOICES:
                        round_results[number]["counts"][row["choice"]] = int(row["total"])
                if voter_key:
                    for row in conn.execute(text("""
                        SELECT round_number, choice FROM battle_poll_round_votes
                        WHERE battle_id = :id AND voter_key = :voter
                    """), {"id": battle_id, "voter": voter_key}).mappings():
                        number = int(row["round_number"])
                        if number in round_results:
                            round_results[number]["own_choice"] = row["choice"]
                try:
                    comments = list(conn.execute(
                        text("""
                            SELECT perspective_text, created_at
                            FROM community_perspectives
                            WHERE related_type IN ('battle', 'battle_record')
                              AND related_id = :id
                              AND perspective_status IN ('Approved', 'Community Supported')
                            ORDER BY created_at DESC LIMIT 12
                        """),
                        {"id": battle_id},
                    ).mappings())
                except Exception:
                    comments = []
        total = sum(counts.values())
        for result in round_results.values():
            round_total = sum(result["counts"].values())
            result["total"] = round_total
            result["percent"] = {
                choice: round(100 * count / round_total, 1) if round_total else 0
                for choice, count in result["counts"].items()
            }
        return {
            "status": status,
            "label": POLL_LABELS.get(status, ""),
            "is_open": status in POLL_LABELS,
            "counts": counts,
            "total": total,
            "percent": {choice: (round(100 * count / total, 1) if total else 0) for choice, count in counts.items()},
            "own_choice": own_choice,
            "round_count": round_count,
            "rounds": round_results,
            "can_vote": bool(user_identity()),
            "can_manage": can_manage(),
            "csrf": csrf(),
            "comments": comments,
        }

    def open_battle_poll_ids():
        ensure_tables()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT battle_id FROM battle_poll_settings
                WHERE poll_status IN ('unjudged', 'tie', 'youtube_decide')
            """)).fetchall()
        return {int(row[0]) for row in rows}

    def seed_confirmed_awards_battles():
        """Idempotently include the two reported Nov 21 unjudged matchups.

        Names, rounds and format come from the event report. Eloise's stage name
        is not known, so do not assert one. No official winners or videos.
        """
        ensure_tables()
        now = datetime.utcnow().isoformat(timespec="seconds")
        battles = (
            ("Tay Millz", "Boy Q", "1v1", 1,
             "One-round unjudged battle. No official winner reported."),
            ("Flii Boogiie", "King K & Eloise", "1v2", 2,
             "Two-round 1v2 unjudged battle: Flii Boogiie versus King K and Eloise together. Eloise's dance name is not confirmed. No official winner reported."),
        )
        with engine.begin() as conn:
            if engine.dialect.name.startswith("postgres"):
                conn.execute(text("SELECT pg_advisory_xact_lock(20261121)"))
            for one, two, battle_type, round_count, note in battles:
                params = {
                    "one": one, "two": two, "battle_type": battle_type,
                    "round_count": round_count, "note": note,
                    "event": "5th Annual LiteFeet Awards Weekend — Battle Day",
                    "date": "2026-11-21", "now": now,
                }
                existing = conn.execute(text("""
                    SELECT id, official_winner, winner, round_count
                    FROM battle_records
                    WHERE (
                        (LOWER(TRIM(competitor_one)) = LOWER(:one)
                         AND LOWER(TRIM(competitor_two)) = LOWER(:two))
                        OR
                        (LOWER(TRIM(competitor_one)) = LOWER(:two)
                         AND LOWER(TRIM(competitor_two)) = LOWER(:one))
                    )
                    AND (
                        COALESCE(event_date, '') IN ('2026-11-21', '11/21/2026', '11-21-2026')
                        OR LOWER(COALESCE(event_name, '')) LIKE '%litefeet award%'
                    )
                    ORDER BY id ASC LIMIT 1
                """), params).mappings().first()
                if existing:
                    battle_id = int(existing["id"])
                    has_winner = bool(str(existing["official_winner"] or existing["winner"] or "").strip())
                    if not has_winner and (existing["round_count"] is None or int(existing["round_count"]) != round_count):
                        conn.execute(text("""
                            UPDATE battle_records
                            SET round_count = :round_count, updated_at = :now
                            WHERE id = :battle_id
                        """), {"round_count": round_count, "battle_id": battle_id, "now": now})
                else:
                    battle_id = int(conn.execute(text("""
                        INSERT INTO battle_records
                            (event_name, event_date, battle_type, round_count,
                             competitor_one, competitor_two, official_winner, winner,
                             judges_text, notes, review_status, created_at, updated_at)
                        VALUES
                            (:event, :date, :battle_type, :round_count,
                             :one, :two, NULL, NULL, 'No judges / unjudged',
                             :note, 'Needs Verification', :now, :now)
                        RETURNING id
                    """), params).scalar())
                    has_winner = False
                if not has_winner:
                    conn.execute(text("""
                        INSERT INTO battle_poll_settings
                            (battle_id, poll_status, updated_at, updated_by)
                        VALUES (:battle_id, 'unjudged', :now, 'event-admin-seed')
                        ON CONFLICT (battle_id) DO NOTHING
                    """), {"battle_id": battle_id, "now": now})

    try:
        seed_confirmed_awards_battles()
    except Exception as exc:
        app.logger.warning("AWARDS_BATTLE_SEED_FAILED: %s: %s", type(exc).__name__, exc)

    @app.context_processor
    def inject_battle_poll_helpers():
        return {
            "get_battle_poll": get_battle_poll,
            "open_battle_poll_ids": open_battle_poll_ids,
            "battle_poll_can_manage": can_manage,
        }

    @app.route("/battle-records/<int:battle_id>/community-vote", methods=["POST"], endpoint="battle_poll_vote")
    def battle_poll_vote(battle_id):
        if not csrf_valid():
            abort(400, "This voting form expired. Reload the page and try again.")
        battle = battle_by_id(battle_id)
        if not battle:
            abort(404)
        if stored_status(battle_id) not in POLL_LABELS:
            abort(403, "This battle is not currently open for community voting.")
        identity = user_identity()
        if not identity:
            flash("Sign in before voting. You can still read all community results.", "warning")
            return redirect(url_for("account_login", next=url_for("battle_record_detail_phase2", battle_id=battle_id)))
        choice = str(request.form.get("choice", "")).strip().lower()
        if choice not in CHOICES:
            abort(400, "Choose an overall winner or a tie.")
        try:
            round_count = int(battle.get("round_count") or 1)
        except (ValueError, TypeError):
            round_count = 1
        if not 1 <= round_count <= 20:
            abort(400, "Invalid battle round count.")
        round_choices = {}
        for number in range(1, round_count + 1):
            round_choice = str(request.form.get(f"round_{number}", "")).strip().lower()
            if round_choice not in CHOICES:
                abort(400, f"Choose a winner or a tie for round {number}.")
            round_choices[number] = round_choice
        now = datetime.utcnow().isoformat(timespec="seconds")
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO battle_poll_votes (battle_id, voter_key, choice, created_at, updated_at)
                VALUES (:battle_id, :voter_key, :choice, :now, :now)
                ON CONFLICT (battle_id, voter_key)
                DO UPDATE SET choice = EXCLUDED.choice, updated_at = EXCLUDED.updated_at
            """), {"battle_id": battle_id, "voter_key": identity, "choice": choice, "now": now})
            for number, round_choice in round_choices.items():
                conn.execute(text("""
                    INSERT INTO battle_poll_round_votes
                        (battle_id, voter_key, round_number, choice, created_at, updated_at)
                    VALUES (:battle_id, :voter_key, :number, :choice, :now, :now)
                    ON CONFLICT (battle_id, voter_key, round_number)
                    DO UPDATE SET choice = EXCLUDED.choice, updated_at = EXCLUDED.updated_at
                """), {
                    "battle_id": battle_id, "voter_key": identity,
                    "number": number, "choice": round_choice, "now": now,
                })
        flash("Your overall and round-by-round community votes were saved. They do not change the official result.", "success")
        return redirect(url_for("battle_record_detail_phase2", battle_id=battle_id) + "#cultures-call")

    @app.route("/battle-records/<int:battle_id>/poll-settings", methods=["POST"], endpoint="battle_poll_settings_update")
    def battle_poll_settings_update(battle_id):
        if not can_manage():
            abort(403)
        if not csrf_valid():
            abort(400, "This form expired. Reload the page.")
        battle = battle_by_id(battle_id)
        if not battle:
            abort(404)
        status = str(request.form.get("poll_status", "")).strip()
        if status not in {*POLL_LABELS.keys(), "closed"}:
            abort(400, "Invalid poll setting.")
        official_winner = str(battle.get("official_winner") or battle.get("winner") or "").strip().lower()
        if status == "unjudged" and official_winner and official_winner not in {"unjudged", "not judged", "no decision", "none"}:
            flash("An official winner is recorded. Remove or correct that historical field before marking this battle unjudged.", "warning")
            return redirect(url_for("battle_record_detail_phase2", battle_id=battle_id))
        now = datetime.utcnow().isoformat(timespec="seconds")
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO battle_poll_settings (battle_id, poll_status, updated_at, updated_by)
                VALUES (:battle_id, :status, :now, :admin)
                ON CONFLICT (battle_id)
                DO UPDATE SET poll_status = EXCLUDED.poll_status,
                              updated_at = EXCLUDED.updated_at,
                              updated_by = EXCLUDED.updated_by
            """), {
                "battle_id": battle_id,
                "status": status,
                "now": now,
                "admin": user_identity() or "admin",
            })
        flash("Community voting setting updated. All existing votes are preserved.", "success")
        return redirect(url_for("battle_record_detail_phase2", battle_id=battle_id) + "#cultures-call")
