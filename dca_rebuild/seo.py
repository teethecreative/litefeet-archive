"""The LiteFeet Vault public search metadata, crawl directives and XML sitemap."""
import re
from xml.sax.saxutils import escape
from flask import Response, request

SITE_URL = "https://thelitefeetvault.com"
PAGES = {
    "/": (
        "The LiteFeet Vault | LiteFeet Culture & History",
        "Discover the people, history and creativity of LiteFeet in a living cultural archive built to preserve the culture.",
    ),
    "/awards/dancers-choice/2026": (
        "Dancer's Choice Awards 2026 | The LiteFeet Vault",
        "Follow the 2026 Dancer's Choice Awards, from community category selection to nominations, voting and official results on The LiteFeet Vault.",
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
        "Explore recorded category-selection results and updates for the 2026 Dancer's Choice Awards. Results remain subject to final review.",
    ),
}
PAGES.update({
    "/archive/lock-in": ("Lock In | The LiteFeet Card Battle Game", "Learn the rules, browse sample decks, play a practice round and contribute to the LiteFeet card game."),
    "/submit": ("Submit a Battle, Lab, Link-Up or Class | The LiteFeet Vault",
                "Submit an upcoming battle, lab session, link-up, workshop, class or community gathering for review on The LiteFeet Vault."),
    "/submit/thank-you": ("Submission Received | The LiteFeet Vault", "Your community gathering has been submitted for review."),
    "/archive": ("The Archive | The LiteFeet Vault", "Browse LiteFeet historical research, original battle announcements, moves, events, dancer references and preserved award records."),
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

    "/awards/dancers-choice/nominations": ("DCA 2026 Nominations | The LiteFeet Vault", "Explore the categories and nominate the people who represent LiteFeet culture."),
})

# Only advertise curated public entry points. Some linked pages are unfinished.
SITEMAP_PATHS = (
    "/",
    "/archive/lock-in",
    "/archive",
    "/archive/timeline",
    "/awards",
    "/awards/dancers-choice",
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
    "/awards/dancers-choice/category-suggestions",
    "/awards/dancers-choice/category-voting",
)


def metadata_for_path(path, view=None):
    record = PAGES.get(path)
    if record is None:
        match = re.fullmatch(r"/awards/litefeet-awards/(2023|2024|2025|2026)", path)
        if match:
            year = match.group(1)
            record = (
                f"LiteFeet Awards {year} Archive | The LiteFeet Vault",
                f"Explore the LiteFeet Awards {year} archive and its preserved awards history on The LiteFeet Vault.",
            )
    if record is None and path.startswith("/archive/records/"):
        from dca_rebuild.archive_catalog import find_record
        item = find_record(path[len("/archive/records/"):])
        if item:
            record = (
                item["title"] + " | The LiteFeet Vault Archive",
                ("Research under review: " + item["summary"])[:200],
            )
    if record is None:
        return None
    results = path == '/awards/dancers-choice/nominations' and view == 'results'
    if results:
        record = ("DCA 2026 Nominee Standings | The LiteFeet Vault",
                  "See current Dancer’s Choice Awards 2026 nominees and nomination totals across every category on The LiteFeet Vault.")
    title, description = record
    canonical = SITE_URL + path + ('?view=results' if results else '')
    image_url = SITE_URL + '/static/social/dca-2026-standings-v1.png' if results else None
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
            "image": image_url, "image_alt": "The LiteFeet Vault — Dancer’s Choice Awards 2026 nominee standings" if results else None}


def register_seo(app):
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
        entries = "".join(
            "<url><loc>" + escape(SITE_URL + path) + "</loc></url>"
            for path in SITEMAP_PATHS
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
        )
        if restricted or request.method == "POST" and "text/html" in response.content_type.lower():
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response
