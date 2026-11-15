"""Internal consolidation preview and isolated staging; never a public publisher.

No application import, production engine, external requests or fuzzy identity merges.
Source locators are crosswalk keys, not permanent entity IDs. IDs are assigned once
in staging and preserved across subsequent imports of the same locator.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from dca_rebuild.archive_catalog import all_records, public_record
from dca_rebuild.archive_recovery import identity_key, recovery_candidates
from dca_rebuild.archive_graph_schema import GRAPH_SCHEMA, GRAPH_TABLES, KIND_MAP, seed_graph_record


def source_records():
    """Only allowlisted catalog fields and sanitized recovery identity fields."""
    records = []
    identities = json.loads((Path(__file__).parent / "data" / "archive_recovered_identities.json").read_text(encoding="utf-8"))
    recorded_aliases = {item["slug"]: item.get("aliases", []) for item in identities["records"]}
    for item in all_records():
        payload = public_record(item)
        if item["slug"] in recorded_aliases:
            payload["aliases"] = recorded_aliases[item["slug"]]
        records.append({
            "system": "editorial_catalog", "key": item["slug"],
            "title": item["title"], "kind": item["record_type"],
            "visibility": "existing_public", "payload": payload,
        })
    for item in recovery_candidates():
        records.append({
            "system": "legacy_profile_export", "key": str(item["source_id"]),
            "title": item["name"], "kind": "person_candidate",
            "visibility": "private_review", "payload": dict(item),
        })
    return records


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def reference(item):
    return {key: item[key] for key in ("system", "key", "title")}


def consolidation_preview(records=None):
    """Deterministic research suggestions; sentiment and name matches prove nothing."""
    records = source_records() if records is None else list(records)
    required = {"system", "key", "title", "kind", "visibility", "payload"}
    for item in records:
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("Each source record must specify system, key, title, kind, visibility and payload")
        if any(not isinstance(item[key], str) or not item[key].strip()
               for key in required - {"payload"}):
            raise ValueError("Source identifiers and labels must be nonempty strings")
        if not isinstance(item["payload"], dict) or item["visibility"] not in {"existing_public", "private_review"}:
            raise ValueError("Invalid source payload or visibility")
        if item["kind"] not in KIND_MAP:
            raise ValueError("Unsupported archive record kind")
    locators = [(r["system"], r["key"]) for r in records]
    if len(set(locators)) != len(locators):
        raise ValueError("Duplicate source locator; review before staging")
    names = defaultdict(list)
    suggestions = []

    def suggest(category, subjects, reason, evidence):
        subjects = sorted((reference(s) for s in subjects),
                          key=lambda s: (s["system"], s["key"]))
        body = dict(category=category, subjects=subjects, reason=reason, evidence=evidence)
        suggestions.append(dict(body, id=fingerprint(body), status="pending"))

    for item in records:
        payload = item["payload"]
        # Restrict identity comparisons to people, never event titles or team names.
        if item["kind"] in {"person", "person_candidate", "dancer_profile", "legacy_identity"}:
            for name in set(item["title"].split("/")):
                key = identity_key(name)
                if key and item not in names[key]:
                    names[key].append(item)
        if item["system"] != "editorial_catalog":
            continue
        if not payload.get("source_url") and not payload.get("research_sources"):
            suggest("sources", [item], "No linked source is recorded; inspect existing citations before researching.",
                    {"source_label": payload.get("source_label", "")})
        if payload.get("collection") == "events" and payload.get("date_certainty") != "confirmed":
            suggest("basics", [item], "Review the event date and its certainty; do not infer an event date from an upload date.",
                    {"date": payload.get("date", ""), "certainty": payload.get("date_certainty", "")})
    for key, group in sorted(names.items()):
        if len(group) > 1:
            suggest("duplicates", group, "Names or slash-separated labels match after normalization. Identity requires human review.",
                    {"normalized_label": key})

    # related_to is free text, not a verified relationship. Exact individual labels
    # can suggest connections, but are never imported as approved edges.
    for item in records:
        if item["system"] != "editorial_catalog":
            continue
        for label in sorted(set(item["payload"].get("related_to", "").split(","))):
            matches = [other for other in names.get(identity_key(label), []) if other != item]
            if matches:
                suggest("relationships", [item, *matches],
                        "An existing related-to label matches an identity label. Confirm the subject and relationship type.",
                        {"related_to_label": label.strip(), "source_locator": item["key"]})
    suggestions.sort(key=lambda s: (s["category"], s["subjects"][0]["title"].casefold(), s["id"]))
    return {
        "record_count": len(records),
        "systems": dict(sorted(Counter(r["system"] for r in records).items())),
        "kinds": dict(sorted(Counter(r["kind"] for r in records).items())),
        "suggestion_counts": dict(sorted(Counter(s["category"] for s in suggestions).items())),
        "suggestions": suggestions,
        "limitations": [
            "Repository snapshots only; production databases and backups are not inspected.",
            "No identity is merged, no relationship is approved, and no content is published.",
            "These deterministic checks are a review foundation, not deployed Archive AI or footage analysis.",
        ],
    }


SCHEMA = """
CREATE TABLE IF NOT EXISTS staging_metadata (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS entities (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_crosswalk (
 system TEXT NOT NULL, source_key TEXT NOT NULL, entity_id TEXT NOT NULL REFERENCES entities(id),
 PRIMARY KEY(system, source_key)
);
CREATE TABLE IF NOT EXISTS source_revisions (
 id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL REFERENCES entities(id),
 digest TEXT NOT NULL, payload_json TEXT NOT NULL, captured_at TEXT NOT NULL,
 UNIQUE(entity_id, digest)
);
CREATE TABLE IF NOT EXISTS review_suggestions (
 id TEXT PRIMARY KEY, category TEXT NOT NULL, body_json TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suggestion_subjects (
 suggestion_id TEXT NOT NULL REFERENCES review_suggestions(id),
 entity_id TEXT NOT NULL REFERENCES entities(id), PRIMARY KEY(suggestion_id, entity_id)
);
CREATE TABLE IF NOT EXISTS import_runs (
 id INTEGER PRIMARY KEY, input_digest TEXT NOT NULL, record_count INTEGER NOT NULL,
 suggestion_count INTEGER NOT NULL, captured_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS import_run_records (
 run_id INTEGER NOT NULL REFERENCES import_runs(id),
 entity_id TEXT NOT NULL REFERENCES entities(id),
 revision_id INTEGER NOT NULL REFERENCES source_revisions(id),
 PRIMARY KEY(run_id, entity_id)
);
"""

BASE_TABLES = {"staging_metadata", "entities", "source_crosswalk", "source_revisions",
               "review_suggestions", "suggestion_subjects", "import_runs", "import_run_records"}


def staging_path(destination):
    path = Path(destination).absolute()
    if path.is_symlink() or not path.name.endswith(".staging.sqlite"):
        raise ValueError("Use a regular local filename ending in .staging.sqlite")
    return path


def validate_staging(db, require_graph=False):
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "staging_metadata" not in tables:
        raise ValueError("Not an archive staging database")
    versions = db.execute("SELECT version FROM staging_metadata").fetchall()
    if versions == [(1,)] and tables == BASE_TABLES and not require_graph:
        return 1
    if versions == [(2,)] and tables == BASE_TABLES | GRAPH_TABLES:
        return 2
    raise ValueError("Unrecognized archive staging schema; run the explicit staging importer")


def stage_snapshot(destination, records=None):
    """Create/update an explicitly named local .staging.sqlite snapshot atomically.

    Existing snapshots are backed up before writes. No delete/update of historical
    revisions, public tables, approvals, or source files is performed.
    """
    destination = staging_path(destination)
    records = source_records() if records is None else list(records)
    preview = consolidation_preview(records)
    now = datetime.now(timezone.utc).isoformat()
    backup = None
    if destination.exists():
        with sqlite3.connect(f"{destination.as_uri()}?mode=ro", uri=True) as source:
            validate_staging(source)
            backup = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".bak")
            with sqlite3.connect(backup) as target:
                source.backup(target)
    with sqlite3.connect(destination) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + GRAPH_SCHEMA)
        if not db.execute("SELECT 1 FROM staging_metadata").fetchone():
            db.execute("INSERT INTO staging_metadata VALUES (2)")
        else:
            db.execute("UPDATE staging_metadata SET version=2")
        # Upgrade all preserved v1 source entities, including sources absent from
        # the current import. Nothing is removed or silently joined by name.
        for entity_id, revision_id, payload_json in db.execute(
                "SELECT entity_id,id,payload_json FROM source_revisions ORDER BY id"):
            seed_graph_record(db, json.loads(payload_json), entity_id, revision_id)
        ids = {}
        revisions = {}
        for item in records:
            locator = (item["system"], item["key"])
            existing = db.execute("SELECT entity_id FROM source_crosswalk WHERE system=? AND source_key=?", locator).fetchone()
            entity_id = existing[0] if existing else str(uuid.uuid4())
            ids[locator] = entity_id
            if not existing:
                db.execute("INSERT INTO entities VALUES (?,?,?)", (entity_id, item["kind"], now))
                db.execute("INSERT INTO source_crosswalk VALUES (?,?,?)", (*locator, entity_id))
            db.execute("INSERT OR IGNORE INTO source_revisions(entity_id,digest,payload_json,captured_at) VALUES (?,?,?,?)",
                       (entity_id, fingerprint(item), json.dumps(item, ensure_ascii=False, sort_keys=True), now))
            revisions[entity_id] = db.execute("SELECT id FROM source_revisions WHERE entity_id=? AND digest=?",
                                              (entity_id, fingerprint(item))).fetchone()[0]
            seed_graph_record(db, item, entity_id, revisions[entity_id])
        for suggestion in preview["suggestions"]:
            db.execute("INSERT OR IGNORE INTO review_suggestions(id,category,body_json,created_at) VALUES (?,?,?,?)",
                       (suggestion["id"], suggestion["category"], json.dumps(suggestion, ensure_ascii=False, sort_keys=True), now))
            for subject in suggestion["subjects"]:
                db.execute("INSERT OR IGNORE INTO suggestion_subjects VALUES (?,?)",
                           (suggestion["id"], ids[(subject["system"], subject["key"])]) )
        run_id = db.execute("INSERT INTO import_runs(input_digest,record_count,suggestion_count,captured_at) VALUES (?,?,?,?)",
                            (fingerprint(records), len(records), len(preview["suggestions"]), now)).lastrowid
        for entity_id, revision_id in revisions.items():
            db.execute("INSERT INTO import_run_records VALUES (?,?,?)", (run_id, entity_id, revision_id))
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Staging relationship integrity check failed")
    return {"destination": str(destination), "backup": str(backup) if backup else None,
            "records": len(records), "suggestions": len(preview["suggestions"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, help="Explicit local .staging.sqlite file; default is read-only preview")
    parser.add_argument("--input", type=Path, help="Explicit JSON array of source records; replaces the input snapshot, not preserved history")
    args = parser.parse_args()
    records = None
    if args.input:
        records = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            parser.error("--input must contain an array of source records")
    print(json.dumps(stage_snapshot(args.stage, records) if args.stage else consolidation_preview(records),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
