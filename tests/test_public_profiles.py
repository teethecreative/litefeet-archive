"""Starter profiles only aggregate records already public in the archive."""
from types import SimpleNamespace

from dca_rebuild.archive_2023 import ArchiveCategory, ArchiveNominee
from dca_rebuild.public_profiles import (PublicProfileIndex, matchup_participants,
                                        eligible_historian_contributor)


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


def test_event_and_song_awards_do_not_create_fake_people():
    historical = [
        ArchiveCategory(id="best-event-2023", name="Best Event 2023",
                        nominees=(ArchiveNominee("Body Bag 2", True),)),
        ArchiveCategory(id="battle-song", name="Battle Song of the Year",
                        nominees=(ArchiveNominee("Track Title", True),)),
    ]
    index = PublicProfileIndex([], historical, [], [])
    assert index.href("Body Bag 2") is None
    assert index.href("Track Title") is None


def test_team_profile_has_dedicated_undocumented_fields():
    current = [{"name": "Best Team", "href": "/awards/dancers-choice/2026",
                "nominees": [{"name": "Team Demon"}]}]
    index = PublicProfileIndex([], [], current, [])
    team = index.by_name("Team Demon")
    assert team["is_team"] is True
    assert team["team_details"] == {
        "founded": "", "founders": [], "current_roster": [], "former_roster": [],
    }
    assert index.by_name("Nobody") is None


def test_team_founders_and_roster_only_link_exact_profiles():
    records = [
        dict(slug="team-demon", title="Team Demon", collection="people",
             record_type="team", team_details={
                 "founded": "2012",
                 "founders": ["Kid Smoove"],
                 "current_roster": [{"name": "Flii Boogie", "role": "Member"}],
                 "former_roster": ["Unlisted Person"],
             }),
        dict(slug="kid-smoove", title="Kid Smoove", collection="people"),
        dict(slug="flii-boogie", title="Flii Boogie", collection="people"),
    ]
    index = PublicProfileIndex(records, [], [], [])
    team = index.for_archive_record("team-demon")
    assert team["is_team"] is True
    assert team["team_details"]["founded"] == "2012"
    assert team["team_details"]["founders"][0]["href"] == "/people/kid-smoove"
    assert team["team_details"]["current_roster"][0]["href"] == "/people/flii-boogie"
    assert "href" not in team["team_details"]["former_roster"][0]
    assert index.by_name("Kid Smoove")["is_team"] is False


def test_judge_is_secondary_and_lists_only_advertised_event_appearances():
    records = [
        dict(slug="dancer-a", title="Dancer A", collection="people",
             record_type="dancer_profile"),
        dict(slug="event-one", title="Body Bag 2026", collection="events",
             date="2026-10-01", date_label="October 1, 2026",
             information=[("Judges", "Dancer A, Unlisted Judge")],
             battles=[{"items": ["Dancer A vs Another Dancer"]}],
             lineup_participants=[]),
    ]
    index = PublicProfileIndex(records, [], [], [])
    dancer = index.for_archive_record("dancer-a")
    assert [badge["key"] for badge in dancer["badges"]] == ["dancer", "judge"]
    judging = next(badge for badge in dancer["badges"] if badge["key"] == "judge")
    assert len(judging["rows"]) == 1
    assert judging["rows"][0]["title"] == "Body Bag 2026"
    assert "specific battles unconfirmed" in judging["rows"][0]["detail"]
    assert "Another Dancer" not in judging["rows"][0]["detail"]


def test_judge_role_alone_cannot_create_standalone_judge_page():
    records = [dict(slug="person", title="Someone", collection="people",
                    profile_roles=["Judge"], record_type="person")]
    index = PublicProfileIndex(records, [], [], [])
    entry = index.for_archive_record("person")
    assert entry["badges"] == []
    assert "judge" not in entry["roles"]


