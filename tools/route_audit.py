from pathlib import Path
import re
import sys

ROOT = Path.cwd()

possible_app_paths = [
    ROOT / "app.py",
    ROOT / "src" / "app.py",
]

app_path = None

for path in possible_app_paths:
    if path.exists():
        app_path = path
        break

if app_path is None:
    matches = list(ROOT.glob("**/app.py"))
    if matches:
        app_path = matches[0]

if app_path is None:
    print("Could not find app.py from", ROOT)
    sys.exit(1)

template_dir = app_path.parent / "templates"
if not template_dir.exists():
    template_dir = ROOT / "templates"

print(f"Using app file: {app_path}")
print(f"Using templates: {template_dir}")

app_text = app_path.read_text(errors="ignore")

print("\n=== FLASK ROUTES FOUND IN APP.PY ===")

route_pattern = re.compile(
    r'''@app\.route\(\s*["']([^"']+)["'](?:,\s*methods=\[([^\]]+)\])?\s*\)\s*\ndef\s+([a-zA-Z_][a-zA-Z0-9_]*)''',
    re.S,
)

routes = []

for match in route_pattern.finditer(app_text):
    route = match.group(1)
    methods_raw = match.group(2) or '"GET"'
    endpoint = match.group(3)

    methods = ", ".join(re.findall(r'''["']([^"']+)["']''', methods_raw))
    routes.append((route, endpoint, methods))

for route, endpoint, methods in sorted(routes):
    print(f"{route:60} -> {endpoint:45} [{methods}]")

print("\n=== HARDCODED TEMPLATE LINKS / FORMS ===")

template_pattern = re.compile(r'''(href|action)=["'](/[^"'{%][^"']*)["']''')

hardcoded = []

if template_dir.exists():
    for path in sorted(template_dir.glob("*.html")):
        text = path.read_text(errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in template_pattern.finditer(line):
                attr = match.group(1)
                url = match.group(2)

                if url.startswith(("/static/", "/assets/", "/favicon", "/#", "/uploads/")):
                    continue

                hardcoded.append((path, lineno, attr, url, line.strip()))
                print(f"{path}:{lineno}: {attr}={url}")
else:
    print("No templates directory found.")

print("\n=== POSSIBLE BAD EVENT ROUTE REFERENCES OUTSIDE EVENT TEMPLATES ===")

if template_dir.exists():
    for path in sorted(template_dir.glob("*.html")):
        text = path.read_text(errors="ignore")

        if "event" in path.name.lower():
            continue

        for lineno, line in enumerate(text.splitlines(), 1):
            lowered = line.lower()

            if "/events" in lowered or "event_public_url" in lowered or "event_detail" in lowered:
                print(f"{path}:{lineno}: {line.strip()}")

print("\n=== DYNAMIC ROUTE-LIKE TEMPLATE LINES TO MANUALLY CHECK ===")

dynamic_pattern = re.compile(r'''(href|action)=["'][^"']*{{[^"']+["']''')

if template_dir.exists():
    for path in sorted(template_dir.glob("*.html")):
        text = path.read_text(errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if dynamic_pattern.search(line):
                print(f"{path}:{lineno}: {line.strip()}")

print("\nAudit complete.")
