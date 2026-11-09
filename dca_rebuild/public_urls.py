"""Readable public URLs for published Vault records.

No schema migrations or mutable slug fields. Canonical slugs are generated
from visible names only when a name identifies exactly one public record.
Ambiguous names keep their existing, precise URLs.
"""
from datetime import date
import re
import unicodedata


def slugify(value):
    ascii_name = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")


def _unique(matches):
    return matches[0] if len(matches) == 1 else None


def person_slug(record):
    return slugify(str(record.get("title") or "").split("/")[0])


def person_by_slug(slug, records):
    if slug in {"dancers", "teams", "producers", "create", "search"}:
        return None
    return _unique([r for r in records
                    if r.get("collection") == "people" and person_slug(r) == slug])


def person_href(record, records):
    old = "/archive/records/" + str(record["slug"])
    if record.get("collection") != "people":
        return old
    slug = person_slug(record)
    chosen = person_by_slug(slug, records)
    return "/people/" + slug if slug and chosen and chosen["slug"] == record["slug"] else old


def music_slugs(record):
    artist = (record.get("artist_or_creator") or record.get("artist")
              or record.get("producer_name") or record.get("producer") or "")
    return slugify(artist), slugify(record.get("title"))


def music_by_slugs(artist_slug, title_slug, releases):
    return _unique([r for r in releases if music_slugs(r) == (artist_slug, title_slug)])


def music_href(record, releases):
    old = record["record_href"]
    artist, title = music_slugs(record)
    if not artist or not title:
        return old
    unique = music_by_slugs(artist, title, releases)
    if not unique or unique["record_href"] != old:
        return old
    return "/music/" + artist + "/" + title


def event_href(record, events):
    old = record["href"]
    day, title = record["date"], slugify(record["title"])
    if not title:
        return old
    collisions = sum(1 for r in events
                     if r["date"] == day and slugify(r["title"]) == title)
    return "/events/" + title + "/" + day if collisions == 1 else old


def event_by_slugs(title_slug, event_date, events):
    matches = [r for r in events
               if r["date"] == event_date and slugify(r["title"]) == title_slug]
    return _unique(matches)


def category_by_slug(name_slug, categories):
    return _unique([c for c in categories if slugify(c["name"]) == name_slug])


def nominee_by_slug(name_slug, category):
    return _unique([n for n in category["nominees"] if slugify(n["name"]) == name_slug])


def category_href(category, categories):
    name_slug = slugify(category["name"])
    chosen = category_by_slug(name_slug, categories)
    if name_slug and chosen and chosen["id"] == category["id"]:
        return "/awards/2026/" + name_slug
    return "/awards/dancers-choice/nominations?view=results&category=" + str(category["id"])


def nominee_href(category, nominee, categories):
    base = category_href(category, categories)
    name_slug = slugify(nominee["name"])
    chosen = nominee_by_slug(name_slug, category)
    if base.startswith("/awards/2026/") and name_slug and chosen and chosen["id"] == nominee["id"]:
        return base + "/" + name_slug
    return ("/awards/dancers-choice/nominations?view=results&category="
            + str(category["id"]) + "&suggestion=" + str(nominee["id"]))


