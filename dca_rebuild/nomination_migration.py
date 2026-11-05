"""Idempotent, additive historical import. No legacy tables/rows are changed."""
from sqlalchemy import text


def migrate_nomination_history(engine):
    # INSERT ... SELECT keeps this bounded in Python memory. The source-ID
    # uniqueness constraint serializes simultaneous startup imports as well.
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO ledger_dca_nomination_entries
                (legacy_submission_id, edition_id, nominee_id, submitter_hash, ip_hash, submitted_at)
            SELECT id, edition_id, nominee_id, submitter_hash, ip_hash, submitted_at
            FROM ledger_dca_nomination_submissions WHERE true
            ON CONFLICT (legacy_submission_id) DO NOTHING
        """))
        connection.execute(text("""
            INSERT INTO ledger_dca_nomination_entry_details
                (submission_id, team, location, instagram, justification)
            SELECT entry.id, detail.team, detail.location, detail.instagram, detail.justification
            FROM ledger_dca9e_nomination_details detail
            JOIN ledger_dca_nomination_entries entry
              ON entry.legacy_submission_id = detail.submission_id
            WHERE true
            ON CONFLICT (submission_id) DO NOTHING
        """))
