"""Privacy-preserving nominations with atomic, per-category rolling cooldowns."""
from datetime import datetime, timedelta, timezone
from math import ceil
import re
import unicodedata
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from dca_rebuild.models import DCACategory, DCANominee, DCANominationSubmission, NominationCooldown


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
    display, normalized = normalize_nominee_name(name)
    if not isinstance(submitter_hash, str) or not submitter_hash.strip():
        raise ValueError("Submitter identity is required")
    category = db.get(DCACategory, category_id)
    if not category or category.edition_id != edition_id:
        raise ValueError("Category and edition mismatch")
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
                      DCANominee.category_id == category_id)
              .order_by(DCANominationSubmission.submitted_at.desc()).first())
    if latest and remaining_seconds(latest[0], now):
        return None, False
    db.execute(insert_for(db, DCANominee).values(
        edition_id=edition_id, category_id=category_id, name=display,
        normalized_name=normalized, description=(description or '')[:2000],
        moderation_status='pending', created_at=now)
        .on_conflict_do_nothing(index_elements=['category_id', 'normalized_name']))
    nominee = db.scalars(select(DCANominee).filter_by(category_id=category_id, normalized_name=normalized)).one()
    db.add(DCANominationSubmission(edition_id=edition_id, nominee_id=nominee.id,
                                 submitter_hash=submitter_hash, ip_hash=ip_hash, submitted_at=now))
    db.flush()
    return nominee, True
