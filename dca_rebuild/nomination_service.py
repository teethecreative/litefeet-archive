"""Privacy-preserving nominations with atomic, per-category rolling cooldowns."""
from datetime import datetime, timedelta, timezone
from math import ceil
from difflib import SequenceMatcher
import re
import unicodedata
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from dca_rebuild.models import DCACategory, DCAEdition, DCANominee, DCANominationSubmission, NominationCooldown


def utc_now():
    # Existing timestamp columns store naive UTC. Normalize aware input too.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def normalize_nominee_name(value):
    if not isinstance(value, str):
        raise ValueError("Nominee name is required")
    display = " ".join(unicodedata.normalize("NFKC", value).split())
    if not 2 <= len(display) <= 250:
        raise ValueError("Nominee name must be 2–250 characters")
    normalized = re.sub(r"[^\w]+", " ", display.casefold(), flags=re.UNICODE).strip()
    if len(normalized) < 2:
        raise ValueError("Nominee name is invalid")
    return display, normalized


# Confirmed owner-supplied identity mappings. Never infer an alias from
# similar spelling alone. Keys/values use normalized_nominee_name syntax.
CONFIRMED_NOMINEE_ALIASES = {
    "a astro": ("D Astro", "d astro"),
    "d ski": ("D Ski", "d ski"),
    "dski": ("D Ski", "d ski"),
    "bsn": ("BSNYEA", "bsnyea"),
    "bsnyea": ("BSNYEA", "bsnyea"),
    "d rillz": ("D Rillz", "d rillz"),
    "ty shots": ("Ty Shotz", "ty shotz"),
    "ty shotz": ("Ty Shotz", "ty shotz"),
    "noah lot": ("Noahlot", "noahlot"),
    "noahalot": ("Noahlot", "noahlot"),
    "noahlot": ("Noahlot", "noahlot"),
}


def canonical_nominee_name(value, *, category_name=None):
    """Apply owner-confirmed aliases without conflating dance and production credits."""
    display, normalized = normalize_nominee_name(value)
    if normalized in ("aye jae", "aye jae beats"):
        if category_name is not None:
            return (("Aye Jae Beats", "aye jae beats") if "produc" in category_name.casefold()
                    else ("Aye Jae", "aye jae"))
        return (("Aye Jae Beats", "aye jae beats") if normalized == "aye jae beats"
                else ("Aye Jae", "aye jae"))
    return CONFIRMED_NOMINEE_ALIASES.get(normalized, (display, normalized))


def canonical_nominee_key(value, *, category_name=None):
    return canonical_nominee_name(value, category_name=category_name)[1]


def _related_category_ids(db, category):
    """Return the linked producer write-in category IDs, retaining original records."""
    from dca_rebuild.phase9e import producer_writein_alias_map
    edition = db.get(DCAEdition, category.edition_id)
    aliases = producer_writein_alias_map(db, edition) if edition else {}
    canonical = aliases.get(category.id, category.id)
    return canonical, {canonical} | {cid for cid, target in aliases.items() if target == canonical}


def candidate_matches(db, *, category_id, name):
    """Check existing nominees before submit; confirmed aliases aren't guesses."""
    category = db.get(DCACategory, category_id)
    if category is None:
        return []
    canonical_id, related_ids = _related_category_ids(db, category)
    canonical_category = db.get(DCACategory, canonical_id)
    display, name_key = canonical_nominee_name(name, category_name=canonical_category.name)
    choices = db.query(DCANominee).filter(
        DCANominee.category_id.in_(related_ids),
        DCANominee.moderation_status.in_(('pending', 'approved')),
    ).all()
    found = []
    for nominee in choices:
        existing_key = canonical_nominee_key(nominee.name, category_name=canonical_category.name)
        exact = existing_key == name_key
        score = SequenceMatcher(None, name_key, existing_key).ratio()
        if exact or (len(name_key) >= 4 and len(existing_key) >= 4 and score >= 0.84):
            found.append({
                "id": nominee.id,
                "name": display if exact else nominee.name,
                "type": "existing" if exact else "similar",
                "score": score,
            })
    found.sort(key=lambda row: (row["type"] != "existing", -row["score"], row["name"].casefold()))
    # One canonical existing name is enough; distinct close-name candidates
    # are offered for human confirmation rather than automatic merging.
    unique = []
    seen = set()
    for row in found:
        key = row["name"].casefold()
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique[:5]


