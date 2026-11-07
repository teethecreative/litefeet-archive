"""Public recovered-name index: reversible duplicate consolidation and source safety."""
from dca_rebuild.archive_catalog import all_records, browse, find_record
from dca_rebuild.archive_recovery import recovery_candidates


def test_legacy_source_preservation_and_name_only_publication():
    source = recovery_candidates()
    assert len(source) == 138
    assert len({r["source_id"] for r in source}) == 138
    published = [r for r in all_records() if r["source_kind"] == "legacy_name"]
    assert len(published) == 133  # 135 unique names; Mr YouTube & Kid The Wiz already researched
    assert len({r["slug"] for r in published}) == len(published)
    assert not any("ghost" in r["description"].lower() for r in published)
    assert not any("email" in r or "team_affiliation" in r for r in published)
    assert all(r["can_verify"] is False for r in published)


def test_three_duplicate_name_groups_one_public_entry_each():
    records = [r for r in all_records() if r["source_kind"] == "legacy_name"]
    for name, expected_ids in [
        ("Venom", "29, 112"),
        ("BSNYEA", "11, 118"),
        ("PRockz", "12, 135"),
    ]:
        matches = [r for r in records if r["title"] == name]
        assert len(matches) == 1, name
        assert matches[0]["information"][0] == ("Preserved source IDs", expected_ids)
    assert find_record("legacy-prockz") is not None
    assert "P Rockz" in find_record("legacy-prockz")["search"] or "p rockz" in find_record("legacy-prockz")["search"]


def test_public_search_and_profile_pages_without_private_claims(website):
    client = website.test_client()
    names = client.get("/archive/api/records?collection=people&q=Matt+Live").get_json()
    assert names["total"] >= 1
    assert any(r["title"] == "Matt Live" for r in names["records"])
    profile = client.get("/archive/records/legacy-mattlive")
    assert profile.status_code == 200
    html = profile.get_data(as_text=True)
    assert "Recovered historical name" in html
    assert "Biographical details and affiliations have not been verified." in html
    assert "This is a ghost profile" not in html
    assert "Community verification" not in html


def test_known_research_profiles_not_duplicated():
    records = all_records()
    assert len([r for r in records if r["title"] in ("Mr YouTube", "Mr. YouTube")]) == 1
    assert len([r for r in records if r["title"] == "Kid The Wiz"]) == 0
    assert find_record("research-mr-youtube") is not None
    assert find_record("research-kid-the-wiz-randy-vargas") is not None
