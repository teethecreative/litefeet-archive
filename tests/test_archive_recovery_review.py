"""Historical identity recovery keeps original rows and prevents ghost publishing."""
from dca_rebuild.archive_catalog import all_records, people_crew_cloud
from dca_rebuild.archive_recovery import recovery_candidates, recovery_review


def test_all_preserved_ids_and_safe_fields():
    entries = recovery_candidates()
    assert len(entries) == 138
    assert len({e["source_id"] for e in entries}) == 138
    assert len({e["legacy_slug"] for e in entries}) == 138
    assert all(set(e) == {"source_id", "name", "legacy_slug", "reported_roles"}
               for e in entries)
    assert all(e["name"] and e["legacy_slug"] for e in entries)
    # Generated ghost biographies and asserted crew affiliation are excluded.
    assert not any("bio" in e or "team_affiliation" in e or "email" in e
                   for e in entries)


def test_duplicate_review_groups_keep_separate_ids():
    review = recovery_review(all_records())
    by_name = {}
    for row in review:
        by_name.setdefault(row["name"].casefold().replace(" ", ""), []).append(row)
    assert sorted(row["source_id"] for row in by_name["venom"]) == [29, 112]
    assert sorted(row["source_id"] for row in by_name["bsnyea"]) == [11, 118]
    assert sorted(row["source_id"] for row in by_name["prockz"]) == [12, 135]
    assert all(row["duplicate_name_count"] == 2 for key in
               ("venom", "bsnyea", "prockz") for row in by_name[key])


def test_existing_public_profiles_are_hints_not_automatic_merges():
    matches = recovery_review(all_records())
    mr_youtube = next(row for row in matches if row["name"] == "Mr YouTube")
    assert any("mr-youtube" in p["slug"] for p in mr_youtube["possible_public_matches"])
    assert all(row["review_status"] == "Identity review required" for row in matches)


def test_recovery_stage_not_auto_published_to_public_catalog_or_wordcloud():
    public = {r["slug"] for r in all_records()}
    recovered = {r["legacy_slug"] for r in recovery_candidates()}
    assert "mattlive" in recovered
    assert "mattlive" not in public
    assert "mattlive" not in {e["slug"] for e in people_crew_cloud()}
