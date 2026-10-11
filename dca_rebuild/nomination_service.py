"""DCA nomination normalization and idempotent persistence helpers.

No route calls these helpers until nominations are deliberately opened.
"""
import re
import unicodedata
from sqlalchemy.exc import IntegrityError
from dca_rebuild.models import DCANominee, DCANominationSubmission


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


def add_nomination(db, *, edition_id, category_id, name, submitter_hash, ip_hash=None, description=None):
    """Add one submission for one nominee. Caller owns commit/rollback.

    A duplicate submitter/nominee combination returns False; a second person
    nominating the same name creates a submission, not a second nominee.
    Must be called after checking that category belongs to edition and that
    the public nomination phase is open. Database unique constraints provide
    the final concurrency protection.
    """
    display, normalized = normalize_nominee_name(name)
    if not isinstance(submitter_hash, str) or not submitter_hash.strip():
        raise ValueError("Submitter identity is required")
    nominee = db.query(DCANominee).filter_by(category_id=category_id, normalized_name=normalized).first()
    if nominee is None:
        nominee = DCANominee(edition_id=edition_id, category_id=category_id,
                            name=display, normalized_name=normalized,
                            description=(description or "")[:2000], moderation_status="pending")
        db.add(nominee)
        db.flush()
    elif nominee.edition_id != edition_id:
        raise ValueError("Category and edition mismatch")
    prior = db.query(DCANominationSubmission).filter_by(
        nominee_id=nominee.id, submitter_hash=submitter_hash).first()
    if prior:
        return nominee, False
    db.add(DCANominationSubmission(edition_id=edition_id, nominee_id=nominee.id,
                                   submitter_hash=submitter_hash, ip_hash=ip_hash))
    db.flush()
    return nominee, True
