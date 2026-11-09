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