def test_historian_not_inferred_from_archive_mentions_or_legacy_roles():
    records = [
        dict(slug="legacy", title="Historian Name", collection="people",
             record_type="legacy_identity", profile_roles=["Historian"],
             information=[("Original role labels (unverified)", "Historian")]),
        dict(slug="person", title="Archivist", collection="people",
             record_type="dancer_profile", profile_roles=["Historian"]),
    ]
    index = PublicProfileIndex(records, [], [], [])
    assert index.for_archive_record("legacy")["badges"] == []
    assert "historian" not in index.for_archive_record("person")["roles"]


def test_source_supported_role_overlaps_do_not_duplicate_identity():
    records = [dict(slug="person", title="DJ Creator", collection="people",
                    record_type="dancer_profile", profile_roles=[
                        "Producer", "DJ", "Host", "Videographer", "Educator"],
                    role_records={"producer": [
                        {"title": "Documented beat", "href": "/music/example",
                         "detail": "Released 2024"}]})]
    index = PublicProfileIndex(records, [], [], [])
    profile = index.for_archive_record("person")
    keys = [badge["key"] for badge in profile["badges"]]
    assert keys == ["dancer", "producer", "dj", "host", "videographer", "educator"]
    assert next(b for b in profile["badges"] if b["key"] == "producer")["rows"][0]["href"] == "/music/example"


def test_award_category_does_not_create_unearned_judging_or_historian_badges():
    categories = [{"name": "Best Team", "nominees": [{"name": "Team Demon"}]},
                  {"name": "Producer of the Year", "nominees": [{"name": "Sound Wave"}]}]
    index = PublicProfileIndex([], [], categories, [])
    assert [b["key"] for b in index.by_name("Team Demon")["badges"]] == ["team"]
    assert [b["key"] for b in index.by_name("Sound Wave")["badges"]] == ["producer"]


def test_historian_requires_verified_account_approved_contribution_and_no_archive_identity():
    assert eligible_historian_contributor(
        approved_contributions=1, account_verified=True, has_archival_mention=False)
    assert not eligible_historian_contributor(
        approved_contributions=0, account_verified=True, has_archival_mention=False)
    assert not eligible_historian_contributor(
        approved_contributions=3, account_verified=False, has_archival_mention=False)
    assert not eligible_historian_contributor(
        approved_contributions=3, account_verified=True, has_archival_mention=True)


def test_people_search_finds_nomination_only_team():
    from dca_rebuild.people_discovery import find_profiles
    current = [{"name": "Best Team",
                "nominees": [{"name": "Team Demon"}, {"name": "2 Live Krew"}]}]
    index = PublicProfileIndex([], [], current, [])
    results = find_profiles(index, query="TEAM DEMON")
    assert results["count"] == 1
    assert results["items"][0]["href"] == "/people/team-demon"
    assert results["items"][0]["is_team"] is True


def test_people_search_includes_archive_and_nomination_only_profiles():
    from dca_rebuild.people_discovery import find_profiles
    records = [dict(slug="person-old", title="Old School Dancer",
                    collection="people", record_type="dancer_profile")]
    current = [{"name": "Best Team", "nominees": [{"name": "Team Demon"}]}]
    index = PublicProfileIndex(records, [], current, [])
    results = find_profiles(index, page_size=8)
    assert results["count"] == 2
    assert {row["href"] for row in results["items"]} == {
        "/people/old-school-dancer", "/people/team-demon"
    }
    assert find_profiles(index, query="not a real dancer")["count"] == 0


def test_people_cloud_links_award_nominees_to_profiles():
    from dca_rebuild.people_discovery import nominee_people_cloud
    current = [{"name": "Most Improved", "nominees": [
        {"name": "XO Wavy"}, {"name": "Kid Smoove"}]}]
    index = PublicProfileIndex([], [], current, [])
    cloud = nominee_people_cloud(index, [], limit=8)
    assert {row["href"] for row in cloud} == {
        "/people/xo-wavy", "/people/kid-smoove"
    }
    assert all(row["is_nominee"] for row in cloud)
