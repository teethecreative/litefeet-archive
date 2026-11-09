"""Non-destructive addition of sourced Yaffi Tune 2026 music."""
from dca_rebuild.music_batch_catalog import (
    batch_catalog, yaffi_catalog, all_music_catalog, batch_record, combined_releases
)
from dca_rebuild.music_public import full_date, music_duration


def test_yaffi_addition_preserves_original_batch():
    assert len(batch_catalog()) == 87
    assert len(yaffi_catalog()) == 7
    assert len(all_music_catalog()) == 94
    assert len({(r["kind"], r["catalog_id"]) for r in all_music_catalog()}) == 94


def test_yaffi_sources_and_metadata_are_preserved():
    single = batch_record("track", "yaffi-2026-pun-lock")
    assert single["title"] == "Pun (Lock)"
    assert full_date(single["release_date"]) == "April 11, 2026"
    assert single["duration"] == ""  # Rounded project duration is not track duration
    assert single["playable_url"] == ""  # Provider page links are not direct audio
    project = batch_record("project", "yaffi-2026-death-of-a-reaper")
    assert project["title"] == "Death Of A Reaper"
    tracks = [r for r in all_music_catalog()
              if r["kind"] == "track" and r.get("project_id") == project["catalog_id"]]
    assert len(tracks) == 5
    assert [t["duration"] for t in tracks] == ["3:01", "2:43", "2:51", "3:03", "2:42"]


def test_yaffi_releases_appear_without_replacing_existing_records():
    existing = [{"id": 345, "title": "Unrelated archived song",
                 "artist_or_creator": "Historic artist", "release_date": "2014-01-01"}]
    releases = combined_releases(existing, full_date, music_duration)
    assert len(releases) == 95
    assert any(r.get("id") == 345 for r in releases)
    assert any(r.get("catalog_id") == "yaffi-2026-pun-lock" for r in releases)
    assert all(not row.get("playable_url") for row in yaffi_catalog())


def test_yaffi_music_record_pages_have_canonical_seo(website):
    client = website.test_client()
    response = client.get("/litefeet-music/catalog/track/yaffi-2026-pun-lock")
    assert response.status_code == 200
    assert "Pun (Lock)" in response.get_data(as_text=True)
    assert 'rel="canonical"' in response.get_data(as_text=True)
    project = client.get("/litefeet-music/catalog/project/yaffi-2026-death-of-a-reaper")
    assert project.status_code == 200
    html = project.get_data(as_text=True)
    assert "Wine &amp; Dine" in html or "Wine & Dine" in html
    sitemap = client.get("/sitemap.xml").get_data(as_text=True)
    assert "/music/" in sitemap
    assert "/music/" in sitemap
