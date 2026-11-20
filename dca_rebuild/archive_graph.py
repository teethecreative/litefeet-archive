"""Evidence-linked, human-reviewed connections in an explicit staging snapshot.

This service has no access to the public database or application session globals.
Identity matches are reversible assertions, never destructive profile merges.
"""
from collections import deque
from contextlib import contextmanager
import calendar
from datetime import date, datetime, timezone
import json
import re
import sqlite3
import uuid

from dca_rebuild.archive_foundation import staging_path, validate_staging


RELATIONS = {
    "member_of": ({"person"}, {"team"}),
    "participated_in": ({"person", "team"}, {"event", "battle"}),
    "contains_battle": ({"event"}, {"battle"}),
    "documented_by": ({"event", "battle"}, {"footage"}),
    "produced": ({"person"}, {"track"}),
    "featured_in": ({"track"}, {"footage", "battle"}),
    "same_identity": ({"person", "team"}, {"person", "team"}),
}
ROLES = {"dancer", "judge", "host", "photographer", "producer", "organizer", "team"}


class ReviewConflict(ValueError):
    """A newer decision or changed source requires the reviewer to refresh."""


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def graph_session(destination, write=False):
    path = staging_path(destination)
    # mode=rw/ro never creates a file as a side effect of a page request.
    db = sqlite3.connect(f"{path.as_uri()}?mode={'rw' if write else 'ro'}", uri=True, timeout=20)
    try:
        validate_staging(db, require_graph=True)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        if write:
            backup = path.with_name(path.name + "." + uuid.uuid4().hex + ".bak")
            with sqlite3.connect(backup) as target:
                db.backup(target)
            db.execute("BEGIN IMMEDIATE")
        yield db
        if write:
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Broken staging references")
            db.commit()
    except Exception:
        if write:
            db.rollback()
        raise
    finally:
        db.close()


def _required_text(value, label, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{label} is required and must be at most {maximum} characters")
    return value.strip()


def _partial_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}(?:-\d{2}){0,2}", value):
        raise ValueError("Use a year, YYYY-MM, or YYYY-MM-DD; omit unknown dates")
    first = date.fromisoformat(value + {4: "-01-01", 7: "-01", 10: ""}[len(value)])
    last = (date(first.year, 12, 31) if len(value) == 4 else
            date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])
            if len(value) == 7 else first)
    return first, last


def _details(relation, details):
    if not isinstance(details, dict):
        raise ValueError("Connection details must be an object")
    allowed = {
        "member_of": {"from", "until", "date_certainty"},
        "participated_in": {"role"},
        "documented_by": {"start_seconds", "end_seconds"},
    }.get(relation, set())
    if set(details) - allowed:
        raise ValueError("Unsupported connection detail")
    for key in ("from", "until"):
        if key in details:
            _partial_date(details[key])
    if "from" in details and "until" in details and _partial_date(details["until"])[1] < _partial_date(details["from"])[0]:
        raise ValueError("Membership end precedes its start")
    if "date_certainty" in details and details["date_certainty"] not in {"reported", "approximate", "unknown", "documented"}:
        raise ValueError("Unknown date certainty")
    if "role" in details and details["role"] not in ROLES:
        raise ValueError("Unknown participation role")
    for key in ("start_seconds", "end_seconds"):
        if key in details and (type(details[key]) is not int or details[key] < 0):
            raise ValueError("Footage timestamps must be nonnegative whole seconds")
    if "end_seconds" in details and details["end_seconds"] <= details.get("start_seconds", 0):
        raise ValueError("Footage end must follow its start")
    return json.dumps(details, sort_keys=True, separators=(",", ":"))


def _current_evidence(db, revision_id):
    return db.execute("""SELECT 1 FROM import_run_records r
        WHERE r.run_id=(SELECT max(id) FROM import_runs) AND r.revision_id=?""",
                      (revision_id,)).fetchone() is not None


def _audit(db, link_id, previous, status, version, reviewer_id, reason):
    db.execute("INSERT INTO graph_decisions VALUES (?,?,?,?,?,?,?,?)",
               (str(uuid.uuid4()), link_id, previous, status, version,
                _required_text(reviewer_id, "Reviewer", 200), _required_text(reason, "Reason"), now()))


def propose_connection(destination, subject_id, relation, object_id, evidence_revision_id,
                       reviewer_id, reason, details=None):
    details_json = _details(relation, {} if details is None else details)
    if type(evidence_revision_id) is not int:
        raise ValueError("Evidence revision must be an integer")
    with graph_session(destination, write=True) as db:
        subject = db.execute("SELECT kind FROM graph_records WHERE id=?", (subject_id,)).fetchone()
        target = db.execute("SELECT kind FROM graph_records WHERE id=?", (object_id,)).fetchone()
        kinds = RELATIONS.get(relation)
        if not subject or not target or not kinds or subject_id == object_id:
            raise ValueError("Choose distinct existing records and a supported relationship")
        if subject["kind"] not in kinds[0] or target["kind"] not in kinds[1]:
            raise ValueError("Relationship does not support these record types")
        if relation == "same_identity" and subject["kind"] != target["kind"]:
            raise ValueError("Identity matches must have the same record type")
        if not db.execute("SELECT 1 FROM source_revisions WHERE id=?", (evidence_revision_id,)).fetchone():
            raise ValueError("Select an existing evidence revision")
        # Same identity is symmetric. Normalize the endpoints to avoid duplicates.
        if relation == "same_identity" and object_id < subject_id:
            subject_id, object_id = object_id, subject_id
        duplicate = db.execute("""SELECT id FROM graph_links WHERE subject_id=? AND object_id=?
            AND relation=? AND evidence_revision_id=? AND details_json=?""",
            (subject_id, object_id, relation, evidence_revision_id, details_json)).fetchone()
        if duplicate:
            raise ReviewConflict("This proposal already exists; review its existing history")
        link_id = str(uuid.uuid4())
        db.execute("""INSERT INTO graph_links(id,subject_id,object_id,relation,evidence_revision_id,
            details_json,created_at) VALUES (?,?,?,?,?,?,?)""",
            (link_id, subject_id, object_id, relation, evidence_revision_id, details_json, now()))
        _audit(db, link_id, "none", "pending", 1, reviewer_id, reason)
        return link_id