def category_history(db, edition_id, submitter_hash):
    return (db.query(DCANominationSubmission, DCANominee)
            .join(DCANominee, DCANominee.id == DCANominationSubmission.nominee_id)
            .filter(DCANominationSubmission.edition_id == edition_id,
                    DCANominationSubmission.submitter_hash == submitter_hash)
            .order_by(DCANominationSubmission.submitted_at.desc(), DCANominationSubmission.id.desc()).all())


def remaining_seconds(submitted_at, now=None):
    return max(0, ceil((as_utc(submitted_at) + timedelta(hours=24) - as_utc(now or utc_now())).total_seconds()))


def insert_for(db, model):
    dialect = db.get_bind().dialect.name
    if dialect == 'postgresql':
        return pg_insert(model)
    if dialect == 'sqlite':
        return sqlite_insert(model)
    raise RuntimeError('Nomination cooldowns require PostgreSQL or SQLite')


def add_nomination(db, *, edition_id, category_id, name, submitter_hash, ip_hash=None, description=None, now=None):
    """Caller owns the transaction and MUST roll back when created is False.

    A conditional UPDATE of a composite primary key serializes requests across
    workers. The claim, nominee and submission commit or roll back together.
    Historical entries are checked while holding this category/identity lock.
    """
    if not isinstance(submitter_hash, str) or not submitter_hash.strip():
        raise ValueError("Submitter identity is required")
    category = db.get(DCACategory, category_id)
    if not category or category.edition_id != edition_id:
        raise ValueError("Category and edition mismatch")
    category_id, related_ids = _related_category_ids(db, category)
    category = db.get(DCACategory, category_id)
    display, normalized = canonical_nominee_name(name, category_name=category.name)
    now = as_utc(now or utc_now())
    key = dict(edition_id=edition_id, category_id=category_id, submitter_hash=submitter_hash)
    db.execute(insert_for(db, NominationCooldown).values(**key, next_eligible_at=now)
               .on_conflict_do_nothing())
    claim = db.execute(update(NominationCooldown).filter_by(**key)
                       .where(NominationCooldown.next_eligible_at <= now)
                       .values(next_eligible_at=now + timedelta(hours=24)))
    if claim.rowcount != 1:
        return None, False
    latest = (db.query(DCANominationSubmission.submitted_at)
              .join(DCANominee, DCANominee.id == DCANominationSubmission.nominee_id)
              .filter(DCANominationSubmission.edition_id == edition_id,
                      DCANominationSubmission.submitter_hash == submitter_hash,
                      DCANominee.category_id.in_(related_ids))
              .order_by(DCANominationSubmission.submitted_at.desc()).first())
    if latest and remaining_seconds(latest[0], now):
        return None, False
    # Known aliases (e.g. A Astro / D Astro) count for the established
    # person. All older submissions remain attached to their original IDs.
    matching = [
        nominee for nominee in db.query(DCANominee).filter(
            DCANominee.category_id.in_(related_ids)).all()
        if canonical_nominee_key(nominee.name, category_name=category.name) == normalized
    ]
    matching.sort(key=lambda n: (n.category_id != category_id, n.normalized_name != normalized, n.id))
    nominee = matching[0] if matching else None
    if nominee is None:
        db.execute(insert_for(db, DCANominee).values(
            edition_id=edition_id, category_id=category_id, name=display,
            normalized_name=normalized, description=(description or '')[:2000],
            moderation_status='pending', created_at=now)
            .on_conflict_do_nothing(index_elements=['category_id', 'normalized_name']))
        nominee = db.scalars(select(DCANominee).filter_by(
            category_id=category_id, normalized_name=normalized)).one()
    db.add(DCANominationSubmission(edition_id=edition_id, nominee_id=nominee.id,
                                 submitter_hash=submitter_hash, ip_hash=ip_hash, submitted_at=now))
    db.flush()
    return nominee, True
