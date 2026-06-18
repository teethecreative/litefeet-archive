from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as app_module

app = app_module.app
app.testing = True

ROUTES_TO_TEST = [
    "/",
    "/people",
    "/people/dancers",
    "/people/producers",
    "/people/teams",
    "/dancers",
    "/dancers/create",
    "/people/dancers/create",
    "/events",
    "/events/submit",
    "/litefeet-music",
    "/litefeet-music/projects/submit",
    "/account/login",
    "/account/signup",
    "/account/profile-link",
    "/account/profile-visibility",
    "/admin/login",
    "/admin",
    "/admin/users",
    "/admin/profile-links",
    "/admin/profile-visibility-requests",
    "/admin/submissions",
    "/verify",
    "/submit",
]

with app.test_client() as client:
    failures = []

    for route in ROUTES_TO_TEST:
        try:
            response = client.get(route, follow_redirects=False)
            status = response.status_code
            location = response.headers.get("Location", "")

            if status >= 500:
                failures.append((route, status, location, "500 error"))

            print(f"{status:3} {route} -> {location}")

        except Exception as exc:
            failures.append((route, "EXCEPTION", "", str(exc)))
            print(f"\nEXCEPTION on {route}: {exc}")
            traceback.print_exc()

    if failures:
        print("\n=== FAILURES ===")
        for failure in failures:
            print(failure)
        raise SystemExit(1)

print("\nSmoke test passed without 500 errors.")