def decide_connection(destination, link_id, decision, expected_version, reviewer_id, reason):
    transitions = {("pending", "approve"): "approved", ("pending", "reject"): "rejected",
                   ("approved", "reverse"): "reversed", ("rejected", "reopen"): "pending",
                   ("reversed", "reopen"): "pending"}
    with graph_session(destination, write=True) as db:
        link = db.execute("SELECT * FROM graph_links WHERE id=?", (link_id,)).fetchone()
        if not link:
            raise ValueError("Unknown connection")
        if type(expected_version) is not int or link["version"] != expected_version:
            raise ReviewConflict("Connection changed; refresh before deciding")
        status = transitions.get((link["status"], decision))
        if not status:
            raise ReviewConflict("This decision is not allowed from the current state")
        if decision == "approve" and not _current_evidence(db, link["evidence_revision_id"]):
            raise ReviewConflict("Evidence changed or left the latest snapshot; submit a new proposal using current evidence")
        version = link["version"] + 1
        db.execute("UPDATE graph_links SET status=?,version=? WHERE id=?", (status, version, link_id))
        _audit(db, link_id, link["status"], status, version, reviewer_id, reason)


def graph_workspace(destination, status="pending", page=1, query=""):
    if status not in {"pending", "approved", "rejected", "reversed"} or type(page) is not int or not 1 <= page <= 10000:
        raise ValueError("Invalid connection filter or page")
    with graph_session(destination) as db:
        records = [dict(r) for r in db.execute("SELECT * FROM graph_records ORDER BY label,id")]
        for record in records:
            record["details"] = json.loads(record.pop("details_json"))
            record["aliases"] = [r[0] for r in db.execute("SELECT DISTINCT label FROM graph_aliases WHERE record_id=? ORDER BY label", (record["id"],))]
        if query:
            query = query.casefold().strip()[:120]
            records = [r for r in records if query in r["label"].casefold() or
                       any(query in alias.casefold() for alias in r["aliases"])]
        total = db.execute("SELECT count(*) FROM graph_links WHERE status=?", (status,)).fetchone()[0]
        links = []
        for row in db.execute("""SELECT l.*,s.label AS subject_label,o.label AS object_label,
                e.payload_json AS evidence_json FROM graph_links l
                JOIN graph_records s ON s.id=l.subject_id JOIN graph_records o ON o.id=l.object_id
                JOIN source_revisions e ON e.id=l.evidence_revision_id
                WHERE l.status=? ORDER BY l.created_at,l.id LIMIT 20 OFFSET ?""", (status, (page-1)*20)):
            link = dict(row)
            link["evidence"] = json.loads(link.pop("evidence_json"))
            link["details"] = json.loads(link.pop("details_json"))
            link["evidence_current"] = _current_evidence(db, link["evidence_revision_id"])
            link["history"] = [dict(d) for d in db.execute("SELECT * FROM graph_decisions WHERE link_id=? ORDER BY version", (link["id"],))]
            links.append(link)
        return dict(records=records, links=links, total=total, page=page, status=status,
                    query=query, has_more=page*20 < total,
                    evidence=[dict(r) for r in db.execute("""SELECT s.id,c.system,c.source_key FROM source_revisions s
                        JOIN import_run_records r ON r.revision_id=s.id
                        JOIN source_crosswalk c ON c.entity_id=s.entity_id
                        WHERE r.run_id=(SELECT max(id) FROM import_runs) ORDER BY c.system,c.source_key""")])


def connected_path(destination, start_id, end_id, max_hops=5):
    """Undirected exploration of approved, currently sourced edges only.

    Each returned edge retains its own direction, relation, evidence and details.
    Same-identity assertions do not combine profiles or transitively merge them.
    """
    if type(max_hops) is not int or not 1 <= max_hops <= 8:
        raise ValueError("Path depth must be between 1 and 8")
    with graph_session(destination) as db:
        if any(not db.execute("SELECT 1 FROM graph_records WHERE id=?", (key,)).fetchone()
               for key in (start_id, end_id)):
            raise ValueError("Unknown path endpoint")
        adjacency = {}
        for row in db.execute("""SELECT l.*,s.label AS subject_label,o.label AS object_label
                FROM graph_links l JOIN graph_records s ON s.id=l.subject_id
                JOIN graph_records o ON o.id=l.object_id
                WHERE l.status='approved' AND l.relation!='same_identity' ORDER BY l.id"""):
            edge = dict(row)
            if not _current_evidence(db, edge["evidence_revision_id"]):
                continue
            for key in (edge["subject_id"], edge["object_id"]):
                adjacency.setdefault(key, []).append(edge)
        queue = deque([(start_id, [])])
        seen = {start_id}
        while queue:
            current, path = queue.popleft()
            if current == end_id:
                return path
            if len(path) >= max_hops:
                continue
            for edge in adjacency.get(current, []):
                target = edge["object_id"] if current == edge["subject_id"] else edge["subject_id"]
                if target not in seen:
                    seen.add(target)
                    queue.append((target, path + [edge]))
        return None
