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


def test_separate_track_source_artist_profile_without_creating_false_choices():
    from dca_rebuild.music_presentation import with_release_display
    artist = "https://soundcloud.com/pretty-smart-261171146"
    track = {"title": "JELLYFISH JAM", "url": artist, "source_profile_url": artist,
             "needs_exact_track_url": True}
    row = with_release_display(track)
    assert row["source_destination"] == ""
    assert row["artist_profile_destination"] == artist
    assert track["url"] == artist  # source metadata never rewritten
    valid = with_release_display({"title": "Test", "url": "https://example.com/track",
                                  "source_profile_url": "https://example.com/artist"})
    assert valid["source_destination"] == "https://example.com/track"
    assert valid["artist_profile_destination"] == "https://example.com/artist"
    blocked = with_release_display({"title": "Test", "url": "javascript:alert(1)",
                                    "source_profile_url": "data:text/html,hi"})
    assert blocked["source_destination"] == ""
    assert blocked["artist_profile_destination"] == ""


def test_release_radar_track_title_opens_choice_and_preserves_details(website):
    client = website.test_client()
    response = client.get("/litefeet-music?q=JELLYFISH")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-music-track-choice' in html
    assert 'id="lfv-music-choice"' in html
    assert 'Where would you like to go?' in html
    assert 'Original source' in html and 'Artist profile' in html
    assert 'View record details on The LiteFeet Vault' in html
    assert 'data-source-url=""' in html  # batch SoundCloud profile is not a track URL
    assert 'data-artist-url="https://soundcloud.com/pretty-smart-261171146"' in html
    assert 'class="lfv-music-source lfv-music-source-choice"' in html
    assert '/litefeet-music/catalog/track/' in html


def test_record_detail_keeps_original_external_links(website):
    from dca_rebuild.music_batch_catalog import batch_catalog
    item = next(x for x in batch_catalog() if x["kind"] == "track" and x["needs_exact_track_url"])
    response = website.test_client().get(
        "/litefeet-music/catalog/track/" + item["catalog_id"])
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Artist profile' in html
    assert 'View original source / platform' not in html or item["url"] != item["source_profile_url"]
