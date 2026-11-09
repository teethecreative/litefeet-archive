"""The LiteFeet Vault public search metadata, crawl directives and XML sitemap."""
import re
from xml.sax.saxutils import escape
from flask import Response, request, abort

SITE_URL = "https://thelitefeetvault.com"
PAGES = {
    "/": (
        "The LiteFeet Vault | LiteFeet Culture & History",
        "Discover the people, history and creativity of LiteFeet in a living cultural archive built to preserve the culture.",
    ),
    "/awards/dancers-choice/2026": (
        "Dancer's Choice Awards 2026 | The LiteFeet Vault",
        "Explore the 2026 Dancer's Choice Awards: nominations, official categories and community write-ins.",
    ),
    "/awards/dancers-choice/2023": (
        "Dancer's Choice Awards 2023 Archive | The LiteFeet Vault",
        "Explore the August 2023 Dancer's Choice Awards archive: 31 award categories, 152 nominee entries and 32 recorded winning entries.",
    ),
    "/awards/litefeet-awards": (
        "LiteFeet Awards History & Results | The LiteFeet Vault",
        "Explore the LiteFeet Awards historical archive and contribute information about past categories, winners and honorees for verification.",
    ),
    "/awards/hypeitup": (
        "HypeItUpTV Awards | The LiteFeet Vault",
        "Find updates about the HypeItUpTV Awards, a developing section of The LiteFeet Vault awards archive.",
    ),
    "/awards/dancers-choice/category-suggestions": (
        "Dancer's Choice 2026 Category Suggestions | The LiteFeet Vault",
        "Review the Dancer's Choice Awards 2026 category-suggestion stage and learn how the community helps shape the award categories.",
    ),
    "/awards/dancers-choice/category-voting": (
        "Dancer's Choice 2026 Category Results | The LiteFeet Vault",
        "Review the Dancer's Choice Awards 2026 category-selection results and how categories were considered.",
    ),
}
PAGES.update({
    "/archive/people": ("People & Teams | The LiteFeet Vault",
                        "Search LiteFeet dancers, teams and community profiles, and discover their connections through sourced cultural records."),
    "/litefeet-music": ("LiteFeet Music Release Radar | The LiteFeet Vault",
                        "Discover LiteFeet tracks, albums and projects with release dates, artist and producer credits, durations, and original sources."),
        "/archive/lock-in": ("Lock In | The LiteFeet Card Battle Game", "Learn the rules, browse sample decks, play a practice round and contribute to the LiteFeet card game."),
    "/calendar": ("LiteFeet Events Calendar | The LiteFeet Vault", "Browse the community calendar for upcoming LiteFeet labs, battles, classes, workshops, recurring sessions and events."),
    "/submit": ("Submit a Battle, Lab, Link-Up or Class | The LiteFeet Vault",
                "Submit an upcoming battle, lab session, link-up, workshop, class or community gathering for review on The LiteFeet Vault."),
    "/submit/thank-you": ("Submission Received | The LiteFeet Vault", "Your community gathering has been submitted for review."),
    "/archive/timeline": ("History & Timeline | The LiteFeet Vault", "Explore a chronological LiteFeet event timeline and historical research, with sources and verification status."),
    "/archive/history": ("History of LiteFeet, Get Lite & the Harlem Shake | The LiteFeet Vault", "Explore sourced chapters about the original Harlem Shake, Get Lite origins, LiteFeet dancers and crews, music, moves, battle culture and subway performance."),
    "/awards": ("Awards | The LiteFeet Vault", "Explore LiteFeet award programs, current participation and historical results."),
    "/awards/dancers-choice": ("Dancer’s Choice Awards | The LiteFeet Vault", "Explore Dancer’s Choice award editions, current participation and historical archives."),
    "/community": ("Community | The LiteFeet Vault", "Contribute historical sources, suggest corrections and follow public community updates."),
    "/about": ("About The LiteFeet Vault | Dear LiteFeet", "Read the founder’s letter, discover the Vault’s mission and learn how community contributions help preserve LiteFeet history."),
    "/about/letter": ("Dear LiteFeet | Founder's Letter | The LiteFeet Vault", "Read the founder's letter about preserving LiteFeet culture for future generations."),
    "/about/mission": ("Our Mission | The LiteFeet Vault", "Learn the mission behind The LiteFeet Vault and its community archive."),
    "/about/archive": ("About the Archive | The LiteFeet Vault", "Learn how the Vault preserves documented dancers, crews, music, battles and original sources."),
    "/about/how-it-works": ("How It Works | The LiteFeet Vault", "Learn how to explore LiteFeet records, share evidence and suggest corrections."),
    "/about/contact": ("Contact | The LiteFeet Vault", "Reach the Vault team about preserving the history of LiteFeet."),

    "/awards/dancers-choice/nominations": ("Nominate for Dancer's Choice Awards 2026 | The LiteFeet Vault", "Browse official and write-in categories. Nominate or support a LiteFeet community member once per category every rolling 24 hours."),
})

