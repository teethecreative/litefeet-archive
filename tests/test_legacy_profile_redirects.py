"""Regression coverage for old URLs discovered in Google Search Console.

Tests use the app's disposable test database and public historical catalog;
they never mutate production profile records or nomination data.
"""
from dca_rebuild.archive_catalog import find_record
from dca_rebuild.legacy_profile_routes import (
    legacy_dancer_destination, preserved_profile_redirects,
)


def test_preserved_legacy_profiles_have_verified_public_destinations():
    mapping = preserved_profile_redirects()
    expected = {
        "splashocean": "legacy-splashocean",
        "teeth": "legacy-teeth",
        "kari": "legacy-kari",
        "flight": "legacy-flight",
        "mysteryman": "legacy-mysteryman",
    }
    for old_slug, new_slug in expected.items():
        destination = "/archive/records/" + new_slug
        assert mapping[old_slug] == destination
        assert find_record(new_slug) is not None
        assert legacy_dancer_destination("/people/dancers/" + old_slug) == destination
        assert legacy_dancer_destination("/dancers/" + old_slug) == destination


def test_old_dancer_links_redirect_to_matching_archived_records(website):
    client = website.test_client()
    for slug in ("splashocean", "teeth", "kari", "flight", "mysteryman"):
        for prefix in ("/people/dancers/", "/dancers/"):
            result = client.get(prefix + slug, follow_redirects=False)
            assert result.status_code == 301, (slug, result.status_code)
            destination = result.headers["Location"]
            assert destination == "/archive/records/legacy-" + slug
            page = client.get(destination)
            assert page.status_code == 200
            assert 'href="/archive/people"' in page.get_data(as_text=True) or "The LiteFeet Vault" in page.get_data(as_text=True)


def test_unknown_profiles_are_not_redirected_to_unrelated_homepage(website):
    client = website.test_client()
    for path in (
        "/people/dancers/this-name-does-not-exist",
        "/dancers/this-name-does-not-exist",
    ):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 404, path
    assert client.get("/archive/people").status_code == 200


def test_no_historical_data_changes_for_redirects(website):
    from dca_rebuild.archive_recovery import recovery_candidates
    before = tuple((r["source_id"], r["legacy_slug"]) for r in recovery_candidates())
    client = website.test_client()
    client.get("/people/dancers/splashocean")
    client.get("/people/dancers/teeth")
    assert before == tuple((r["source_id"], r["legacy_slug"]) for r in recovery_candidates())
