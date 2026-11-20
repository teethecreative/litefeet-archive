import copy
import json
import sqlite3
import subprocess
import sys

import pytest

from dca_rebuild.archive_foundation import consolidation_preview, source_records, stage_snapshot


def row(key="first", title="Example", system="editorial_catalog", **fields):
    return dict(system=system, key=key, title=title, kind="dancer_profile",
                visibility="existing_public", payload=dict(collection="people", **fields))


def test_preview_is_deterministic_nonmutating_and_does_not_merge_names():
    records = [row(), row("second", "Example", "legacy_profile_export")]
    before = copy.deepcopy(records)
    preview = consolidation_preview(records)
    assert preview == consolidation_preview(list(reversed(records)))
    assert records == before
    assert preview["record_count"] == 2
    groups = [s for s in preview["suggestions"] if s["category"] == "duplicates"]
    assert len(groups) == 1
    assert len(groups[0]["subjects"]) == 2
    assert groups[0]["status"] == "pending"
    assert "requires human review" in groups[0]["reason"]


def test_only_explicit_labels_propose_connections_and_never_claim_a_winner():
    records = [row(title="Example"), row("context", "History", related_to="Example, Examp")]
    preview = consolidation_preview(records)
    links = [s for s in preview["suggestions"] if s["category"] == "relationships"]
    assert len(links) == 1
    assert links[0]["evidence"]["related_to_label"] == "Example"
    assert links[0]["status"] == "pending"
    assert "winner" not in json.dumps(preview)


def test_source_adapter_preserves_all_recovery_ids_without_private_bios():
    records = source_records()
    recovery = [r for r in records if r["system"] == "legacy_profile_export"]
    assert len(recovery) == 138
    assert len({r["key"] for r in recovery}) == 138
    assert all(r["visibility"] == "private_review" for r in recovery)
    assert all(set(r["payload"]) == {"source_id", "name", "legacy_slug", "reported_roles"}
               for r in recovery)
    assert all("editorial_notes" not in r["payload"] for r in records)


def test_staging_preserves_ids_revisions_and_pending_relationships(tmp_path, monkeypatch):
    # A production URL is intentionally ignored by the isolated importer.
    monkeypatch.setenv("DATABASE_URL", "postgresql://never-contact-this.invalid/production")
    destination = tmp_path / "archive.staging.sqlite"
    records = [row(), row("second", "Example", "legacy_profile_export")]
    first = stage_snapshot(destination, records)
    assert first["backup"] is None
    with sqlite3.connect(destination) as db:
        ids = db.execute("SELECT * FROM source_crosswalk ORDER BY system").fetchall()
        assert db.execute("SELECT count(*) FROM source_revisions").fetchone()[0] == 2
        assert db.execute("SELECT DISTINCT status FROM review_suggestions").fetchall() == [("pending",)]
    second = stage_snapshot(destination, records)
    assert second["backup"]
    records[0]["title"] = "Changed display name"
    stage_snapshot(destination, records)
    with sqlite3.connect(destination) as db:
        assert db.execute("SELECT * FROM source_crosswalk ORDER BY system").fetchall() == ids
        assert db.execute("SELECT count(*) FROM entities").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM source_revisions").fetchone()[0] == 3
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    with sqlite3.connect(second["backup"]) as db:
        assert db.execute("SELECT count(*) FROM source_revisions").fetchone()[0] == 2


def test_snapshot_membership_tracks_removed_and_returning_sources(tmp_path):
    destination = tmp_path / "archive.staging.sqlite"
    original = row()
    changed = row(title="New label")
    for records in ([original], [changed], [], [original]):
        stage_snapshot(destination, records)
    with sqlite3.connect(destination) as db:
        assert db.execute("SELECT count(*) FROM entities").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM source_revisions").fetchone()[0] == 2
        snapshots = db.execute("SELECT run_id, revision_id FROM import_run_records ORDER BY run_id").fetchall()
        assert [r[0] for r in snapshots] == [1, 2, 4]
        assert snapshots[0][1] == snapshots[2][1]
        assert snapshots[0][1] != snapshots[1][1]


def test_staging_rejects_production_like_or_unrecognized_files(tmp_path):
    for filename in ("production.db", "production.sqlite"):
        with pytest.raises(ValueError):
            stage_snapshot(tmp_path / filename, [row()])
        assert not (tmp_path / filename).exists()
    destination = tmp_path / "imposter.staging.sqlite"
    with sqlite3.connect(destination) as db:
        db.execute("CREATE TABLE production(value TEXT)")
        db.execute("INSERT INTO production VALUES ('untouched')")
    before = destination.read_bytes()
    with pytest.raises(ValueError):
        stage_snapshot(destination, [row()])
    assert destination.read_bytes() == before
    link = tmp_path / "link.staging.sqlite"
    link.symlink_to(destination)
    with pytest.raises(ValueError):
        stage_snapshot(link, [row()])


def test_duplicate_source_keys_fail_before_file_creation(tmp_path):
    destination = tmp_path / "archive.staging.sqlite"
    with pytest.raises(ValueError):
        stage_snapshot(destination, [row(), row()])
    assert not destination.exists()


def test_cli_defaults_to_preview_without_database_write(tmp_path):
    result = subprocess.run([sys.executable, "-m", "dca_rebuild.archive_foundation"],
                            capture_output=True, text=True, check=True)
    preview = json.loads(result.stdout)
    assert preview["record_count"] == len(source_records())
    assert "destination" not in preview


def test_admin_preview_is_private_paginated_and_read_only(website, database):
    client = website.test_client()
    route = "/admin/archive/research-review"
    assert client.get(route).status_code in (302, 303, 401, 403)
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"] = True
    html = client.get(route + "?category=duplicates").get_data(as_text=True)
    assert "CONNECTED ARCHIVE" in html
    assert "Next suggestions" in html
    assert "AWAITING HUMAN REVIEW" in html
    assert "Production databases" in html
    assert client.post(route).status_code == 405
    for query in ("?page=0", "?page=x", "?category=invalid"):
        assert client.get(route + query).status_code == 400
    # Recovery names and private review evidence stay absent from public API payloads.
    public = client.get('/archive/api/records').get_json()
    assert 'legacy_profile_export' not in json.dumps(public)
    assert 'suggestion_counts' not in json.dumps(public)
