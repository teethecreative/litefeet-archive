"""Music batch import must remain additive and preserve missing metadata."""
from dca_rebuild.music_batch_catalog import batch_catalog, batch_record, combined_releases
from dca_rebuild.music_public import full_date, music_duration


def test_uploaded_catalog_has_all_unique_rows():
    records = batch_catalog()
    assert len(records) == 87
    assert len([x for x in records if x["kind"] == "track"]) == 77
    assert len([x for x in records if x["kind"] == "project"]) == 10
    assert len({(x["kind"], x["catalog_id"]) for x in records}) == 87


def test_preserves_exact_and_unknown_release_metadata():
    track = batch_record("track", "music-b1-001")
    assert track["title"] == "CRAZY CEE x BIG SHOW"
    assert track["release_date"] == ""
    assert track["duration"] == "2:05"
    assert track["playable_url"] == ""
    album = batch_record("project", "gangsta-tunez")
    assert album["title"] == "Gangsta Tunez"
    assert full_date(album["release_date"]) == "July 19, 2025"
    assert album["expected_track_count"] == "7"


def test_existing_published_rows_are_kept_and_batch_is_not_duplicated():
    existing = [
        {"id": 123, "media_type": "music_release", "title": "CRAZY CEE x BIG SHOW",
         "artist_or_creator": "THIS IS PRETTY SMART", "release_date": "", "url": "https://example.org/a"},
        {"id": 124, "media_type": "music_release", "title": "Older existing record",
         "artist_or_creator": "Older artist", "release_date": "2020-05-13", "url": "https://example.org/b"},
    ]
    output = combined_releases(existing, full_date, music_duration)
    assert len(output) == 95  # 87 original catalog rows + seven new Yaffi records, one duplicate suppressed
    assert sum(row["title"] == "CRAZY CEE x BIG SHOW" for row in output) == 1
    assert any(row.get("id") == 124 and row["record_href"].endswith("/124") for row in output)
    assert any(row["catalog_id"] == "music-b1-001" for row in batch_catalog())
    assert any(row["kind"] == "project" and row["title"] == "Gangsta Tunez" for row in output)


def test_project_association_and_duration_precision():
    tracks = [row for row in batch_catalog()
              if row["kind"] == "track" and row.get("project_id") == "gangsta-tunez"]
    assert len(tracks) == 7
    assert music_duration(tracks[0]) == "2:45"
    undated = next(row for row in combined_releases([], full_date, music_duration)
                   if row["catalog_id"] == "music-b1-001")
    assert undated["date_label"] == "Date unknown"
    assert undated["duration_label"] == "2:05"
