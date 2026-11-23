"""Starter profiles only aggregate records already public in the archive."""
from types import SimpleNamespace

from dca_rebuild.archive_2023 import ArchiveCategory, ArchiveNominee
from dca_rebuild.public_profiles import PublicProfileIndex, matchup_participants


def test_announced_matchup_parser_requires_explicit_sides():
    assert matchup_participants("Kid Smoove vs Flii Boogie") == ("Kid Smoove", "Flii Boogie")
    assert matchup_participants("Tyke Star & X Lyve vs Noah Lot & Red Ink") == (
        "Tyke Star", "X Lyve", "Noah Lot", "Red Ink")
    assert matchup_participants("Body Bag Cypher") == ()


def test_lfa_winner_dca_history_and_battle_listing_share_one_profile():
    records = [
        dict(slug="person-kid-smoove", title="Kid Smoove", collection="people"),
        dict(slug="battle-card", title="The Body Baggers Vol. 2",
             collection="events", date="2023-05-27", date_label="May 27, 2023",
             battles=[{"section": "Announced battle card",
                       "items": ["Flii Boogie vs Kid Smoove"]}],
             lineup_participants=[]),
    ]
    historical = [ArchiveCategory(
        id="best-trickster", name="Best Trickster",
        nominees=(ArchiveNominee("Kid Smoove", True),
                  ArchiveNominee("Flii Boogie", False)))]
    current = [{
        "name": "Most Consistent", "href": "/awards/2026/most-consistent",
        "nominees": [{"name": "Kid Smoove"}],
    }]
    winners = [SimpleNamespace(year=2026, category_name="I Am the Lite",
                               person_name="Kid Smoove")]
    index = PublicProfileIndex(records, historical, current, winners)
    entry = index.by_name("kid smoove")
    assert entry["href"] == "/people/kid-smoove"
    assert len(entry["wins"]) == 2
    assert any(win["program"] == "LiteFeet Awards" for win in entry["wins"])
    assert len(entry["nominations"]) == 1
    assert entry["nominations"][0]["provisional"] is True
    assert len(entry["battles"]) == 1
    assert entry["battles"][0]["status"].startswith("Announced")
    assert index.for_archive_record("person-kid-smoove") is entry


def test_dynamic_profile_does_not_claim_unlisted_battle_or_implicit_win():
    records = [dict(slug="event-one", title="Event", collection="events",
                    date="", date_label="Date unconfirmed",
                    battles=[{"items": ["Another Dancer vs Someone Else"]}],
                    lineup_participants=[])]
    current = [{"name": "Most Improved", "href": "/awards/2026/most-improved",
                "nominees": [{"name": "XO Wavy"}]}]
    index = PublicProfileIndex(records, [], current, [])
    profile = index.by_name("XO Wavy")
    assert profile["href"] == "/people/xo-wavy"
    assert index.by_slug("xo-wavy") is profile
    assert not profile["wins"]
    assert not profile["battles"]
    assert len(profile["nominations"]) == 1


def test_ambiguous_published_identities_are_never_automatically_merged():
    records = [
        dict(slug="first", title="Same Name", collection="people"),
        dict(slug="second", title="Same Name", collection="people"),
    ]
    current = [{"name": "Category", "href": "/awards/2026/category",
                "nominees": [{"name": "Same Name"}]}]
    index = PublicProfileIndex(records, [], current, [])
    assert index.href("Same Name") is None
    assert index.for_archive_record("first")["nominations"] == []
    assert index.for_archive_record("second")["nominations"] == []
