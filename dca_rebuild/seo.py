"""LiteFeet Ledger public search metadata, crawl directives and XML sitemap."""
import re
from xml.sax.saxutils import escape
from flask import Response, request

SITE_URL = "https://thelitefeetvault.com"
PAGES = {
    "/": (
        "LiteFeet Ledger | LiteFeet Dance History & Awards",
        "Explore LiteFeet dance culture, history, and community awards. Follow the Dancer's Choice Awards and help preserve the legacy of Harlem's LiteFeet movement.",
    ),
    "/awards/dancers-choice/2026": (
        "Dancer's Choice Awards 2026 | LiteFeet Ledger",
        "Follow the 2026 Dancer's Choice Awards, from community category selection to nominations, voting and official results on LiteFeet Ledger.",
    ),
    "/awards/dancers-choice/2023": (
        "Dancer's Choice Awards 2023 Archive | The LiteFeet Vault",
        "Explore the August 2023 Dancer's Choice Awards archive: 31 award categories, 152 nominee entries and 32 recorded winning entries.",
    ),
    "/awards/litefeet-awards": (
        "LiteFeet Awards History & Results | LiteFeet Ledger",
        "Explore the LiteFeet Awards historical archive and contribute information about past categories, winners and honorees for verification.",
    ),
    "/awards/hypeitup": (
        "HypeItUpTV Awards | LiteFeet Ledger",
        "Find updates about the HypeItUpTV Awards, a developing section of the LiteFeet Ledger awards archive.",
    ),
    "/awards/dancers-choice/category-suggestions": (
        "Dancer's Choice 2026 Category Suggestions | LiteFeet Ledger",
        "Review the Dancer's Choice Awards 2026 category-suggestion stage and learn how the community helps shape the award categories.",
    ),
    "/awards/dancers-choice/category-voting": (
        "Dancer's Choice 2026 Category Results | LiteFeet Ledger",
        "Explore recorded category-selection results and updates for the 2026 Dancer's Choice Awards. Results remain subject to final review.",
    ),
}
# Only advertise curated public entry points. Some linked pages are unfinished.
SITEMAP_PATHS = (
    "/",
    "/awards/dancers-choice/2026",
    "/awards/dancers-choice/2023",
    "/awards/litefeet-awards",
    "/awards/dancers-choice/category-suggestions",
    "/awards/dancers-choice/category-voting",
)


def metadata_for_path(path):
    record = PAGES.get(path)
    if record is None:
        match = re.fullmatch(r"/awards/litefeet-awards/(2023|2024|2025|2026)", path)
        if match:
            year = match.group(1)
            record = (
                f"LiteFeet Awards {year} Archive | LiteFeet Ledger",
                f"Explore the LiteFeet Awards {year} archive and its preserved awards history on LiteFeet Ledger.",
            )
    if record is None:
        return None
    title, description = record
    canonical = SITE_URL + path
    website = {"@type": "WebSite", "name": "LiteFeet Ledger", "url": SITE_URL + "/"}
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
    return {"title": title, "description": description, "canonical": canonical, "schema": schema}


def register_seo(app):
    @app.context_processor
    def litefeet_seo_context():
        return {"seo": metadata_for_path(request.path)}

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
