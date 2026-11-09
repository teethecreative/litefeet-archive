"""Non-mutating coverage for readable public URL resolution and collisions."""
from dca_rebuild.public_urls import (
    slugify, person_href, person_by_slug, music_href, music_by_slugs,
    event_href, event_by_slugs, category_href, nominee_href,
)


def test_slugify_is_readable_and_does_not_include_query_strings():
    assert slugify("Jo Smooth's Good One!") == "jo-smooth-s-good-one"
    assert slugify("  Lét's Lab @ ARC  ") == "let-s-lab-arc"


def test_people_get_short_urls_only_when_names_are_unambiguous():
    records = [
        {"slug": "legacy-splashocean", "title": "Splashocean", "collection": "people"},
        {"slug": "legacy-teeth", "title": "Teeth", "collection": "people"},
    ]
    assert person_href(records[0], records) == "/people/splashocean"
    assert person_by_slug("splashocean", records) == records[0]
    same = records + [{"slug": "another-splashocean", "title": "Splashocean", "collection": "people"}]
    assert person_by_slug("splashocean", same) is None
    assert person_href(records[0], same) == "/archive/records/legacy-splashocean"


def test_music_slug_uses_artist_and_title_and_avoids_collisions():
    a = {"title": "Bounce Back", "artist_or_creator": "Producer A",
         "record_href": "/litefeet-music/catalog/track/source-A"}
    b = {"title": "Bounce Back", "artist_or_creator": "Producer B",
         "record_href": "/litefeet-music/catalog/track/source-B"}
    assert music_href(a, [a, b]) == "/music/producer-a/bounce-back"
    assert music_by_slugs("producer-b", "bounce-back", [a, b]) == b
    duplicate = dict(a, record_href="/litefeet-music/catalog/track/source-C")
    assert music_href(a, [a, b, duplicate]) == a["record_href"]


def test_calendar_occurrences_and_collisions_do_not_lose_identity():
    a = {"date": "2026-11-20", "title": "Let's Lab", "href": "/calendar/events/2026-11-20/let-s-lab"}
    b = {"date": "2026-11-21", "title": "Let's Lab", "href": "/calendar/events/2026-11-21/let-s-lab"}
    assert event_href(a, [a, b]) == "/events/let-s-lab/2026-11-20"
    assert event_by_slugs("let-s-lab", "2026-11-21", [a, b]) == b
    duplicate = dict(a, href="/calendar/events/2026-11-20/let-s-lab-123")
    assert event_href(a, [a, b, duplicate]) == a["href"]


def test_category_and_nominee_slugs_use_source_ids_only_for_ambiguous_names():
    a = {"id": 12, "name": "Most Consistent Dancer",
         "nominees": [{"id": 55, "name": "Smooth"}, {"id": 56, "name": "Rev Up"}]}
    b = {"id": 13, "name": "Producer of the Year", "nominees": []}
    assert category_href(a, [a, b]) == "/awards/2026/most-consistent-dancer"
    assert nominee_href(a, a["nominees"][0], [a, b]) == (
        "/awards/2026/most-consistent-dancer/smooth"
    )
    duplicate = {"id": 99, "name": a["name"], "nominees": []}
    assert "category=12" in category_href(a, [a, b, duplicate])
    another = dict(a["nominees"][0], id=57)
    assert "suggestion=55" in nominee_href(dict(a, nominees=a["nominees"]+[another]),
                                            a["nominees"][0], [a, b])
