"""Identity-review reports must not mutate or disclose private records."""
import copy
import json

import pytest

from dca_rebuild.archive_reconciliation import (
    reconcile_identity_sources, reconcile_legacy_profile_counts,
)


def row(system, key, title, *, aliases=None, kind="person"):
    return {
        "system": system, "key": key, "title": title, "kind": kind,
        "visibility": "private_review", "payload": {"aliases": aliases or []},
    }


def test_collision_hints_preserve_distinct_source_rows_and_hide_names():
    source = [
        row("old", "1", "Test Dancer"),
        row("catalog", "one", "Test-Dancer"),
        row("catalog", "other", "Unrelated Performer"),
        row("old", "2", "Crew A", kind="team"),
    ]
    original = copy.deepcopy(source)
    result = reconcile_identity_sources(source)
    assert result["collision_groups"] == 1
    assert result["collision_keys"] == 2
    assert result["person_source_rows"] == 3
    assert result["groups"][0]["requires_review"]
    assert "candidates" not in result["groups"][0]
    assert "Test Dancer" not in json.dumps(result)
    assert source == original  # strictly read-only


def test_only_explicit_editorial_split_and_aliases_are_considered():
    source = [
        row("editorial_catalog", "one", "Test Dancer / Other Name"),
        row("legacy_profile_export", "1", "Other Name"),
        row("legacy_profile_export", "2", "Alias Recorded", aliases=["Test Dancer"]),
    ]
    report = reconcile_identity_sources(source, include_candidates=True)
    assert report["collision_groups"] == 2
    assert all(g["requires_review"] for g in report["groups"])
    assert any(g["sources"] == 2 for g in report["groups"])


def test_reject_duplicate_source_locators():
    with pytest.raises(ValueError, match="Duplicate historical source locator"):
        reconcile_identity_sources([row("old", "1", "A"), row("old", "1", "B")])


def test_legacy_report_only_returns_aggregates():
    records = [
        {"id": 11, "dance_name": "Test-Dancer", "profile_slug": "dancer-a", "email": "private@example.invalid"},
        {"id": 12, "dance_name": "Test Dancer", "profile_slug": "dancer-b", "private_notes": "hide"},
        {"id": 13, "dance_name": "Someone Else", "profile_slug": "different"},
    ]
    report = reconcile_legacy_profile_counts(records)
    assert report["rows"] == 3
    assert report["distinct_normalized_names"] == 2
    assert report["duplicate_name_groups"] == 1
    assert report["duplicate_name_rows"] == 2
    assert report["distinct_normalized_slugs"] == 3
    assert "private@example.invalid" not in json.dumps(report)
    assert "Test Dancer" not in json.dumps(report)
    assert "hide" not in json.dumps(report)


def test_invalid_legacy_rows_fail_closed():
    with pytest.raises(ValueError):
        reconcile_legacy_profile_counts([None])
