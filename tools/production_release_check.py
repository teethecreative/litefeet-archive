from pathlib import Path
import subprocess
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app


EXPECTED_TABLES = [
    "submissions",
    "archive_users",
    "dancer_profiles",
    "media_items",
    "music_feedback",
    "music_play_events",
    "verification_votes",
    "role_requests",
    "ask_conversations",
    "ask_messages",
    "ask_feedback",
    "profile_claims",
    "profile_edit_logs",
    "saved_items",
    "calendar_item_metadata",
    "battle_records",
    "community_perspectives",
    "team_access_grants",
]


PUBLIC_ROUTES = [
    "/",
    "/ask",
    "/calendar",
    "/people-teams",
    "/litefeet-music",
    "/battles",
    "/awards",
    "/ledger-review",
]

AUTH_ROUTES = [
    "/account/login",
    "/admin/login",
]


def run_git(args):
    try:
        result = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception as exc:
        return f"git unavailable: {exc}"


def get_maintenance_mode():
    try:
        rows = app.fetch_all(
            "SELECT value FROM site_settings WHERE key = :key LIMIT 1",
            {"key": "maintenance_mode"},
        )
        return rows[0]["value"] if rows else "off"
    except Exception:
        return "off"


def set_maintenance_mode(value):
    app.set_site_setting("maintenance_mode", value)


def table_exists(table_name):
    from sqlalchemy import text

    with app.engine.connect() as conn:
        if app.maintenance_uses_postgres():
            rows = conn.execute(
                text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                    LIMIT 1
                """),
                {"table_name": table_name},
            ).fetchall()
            return bool(rows)

        rows = conn.execute(
            text("""
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name = :table_name
                LIMIT 1
            """),
            {"table_name": table_name},
        ).fetchall()
        return bool(rows)


def check_tables():
    print("---- table checks ----")

    missing = []
    for table in EXPECTED_TABLES:
        ok = table_exists(table)
        print(f"{table}: {'OK' if ok else 'MISSING'}")
        if not ok:
            missing.append(table)

    return missing


def check_routes(client, label, routes, expected_statuses):
    print(f"---- {label} ----")
    failures = []

    for route in routes:
        response = client.get(route, follow_redirects=False)
        status = response.status_code
        location = response.headers.get("Location", "")
        print(route, status, location)

        if status not in expected_statuses:
            failures.append((route, status, sorted(expected_statuses)))

    return failures


def main():
    print("=== Phase 2I Production Release Check ===")
    print("branch:", run_git(["branch", "--show-current"]))
    print("commit:", run_git(["rev-parse", "--short", "HEAD"]))
    print("database:", app.engine.dialect.name)

    app.ensure_phase2_ledger_tables()

    phase2g = getattr(app, "ensure_phase2g_community_perspective_columns", None)
    if callable(phase2g):
        phase2g()

    original_mode = get_maintenance_mode()
    print("original maintenance_mode:", original_mode)

    client = app.app.test_client()

    failures = []

    try:
        missing_tables = check_tables()
        if missing_tables:
            failures.append(("missing_tables", ",".join(missing_tables), "all expected tables present"))

        set_maintenance_mode("off")
        failures.extend(check_routes(client, "public mode routes", PUBLIC_ROUTES + AUTH_ROUTES, {200, 302}))

        set_maintenance_mode("on")
        failures.extend(check_routes(client, "maintenance mode public routes", PUBLIC_ROUTES, {503}))
        failures.extend(check_routes(client, "maintenance mode auth routes", AUTH_ROUTES, {200, 302}))

        with client.session_transaction() as session:
            session["admin_logged_in"] = True

        failures.extend(
            check_routes(
                client,
                "admin backend routes during maintenance",
                ["/admin", "/admin/deploy-status", "/admin/phase2"],
                {200, 302},
            )
        )

    finally:
        set_maintenance_mode(original_mode)
        print("restored maintenance_mode:", original_mode)

    if failures:
        print("---- FAILURES ----")
        for failure in failures:
            print(failure)
        return 1

    print("Production release check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