def install_clean_public_urls(app, session_factory):
    """Register clean display routes without changing existing records or POSTs."""
    from flask import abort, current_app, redirect, request, g
    from dca_rebuild.archive_catalog import all_records
    from dca_rebuild.music_batch_catalog import combined_releases
    from dca_rebuild.music_public import full_date, music_duration
    from dca_rebuild.upcoming_calendar import upcoming_calendar
    from dca_rebuild.share_awards import public_categories

    def releases():
        if not hasattr(g, "_clean_music_releases"):
            getter = current_app.extensions.get("vault_published_music_rows")
            g._clean_music_releases = combined_releases(
                getter() if getter else [], full_date, music_duration)
        return g._clean_music_releases

    def categories():
        if not hasattr(g, "_clean_award_categories"):
            g._clean_award_categories = public_categories()
        return g._clean_award_categories

    def day_events(date_value):
        try:
            parsed = date.fromisoformat(date_value)
        except ValueError:
            abort(404)
        return upcoming_calendar(today=parsed, window_days=1,
                                 session_factory=session_factory)["events"]

    @app.before_request
    def move_legacy_links_to_public_paths():
        if request.method != "GET":
            return None
        path = request.path

        if path == "/litefeet-music":
            return redirect("/music" + (("?" + request.query_string.decode("utf-8"))
                                       if request.query_string else ""), code=301)
        if path.startswith("/archive/records/"):
            slug = path[len("/archive/records/"):]
            record = next((r for r in all_records() if r["slug"] == slug), None)
            if record and record["collection"] == "people":
                target = person_href(record, all_records())
                if target != path:
                    return redirect(target, code=301)
        if path.startswith(("/people/dancers/", "/dancers/")):
            from dca_rebuild.legacy_profile_routes import legacy_dancer_destination
            destination = legacy_dancer_destination(path)
            if destination and destination.startswith("/archive/records/"):
                slug = destination[len("/archive/records/"):]
                record = next((r for r in all_records() if r["slug"] == slug), None)
                if record:
                    target = person_href(record, all_records())
                    if target != destination:
                        return redirect(target, code=301)
        if path.startswith(("/litefeet-music/release/", "/litefeet-music/catalog/")):
            row = next((r for r in releases() if r["record_href"] == path), None)
            if row:
                destination = music_href(row, releases())
                if destination != path:
                    return redirect(destination, code=301)
        if path.startswith("/calendar/events/") and not path.endswith("/calendar.ics"):
            pieces = path.split("/")
            if len(pieces) == 5:
                matches = [e for e in day_events(pieces[3]) if e["href"] == path]
                if len(matches) == 1:
                    target = event_href(matches[0], day_events(pieces[3]))
                    if target != path:
                        return redirect(target, code=301)
        if path == "/awards/dancers-choice/nominations" and request.args.get("view") == "results":
            raw_id = request.args.get("category", "")
            raw_nominee = request.args.get("suggestion", "")
            if raw_id.isdigit() and (not raw_nominee or raw_nominee.isdigit()):
                chosen = next((c for c in categories() if c["id"] == int(raw_id)), None)
                if chosen:
                    nominee = next((n for n in chosen["nominees"]
                                   if n["id"] == int(raw_nominee)), None) if raw_nominee else None
                    if raw_nominee and nominee is None:
                        return None
                    target = (nominee_href(chosen, nominee, categories()) if nominee
                              else category_href(chosen, categories()))
                    if target.startswith("/awards/2026/"):
                        return redirect(target, code=301)
            if not raw_id and not raw_nominee and set(request.args) == {"view"}:
                return redirect("/awards/2026/standings", code=301)
        return None

    @app.get("/people/<person_slug>", endpoint="vault_clean_person")
    def clean_person(person_slug):
        record = person_by_slug(person_slug, all_records())
        if not record:
            abort(404)
        return current_app.view_functions["vault_archive_record"](record["slug"])

    @app.get("/music", endpoint="vault_clean_music_index")
    def clean_music_index():
        return current_app.view_functions["vault_music_public"]()

    @app.get("/music/<artist_slug>/<title_slug>", endpoint="vault_clean_music_record")
    def clean_music_record(artist_slug, title_slug):
        item = music_by_slugs(artist_slug, title_slug, releases())
        if item is None or music_href(item, releases()) != request.path:
            abort(404)
        legacy = item["record_href"].split("/")
        if len(legacy) == 4 and legacy[:3] == ["", "litefeet-music", "release"]:
            return current_app.view_functions["vault_music_release"](int(legacy[3]))
        if len(legacy) == 5 and legacy[:3] == ["", "litefeet-music", "catalog"]:
            return current_app.view_functions["vault_music_catalog_record"](legacy[3], legacy[4])
        abort(404)

    @app.get("/events/<title_slug>/<event_date>", endpoint="vault_clean_calendar_event")
    def clean_calendar_event(title_slug, event_date):
        events = day_events(event_date)
        item = event_by_slugs(title_slug, event_date, events)
        if item is None or event_href(item, events) != request.path:
            abort(404)
        legacy_slug = item["href"].rsplit("/", 1)[-1]
        return current_app.view_functions["vault_calendar_event_detail"](event_date, legacy_slug)

    @app.get("/awards/2026/standings", endpoint="vault_clean_awards_standings")
    def clean_awards_standings():
        return current_app.view_functions["dca_nominations_closed"]()

    @app.get("/awards/2026/<category_slug>", endpoint="vault_clean_awards_category")
    def clean_awards_category(category_slug):
        if not category_by_slug(category_slug, categories()):
            abort(404)
        return current_app.view_functions["dca_nominations_closed"]()

    @app.get("/awards/2026/<category_slug>/<nominee_slug>",
             endpoint="vault_clean_awards_nominee")
    def clean_awards_nominee(category_slug, nominee_slug):
        selected = category_by_slug(category_slug, categories())
        if not selected or not nominee_by_slug(nominee_slug, selected):
            abort(404)
        return current_app.view_functions["dca_nominations_closed"]()

    @app.context_processor
    def clean_page_links():
        def person_link(record_slug):
            record = next((r for r in all_records() if r["slug"] == record_slug), None)
            return (person_href(record, all_records()) if record else
                    "/archive/records/" + record_slug)
        return {
            "clean_category_url": lambda c: category_href(c, categories()),
            "clean_nominee_url": lambda c, n: nominee_href(c, n, categories()),
            "clean_person_link": person_link,
        }