# Public short links are real pages, not third-party shortening services.
# Legacy deep links still render and share the same canonical short URL.
PAGES["/write-ins"] = (
    "Write-In Categories | Dancer's Choice Awards 2026 | The LiteFeet Vault",
    "Explore community-suggested categories for the 2026 Dancer's Choice Awards. Find a category, nominate someone and help build support for its inclusion.",
)
CANONICAL_ALIASES = {
    "/awards/dancers-choice/write-ins": "/write-ins",
}

# Index curated public pages only; omit private forms and confirmation pages.
SITEMAP_PATHS = (
    "/",
    "/archive/lock-in",
    "/archive/timeline",
    "/archive/people",
    "/litefeet-music",
    "/calendar",
    "/awards",
    "/awards/dancers-choice",
    "/write-ins",
    "/community",
    "/about",
    "/about/letter",
    "/about/mission",
    "/about/archive",
    "/about/how-it-works",
    "/about/contact",
    "/awards/dancers-choice/2026",
    "/awards/dancers-choice/2023",
    "/awards/litefeet-awards",
    "/awards/litefeet-awards/2023",
    "/awards/litefeet-awards/2024",
    "/awards/litefeet-awards/2025",
    "/awards/litefeet-awards/2026",
    "/awards/hypeitup",
    "/submit",
    "/awards/dancers-choice/nominations",
    "/awards/dancers-choice/category-suggestions",
    "/awards/dancers-choice/category-voting",
)


def _published_music_rows():
    """Use only public releases, never draft/private media rows."""
    from flask import current_app
    loader = current_app.extensions.get("vault_published_music_rows")
    return loader() if loader else []


def _music_detail_record(path):
    from dca_rebuild.music_batch_catalog import batch_record
    match = re.fullmatch(r"/litefeet-music/catalog/(track|project)/([a-zA-Z0-9_-]+)", path)
    if match:
        return batch_record(match.group(1), match.group(2))
    match = re.fullmatch(r"/litefeet-music/release/([0-9]+)", path)
    if match:
        return next((r for r in _published_music_rows() if str(r.get("id")) == match.group(1)), None)
    return None


def _music_detail_metadata(path):
    item = _music_detail_record(path)
    if item is None:
        return None
    from dca_rebuild.music_presentation import with_release_display
    item = with_release_display(dict(item))
    name = " ".join(str(item.get("display_title") or item.get("title") or "Untitled release").split())
    artist = " ".join(str(item.get("artist_or_creator") or item.get("artist") or
                          item.get("producer_name") or "").split())
    kind = "project" if item.get("kind") == "project" else "track"
    title = f"{name} | LiteFeet Music | The LiteFeet Vault"
    description = (f"Discover the LiteFeet music {kind} {name}" +
                   (f" by {artist}" if artist else "") +
                   ". Explore documented credits, release details, and original listening sources.")
    return title[:180], description[:190]


def _published_calendar_events():
    """Current scheduled public occurrences only; future dates are transient."""
    from flask import current_app
    from dca_rebuild.upcoming_calendar import upcoming_calendar
    factory = current_app.extensions.get("vault_seo_session_factory")
    return upcoming_calendar(session_factory=factory)["events"] if factory else []


def _calendar_detail_metadata(path):
    match = re.fullmatch(r"/calendar/events/(\\d{4}-\\d{2}-\\d{2})/([a-z0-9-]+)", path)
    if not match:
        return None
    from dca_rebuild.upcoming_calendar import event_slug
    item = next((event for event in _published_calendar_events()
                 if event["date"] == match.group(1) and event_slug(event["title"]) == match.group(2)), None)
    if item is None:
        return None
    title = f"{item['title']} | LiteFeet Calendar | The LiteFeet Vault"
    description = (f"{item['title']} on {item['display_date']}. " +
                   "Find event details, location, organizer and original sources on The LiteFeet Vault.")
    return title[:180], description[:190]


def card_key_for_path(path):
    if path == "/":
        return "home"
    if path.startswith("/archive/records/"):
        return "record--" + path[len("/archive/records/"):]
    return path.strip("/").replace("/", "--")


def path_for_card_key(key):
    if key == "home":
        return "/"
    if key.startswith("record--"):
        return "/archive/records/" + key[len("record--"):]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,210}", key):
        return None
    return "/" + key.replace("--", "/")


