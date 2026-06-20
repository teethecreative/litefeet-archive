import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


ROUTES = [
    {"path": "/healthz", "expected": [200]},
    {"path": "/", "expected": [200, 302, 503]},
    {"path": "/ask", "expected": [200, 302, 503]},
    {"path": "/events", "expected": [200, 302, 503]},
    {"path": "/people/dancers", "expected": [200, 302, 503]},
    {"path": "/people/producers", "expected": [200, 302, 503]},
    {"path": "/people/teams", "expected": [200, 302, 503]},
    {"path": "/litefeet-music", "expected": [200, 302, 503]},
    {"path": "/battles", "expected": [200, 302, 503]},
    {"path": "/awards", "expected": [200, 302, 503]},
    {"path": "/submit/start", "expected": [200, 302, 503]},
    {"path": "/about", "expected": [200, 302, 503]},
    {"path": "/account/login", "expected": [200, 302]},
]


HELPERS = [
    "ensure_phase2_ledger_tables",
    "ensure_phase3a_profile_columns",
    "ensure_phase2g_community_perspective_columns",
    "ensure_phase3c_ask_source_columns",
    "ensure_phase3e_ask_feedback_table",
    "ensure_phase3f_ask_feedback_admin_columns",
    "ensure_phase4a_profile_claim_link_columns",
    "ensure_phase4c_profile_owner_tables",
    "ensure_phase5_calendar_tables",
    "ensure_phase6_music_feedback_tables",
    "ensure_phase6d_music_project_columns",
    "ensure_phase7_battle_tables",
    "ensure_phase8_awards_tables",
    "ensure_phase9_team_tables",
    "ensure_phase11_account_tables",
    "ensure_phase13_music_feedback_compat_columns",
    "ensure_phase14_performance_indexes",
]


def run_helpers():
    for helper_name in HELPERS:
        helper = getattr(app, helper_name, None)
        if callable(helper):
            try:
                helper()
            except Exception as exc:
                print(f"helper skipped {helper_name}: {exc}")


def time_route(client, path, repeats=4):
    timings = []
    statuses = []
    sizes = []
    headers = []

    # Warmup
    client.get(path, follow_redirects=False)

    for _ in range(repeats):
        started = time.perf_counter()
        response = client.get(path, follow_redirects=False)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

        timings.append(elapsed_ms)
        statuses.append(response.status_code)
        sizes.append(len(response.get_data() or b""))
        headers.append(response.headers.get("X-Ledger-Response-Time-ms", ""))

    return {
        "path": path,
        "status": statuses[-1] if statuses else None,
        "statuses": statuses,
        "min_ms": min(timings) if timings else None,
        "median_ms": round(statistics.median(timings), 2) if timings else None,
        "max_ms": max(timings) if timings else None,
        "avg_size_bytes": round(statistics.mean(sizes), 2) if sizes else 0,
        "timing_header_ms": headers[-1] if headers else "",
    }


def main():
    run_helpers()

    original_maintenance = None

    try:
        original_maintenance = app.get_site_setting("maintenance_mode", "off")
        app.set_site_setting("maintenance_mode", "off")
    except Exception:
        pass

    client = app.app.test_client()

    results = []
    failures = []

    print("=== LiteFeet Ledger Performance Audit ===")

    for route in ROUTES:
        result = time_route(client, route["path"])
        result["expected"] = route["expected"]
        result["ok"] = result["status"] in route["expected"]
        results.append(result)

        if not result["ok"] or (result["status"] and result["status"] >= 500):
            failures.append(result)

        print(
            f"{result['path']:<24} "
            f"status={result['status']:<4} "
            f"median={result['median_ms']:>8}ms "
            f"max={result['max_ms']:>8}ms "
            f"size={int(result['avg_size_bytes'])}b "
            f"header={result['timing_header_ms']}"
        )

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "database": "postgres" if app.maintenance_uses_postgres() else "sqlite",
        "results": results,
        "failures": failures,
    }

    Path("performance_audit_report.json").write_text(json.dumps(payload, indent=2))

    if original_maintenance is not None:
        try:
            app.set_site_setting("maintenance_mode", original_maintenance)
        except Exception:
            pass

    print("Wrote performance_audit_report.json")

    if failures:
        print("FAILURES FOUND")
        sys.exit(1)

    print("Performance audit completed.")


if __name__ == "__main__":
    main()
