from dca_rebuild.music_public import full_date, music_duration


def test_release_date_uses_full_month_name():
    assert full_date("2026-07-25") == "July 25, 2026"
    assert full_date("2025-06-16") == "June 16, 2025"
    assert full_date("2026-03") == "March 2026"
    assert full_date("2026") == "2026"
    assert full_date(None) == "Date unknown"


def test_duration_is_only_reported_when_known():
    assert music_duration({"duration": "2:45"}) == "2:45"
    assert music_duration({"duration_seconds": 125}) == "2:05"
    assert music_duration({"duration": None}) == "—"
    assert music_duration({}) == "—"


def test_display_cleanup_keeps_original_source_metadata():
    from dca_rebuild.music_presentation import with_release_display, duplicate_release_candidates
    item = {
        "id": 1, "title": "JELLYFISH JAM Listen to JELLYFISH JAM by Pretty Smart",
        "description": "Uploaded by artist.", "artist_or_creator": "Pretty Smart",
        "url": "https://soundcloud.com/pretty-smart/jellyfish", "release_date": "2026-06-14"
    }
    row = with_release_display(item)
    assert row["display_title"] == "JELLYFISH JAM"
    assert "Listen to JELLYFISH JAM" in row["display_description"]
    assert row["title"].endswith("Pretty Smart")
    assert item["description"] == "Uploaded by artist."
    assert item["title"].startswith("JELLYFISH JAM Listen")


def test_duplicate_candidates_are_review_only_and_do_not_hide_records():
    from dca_rebuild.music_presentation import duplicate_release_candidates
    original = [
        {"id": 50, "title": "im outside", "artist_or_creator": "DSparkz",
         "release_date": "2026-06-16", "url": "https://soundcloud.com/dsparkz/im-outside"},
        {"id": 51, "title": "im outside", "artist_or_creator": "DSparkz",
         "release_date": "2026-06-16", "url": "https://soundcloud.com/dsparkz/im-outside?utm_source=share"},
        {"id": 52, "title": "im outside (Remix)", "artist_or_creator": "DSparkz",
         "release_date": "2026-06-16", "url": "https://soundcloud.com/dsparkz/im-outside"},
    ]
    candidates = duplicate_release_candidates(original)
    assert len(candidates) == 1
    assert candidates[0]["record_ids"] == [50, 51]
    assert len(original) == 3
    assert original[1]["title"] == "im outside"


def test_music_release_table_keeps_columns_and_non_destructive_display(website):
    client = website.test_client()
    listing = client.get("/litefeet-music")
    assert listing.status_code == 200
    html = listing.get_data(as_text=True)
    assert "Song Name" in html and "Description" in html
    assert "Duration" in html and "Listen / Source" in html
    assert "lfv-music-table" in html
