"""Version 2 schema for the isolated archive staging database only."""
import json

GRAPH_TABLES = {"graph_records", "graph_aliases", "graph_links", "graph_decisions"}
KIND_MAP = {
    "dancer_profile": "person", "legacy_identity": "person", "person_candidate": "person",
    "person": "person", "team": "team", "event": "event", "battle": "battle",
    "track": "track", "footage": "footage", "historical_claim": "claim",
    "move_info": "move", "award_archive": "award",
}
GRAPH_SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_records (
 id TEXT PRIMARY KEY REFERENCES entities(id),
 kind TEXT NOT NULL CHECK(kind IN ('person','team','event','battle','track','footage','claim','move','award')),
 label TEXT NOT NULL, source_revision_id INTEGER NOT NULL REFERENCES source_revisions(id),
 details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS graph_aliases (
 record_id TEXT NOT NULL REFERENCES graph_records(id), label TEXT NOT NULL,
 source_revision_id INTEGER NOT NULL REFERENCES source_revisions(id),
 PRIMARY KEY(record_id, label, source_revision_id)
);
CREATE TABLE IF NOT EXISTS graph_links (
 id TEXT PRIMARY KEY,
 subject_id TEXT NOT NULL REFERENCES graph_records(id),
 object_id TEXT NOT NULL REFERENCES graph_records(id), relation TEXT NOT NULL,
 evidence_revision_id INTEGER NOT NULL REFERENCES source_revisions(id),
 details_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','approved','rejected','reversed')),
 version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
 CHECK(subject_id != object_id),
 UNIQUE(subject_id, object_id, relation, evidence_revision_id, details_json)
);
CREATE TABLE IF NOT EXISTS graph_decisions (
 id TEXT PRIMARY KEY, link_id TEXT NOT NULL REFERENCES graph_links(id),
 previous_status TEXT NOT NULL, status TEXT NOT NULL,
 version INTEGER NOT NULL, reviewer_id TEXT NOT NULL, reason TEXT NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(link_id, version)
);
CREATE INDEX IF NOT EXISTS graph_link_subject ON graph_links(subject_id, status);
CREATE INDEX IF NOT EXISTS graph_link_object ON graph_links(object_id, status);
CREATE INDEX IF NOT EXISTS graph_link_review ON graph_links(status, created_at);
"""


def seed_graph_record(db, item, entity_id, revision_id):
    """One provisional record per source identity; no cross-source identity merge.

    Preserve the first canonical display label on reimport. New source text stays
    in immutable revisions for review rather than overwriting reviewed presentation.
    """
    kind = KIND_MAP.get(item["kind"])
    if not kind:
        return
    existing = db.execute("SELECT kind FROM graph_records WHERE id=?", (entity_id,)).fetchone()
    if existing and existing[0] != kind:
        raise ValueError("A source changed record type; explicit editorial reconciliation is required")
    payload = item["payload"]
    details = {key: payload[key] for key in (
        "date", "date_certainty", "event_date", "upload_date", "editorial_status"
    ) if key in payload}
    db.execute("INSERT OR IGNORE INTO graph_records VALUES (?,?,?,?,?)",
               (entity_id, kind, item["title"], revision_id, json.dumps(details, sort_keys=True)))
    labels = [item["title"]]
    # Only explicitly provided alias labels; do not split names heuristically.
    aliases = payload.get("aliases", [])
    if not isinstance(aliases, list) or any(not isinstance(label, str) for label in aliases):
        raise ValueError("Source aliases must be a list of recorded labels")
    labels += aliases
    for label in labels:
        if isinstance(label, str) and label.strip():
            db.execute("INSERT OR IGNORE INTO graph_aliases VALUES (?,?,?)",
                       (entity_id, label.strip(), revision_id))