def metadata_for_path(path, view=None):
    canonical_path = CANONICAL_ALIASES.get(path, path)
    record = PAGES.get(canonical_path)
    if record is None:
        match = re.fullmatch(r"/awards/litefeet-awards/(2023|2024|2025|2026)", path)
        if match:
            year = match.group(1)
            record = (
                f"LiteFeet Awards {year} Archive | The LiteFeet Vault",
                f"Explore the LiteFeet Awards {year} archive and its preserved awards history on The LiteFeet Vault.",
            )
    if record is None and canonical_path.startswith("/litefeet-music/"):
        record = _music_detail_metadata(canonical_path)
    if record is None and canonical_path.startswith("/calendar/events/"):
        record = _calendar_detail_metadata(canonical_path)
    if record is None and canonical_path.startswith("/archive/records/"):
        from dca_rebuild.archive_catalog import find_record
        item = find_record(canonical_path[len("/archive/records/"):])
        if item:
            summary = " ".join((item.get("summary") or "").split())
            label = ("Archived results" if item.get("editorial_status") == "Archived results"
                     else "Historical research")
            if len(summary) < 40:
                summary = f"{item['title']}: {summary}. Explore this entry in The LiteFeet Vault's historical archive."
            record = (
                item["title"] + " | The LiteFeet Vault Archive",
                (label + ": " + summary)[:180],
            )
    if record is None:
        return None
    results = path == '/awards/dancers-choice/nominations' and view == 'results'
    if results:
        record = ("DCA 2026 Nominee Standings | The LiteFeet Vault",
                  "See current Dancer’s Choice Awards 2026 nominees and nomination totals across every category on The LiteFeet Vault.")
    title, description = record
    canonical = SITE_URL + canonical_path + ('?view=results' if results else '')
    image_url = (SITE_URL + '/static/social/dca-2026-standings-v1.png' if results
                 else SITE_URL + '/social/cards/' + card_key_for_path(canonical_path) + '.png')
    image_alt = (("Dancer's Choice Awards 2026 nominee standings" if results else title)
                 + " — The LiteFeet Vault social preview")
    website = {"@type": "WebSite", "name": "The LiteFeet Vault", "url": SITE_URL + "/"}
    page = {
        "@type": "WebPage",
        "name": title,
        "description": description,
        "url": canonical,
        "isPartOf": {"@id": SITE_URL + "/#website"},
    }
    schema = {"@context": "https://schema.org", "@graph": [
        {**website, "@id": SITE_URL + "/#website"}, page,
    ]}
    return {"title": title, "description": description, "canonical": canonical, "schema": schema,
            "image": image_url, "image_alt": image_alt}


def register_seo(app):
    from dca_rebuild.social_cards import render_social_card

    @app.get("/social/cards/<card>.png")
    def litefeet_social_card(card):
        path = path_for_card_key(card)
        if not path:
            abort(404)
        metadata = metadata_for_path(path)
        if not metadata:
            abort(404)
        kind = "vault" if path == "/" else "write-ins" if path == "/write-ins" else "page"
        return Response(
            render_social_card(kind, metadata["title"], metadata["description"]),
            mimetype="image/png",
            headers={"Cache-Control": "public, max-age=604800",
                     "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/social/<card>.png")
    def litefeet_legacy_social_card(card):
        if card not in ("vault", "write-ins"):
            abort(404)
        path = "/" if card == "vault" else "/write-ins"
        meta = metadata_for_path(path)
        return Response(render_social_card(card, meta["title"], meta["description"]),
                        mimetype="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})

    @app.context_processor
    def litefeet_seo_context():
        return {"seo": metadata_for_path(request.path, request.args.get("view"))}

    @app.get("/robots.txt")
    def litefeet_robots():
        # noindex headers must remain crawlable to be recognized.
        return Response(
            "User-agent: *\nAllow: /\nSitemap: " + SITE_URL + "/sitemap.xml\n",
            content_type="text/plain; charset=utf-8",
        )

    @app.get("/sitemap.xml")
    def litefeet_sitemap():
        from dca_rebuild.archive_catalog import all_records
        from dca_rebuild.music_batch_catalog import batch_catalog
        from dca_rebuild.upcoming_calendar import event_slug
        paths = list(SITEMAP_PATHS) + [
            "/archive/records/" + item["slug"] for item in all_records()
        ] + [
            "/litefeet-music/catalog/" + item["kind"] + "/" + item["catalog_id"]
            for item in batch_catalog()
        ] + [
            "/litefeet-music/release/" + str(item["id"])
            for item in _published_music_rows()
        ] + [
            "/calendar/events/" + item["date"] + "/" + event_slug(item["title"])
            for item in _published_calendar_events()
        ]
        entries = "".join(
            "<url><loc>" + escape(SITE_URL + path) + "</loc></url>"
            for path in dict.fromkeys(paths)
        )
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + entries + '</urlset>',
            content_type="application/xml; charset=utf-8",
        )

    @app.after_request
    def litefeet_noindex_private_pages(response):
        # Do not advertise administrative, beta or confirmation screens.
        path = request.path
        restricted = (
            path == "/admin" or path.startswith("/admin/")
            or path == "/beta" or path.startswith("/beta/")
            or path == "/newsletter" or path.startswith("/newsletter/")
            or path == "/health" or path.startswith("/health/")
            or path in {"/submit/thank-you", "/awards/litefeet-awards/submit"}
            or path.endswith("/check-email")
        )
        if restricted or request.method == "POST" and "text/html" in response.content_type.lower():
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response
