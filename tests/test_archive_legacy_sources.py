"""Review-only legacy imports: preserve provenance, minimize private fields, and never infer links."""
import json
import sqlite3
import subprocess
import sys

import pytest

from dca_rebuild.archive_foundation import stage_snapshot
from dca_rebuild.archive_legacy_sources import inventory_summary, prepare_legacy_records


def sample():
    return {
        "dancer_profiles": [{
            "id": 12, "dance_name": "Test Dancer", "profile_slug": "test-dancer",
            "team_affiliation": "Unverified Team", "email": "secret@example.org",
            "real_name": "Private Legal Name", "private_notes": "do-not-import",
            "user_id": 111, "status": "public",
        }],
        "team_records": [{
            "id": 5, "team_name": "Test Team", "aka_names": "Unverified Alias",
            "submitter_contact": "hidden@example.org", "review_status": "pending",
        }],
        "battle_records": [{
            "id": 9, "event_name": "Test Battle", "event_date": "2018",
            "competitor_one": "Test Dancer", "winner": "Unverified Winner",
            "notes": "PRIVATE BATTLE NOTES", "review_status": "pending",
        }],
        "media_items": [
            {"id": 3, "media_type": "footage", "title": "Test Footage",
             "event_name": "Test Battle", "url": "https://example.org/video"},
            {"id": 4, "media_type": "music_release", "title": "Album, not footage"},
        ],
        "music_projects": [{"id": 1, "title": "Test Album", "project_type": "album"}],
        "music_project_tracks": [{"id": 8, "track_title": "Test Song", "music_project_id": 1}],
        "vault_gathering_submissions": [{
            "id": 7, "title": "Test Gathering", "start_date": "2024-05",
            "contact_email": "private@example.org", "status": "pending",
        }],
    }


def test_allowlist_never_moves_private_fields_or_creates_connections(tmp_path):
    rows, exclusions = prepare_legacy_records(sample())
    assert len(rows) == 6
    assert len(exclusions) == 2
    assert all(row["visibility"] == "private_review" for row in rows)
    assert [row["kind"] for row in rows] == [
        "battle", "person", "footage", "track", "team", "event"
    ]
    assert all(row["system"].startswith("legacy_sql:") for row in rows)
    payload = json.dumps(rows, sort_keys=True)
    for secret in ("secret@example.org", "Private Legal Name", "do-not-import",
                   "Unverified Team", "hidden@example.org", "PRIVATE BATTLE NOTES",
                   "private@example.org"):
        assert secret not in payload
    team = next(row for row in rows if row["kind"] == "team")
    assert team["payload"]["alias_source_text"] == "Unverified Alias"
    assert "aliases" not in team["payload"]
    battle = next(row for row in rows if row["kind"] == "battle")
    assert battle["payload"]["winner"] == "Unverified Winner"
    path = tmp_path / "legacy.staging.sqlite"
    stage_snapshot(path, rows)
    with sqlite3.connect(path) as db:
        assert db.execute("select count(*) from graph_records").fetchone()[0] == 6
        assert db.execute("select count(*) from graph_links").fetchone()[0] == 0
        assert db.execute("select count(*) from source_crosswalk").fetchone()[0] == 6
        assert db.execute("pragma foreign_key_check").fetchall() == []
    assert inventory_summary(rows, exclusions)["excluded"] == 2


def test_source_ids_and_revisions_stay_stable_across_imports(tmp_path):
    original = sample()
    rows, _ = prepare_legacy_records(original)
    path = tmp_path / "legacy.staging.sqlite"
    stage_snapshot(path, rows)
    with sqlite3.connect(path) as db:
        before = dict(db.execute("select system||':'||source_key,entity_id from source_crosswalk"))
    original["battle_records"][0]["winner"] = "Changed disputed winner"
    stage_snapshot(path, prepare_legacy_records(original)[0])
    with sqlite3.connect(path) as db:
        after = dict(db.execute("select system||':'||source_key,entity_id from source_crosswalk"))
        assert before == after
        assert db.execute("select count(*) from source_revisions where entity_id=?", (before["legacy_sql:battle_records:9"],)).fetchone()[0] == 2
        assert db.execute("select count(*) from graph_links").fetchone()[0] == 0
    assert len(list(tmp_path.glob("legacy.staging.sqlite.*.bak"))) == 1


@pytest.mark.parametrize("bad", [
    ["not-a-table-object"], {"secret_accounts": []},
    {"dancer_profiles": [{"id": None, "dance_name": "Name"}]},
    {"dancer_profiles": [{"id": 1, "dance_name": "Name"}, {"id": 1, "dance_name": "Other"}]},
    {"media_items": {"id": 3}},
])
def test_bad_export_fails_closed(bad):
    with pytest.raises(ValueError):
        prepare_legacy_records(bad)


def test_unknown_media_and_missing_titles_are_explicit_exclusions():
    rows, exclusions = prepare_legacy_records({
        "media_items": [{"id": 1, "media_type": "audio", "title": "Audio Source"},
                        {"id": 2, "media_type": "footage", "title": ""}],
        "dancer_profiles": [{"id": 1, "dance_name": None}],
    })
    assert not rows and len(exclusions) == 3
    assert {item["table"] for item in exclusions} == {"media_items", "dancer_profiles"}


def test_cli_can_preview_and_import_explicit_sanitized_export(tmp_path):
    export_path = tmp_path / "source.json"
    export_path.write_text(json.dumps(sample()), encoding="utf-8")
    cmd = [sys.executable, "-m", "dca_rebuild.archive_foundation", "--legacy-input", str(export_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    preview = json.loads(result.stdout)
    assert preview["legacy_inventory"]["staged"] == 6
    assert preview["legacy_inventory"]["excluded"] == 2
    assert preview["legacy_exclusions"][0]["reason"]
    assert not list(tmp_path.glob("*.staging.sqlite"))
    destination = tmp_path / "legacy.staging.sqlite"
    result = subprocess.run(cmd + ["--stage", str(destination)],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["records"] == 6
    assert destination.exists()
