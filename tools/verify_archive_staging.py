"""Rehearse Vault archive staging in temporary, disposable SQLite databases.

No Render connection, production secrets, network access, live DB export, or
production migration is performed. The repository's existing editorial snapshot
is combined only with clearly synthetic legacy source fixtures.
"""
import copy
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from dca_rebuild.archive_foundation import (
    source_records, stage_snapshot, validate_staging,
)
from dca_rebuild.archive_legacy_sources import prepare_legacy_records


def synthetic_legacy_export():
    """Synthetic stand-ins exercise the complete allowlisted source adapter."""
    return {
        "dancer_profiles": [{
            "id": 1, "dance_name": "Synthetic Dancer",
            "profile_slug": "synthetic-dancer", "email": "never-publish@example.invalid",
            "private_notes": "Never publish this source field",
        }],
        "team_records": [{
            "id": 1, "team_name": "Synthetic Crew", "aka_names": "Unverified crew alias",
            "submitter_contact": "never-publish@example.invalid",
        }],
        "battle_records": [{
            "id": 1, "event_name": "Synthetic Battle",
            "competitor_one": "Synthetic Dancer", "winner": "Unverified outcome",
            "event_date": "2018", "source_url": "https://example.invalid/battle",
        }],
        "vault_gathering_submissions": [{
            "id": 1, "title": "Synthetic Gathering", "start_date": "2018-05",
            "contact_email": "never-publish@example.invalid",
        }],
        "music_project_tracks": [{
            "id": 1, "track_title": "Synthetic Track", "music_project_id": 1,
        }],
        "media_items": [
            {"id": 1, "media_type": "footage", "title": "Synthetic Footage"},
            {"id": 2, "media_type": "music_release", "title": "Synthetic Release"},
        ],
        "music_projects": [
            {"id": 1, "title": "Synthetic Project", "project_type": "album"},
        ],
    }


def snapshot_state(path):
    with sqlite3.connect(path) as db:
        assert validate_staging(db, require_graph=True) == 2
        assert db.execute("PRAGMA foreign_key_check").fetchall() == [], "Broken staging FK"
        ids = dict(db.execute(
            "SELECT system||':'||source_key,entity_id FROM source_crosswalk"
        ))
        rows = dict(db.execute(
            "SELECT name, 1 FROM sqlite_master WHERE type='table'"
        ))
        return {
            "ids": ids,
            "crosswalks": len(ids),
            "revisions": db.execute("SELECT count(*) FROM source_revisions").fetchone()[0],
            "graph_records": db.execute("SELECT count(*) FROM graph_records").fetchone()[0],
            "links": db.execute("SELECT count(*) FROM graph_links").fetchone()[0],
            "approved_links": db.execute(
                "SELECT count(*) FROM graph_links WHERE status='approved'"
            ).fetchone()[0],
            "import_runs": db.execute("SELECT count(*) FROM import_runs").fetchone()[0],
            "tables": rows,
        }


def rehearse():
    editorial = source_records()
    assert editorial, "Repository snapshot is unexpectedly empty"
    legacy, exclusions = prepare_legacy_records(synthetic_legacy_export())
    assert len(legacy) == 6 and len(exclusions) == 2
    assert all(row["visibility"] == "private_review" for row in legacy)
    combined = editorial + legacy
    assert len({(row["system"], row["key"]) for row in combined}) == len(combined)
    assert all(not row["system"].startswith("legacy_sql:") or
               "never-publish@example.invalid" not in json.dumps(row)
               for row in combined), "Legacy privacy allowlist failed"

    with TemporaryDirectory(prefix="vault-archive-rehearsal-") as root:
        scratch = Path(root)
        target = scratch / "disposable.staging.sqlite"
        # Import the existing repository catalog, twice, into an isolated copy.
        stage_snapshot(target, editorial)
        baseline = snapshot_state(target)
        assert baseline["crosswalks"] == len(editorial)
        assert baseline["links"] == baseline["approved_links"] == 0
        stage_snapshot(target, editorial)
        repeated = snapshot_state(target)
        assert repeated["ids"] == baseline["ids"], "Reimport changed permanent source IDs"
        assert repeated["revisions"] == baseline["revisions"], "Idempotent import duplicated revisions"
        assert repeated["import_runs"] == 2

        # Explicitly add six synthetic rows: no unreviewed edges or approvals.
        stage_snapshot(target, combined)
        extended = snapshot_state(target)
        assert extended["crosswalks"] == len(combined)
        assert extended["revisions"] == len(combined)
        assert extended["links"] == extended["approved_links"] == 0
        for locator, original_id in baseline["ids"].items():
            assert extended["ids"][locator] == original_id, "Source locator was remapped"

        # Rehearse a recognized v1 -> v2 upgrade against a separate scratch copy.
        upgrade = scratch / "upgrade.staging.sqlite"
        stage_snapshot(upgrade, editorial)
        with sqlite3.connect(upgrade) as db:
            for table in ("graph_decisions", "graph_links", "graph_aliases", "graph_records"):
                db.execute("DROP TABLE " + table)
            db.execute("UPDATE staging_metadata SET version=1")
            assert validate_staging(db) == 1
        result = stage_snapshot(upgrade, combined)
        assert result["backup"], "Upgrade must create an original-state backup"
        with sqlite3.connect(result["backup"]) as backup:
            assert validate_staging(backup) == 1, "Backup did not retain pre-upgrade schema"
            assert backup.execute("PRAGMA foreign_key_check").fetchall() == []
        upgraded = snapshot_state(upgrade)
        assert upgraded["crosswalks"] == len(combined)
        for locator, original_id in baseline["ids"].items():
            assert upgraded["ids"][locator] == original_id, "Upgrade changed permanent source IDs"
        assert upgraded["links"] == upgraded["approved_links"] == 0

        # An invalid subsequent import must not corrupt the existing graph.
        invalid = copy.deepcopy(combined)
        invalid[-1]["payload"]["aliases"] = "not-an-explicit-alias-list"
        try:
            stage_snapshot(upgrade, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed source import was not rejected")
        after_failure = snapshot_state(upgrade)
        assert after_failure["ids"] == upgraded["ids"]
        assert after_failure["revisions"] == upgraded["revisions"]
        assert after_failure["links"] == 0

        return {
            "rehearsal_kind": "isolated repository snapshot + synthetic legacy rows",
            "production_data_accessed": False,
            "production_data_modified": False,
            "repo_source_rows": len(editorial),
            "synthetic_legacy_rows": len(legacy),
            "synthetic_legacy_exclusions": len(exclusions),
            "final_preserved_source_rows": upgraded["crosswalks"],
            "stable_source_ids": True,
            "idempotent_reimport": True,
            "v1_to_v2_backup_and_upgrade": True,
            "invalid_import_rollback": True,
            "foreign_keys_valid": True,
            "approved_historical_connections": upgraded["approved_links"],
            "scratch_cleaned_on_exit": True,
        }


if __name__ == "__main__":
    print(json.dumps(rehearse(), indent=2, sort_keys=True))
