"""404 navigation and legacy URL behavior; no production writes."""
import importlib

from dca_rebuild.archive_catalog import find_record
from dca_rebuild.legacy_profile_routes import legacy_dancer_destination


def test_known_historical_links_resolve_to_existing_records():
    for slug in ("splashocean", "teeth", "kari", "flight", "mysteryman"):
        destination = "/archive/records/legacy-" + slug
        assert legacy_dancer_destination("/people/dancers/" + slug) == destination
        assert legacy_dancer_destination("/dancers/" + slug) == destination
        assert find_record("legacy-" + slug) is not None


def test_unknown_urls_show_one_helpful_404_page(website):
    # Use the real registered error handler, not only the isolated route fixture.
    app = importlib.import_module("dca_rebuild.app").app
    client = app.test_client()
    for path in (
        "/people/dancers/not-a-real-dancer-404",
        "/dancers/not-a-real-dancer-404",
        "/events/unknown-event-404",
        "/music/not-a-record-404",
        "/completely-missing-404",
    ):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 404, path
        assert "noindex" in response.headers.get("X-Robots-Tag", "")
        html = response.get_data(as_text=True)
        assert "This URL doesn't exist." in html
        assert "What were you looking for?" in html
        for href in ("/archive/people", "/archive", "/litefeet-music", "/calendar", "/awards", "/"):
            assert 'href="' + href + '"' in html
        assert "/people/dancers/not-a-real-dancer-404" not in response.headers.get("Location", "")


def test_preserved_historical_urls_do_not_go_to_homepage(website):
    app = importlib.import_module("dca_rebuild.app").app
    client = app.test_client()
    for slug in ("splashocean", "teeth"):
        response = client.get("/people/dancers/" + slug, follow_redirects=False)
        assert response.status_code == 301
        assert response.headers["Location"] == "/archive/records/legacy-" + slug
        assert client.get(response.headers["Location"]).status_code == 200
