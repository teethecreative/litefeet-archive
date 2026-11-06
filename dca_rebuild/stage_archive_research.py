"""Safely stage legacy LiteFeet research as PRIVATE, unverified archive records.

This is deliberately not invoked by application startup or deployment.
Default mode ONLY prints a dry run; database writes require both --apply
and the exact --confirm string. No current records are overwritten.
"""
import argparse
import hashlib
import json
import re

from litefeet_seed_data import LITEFEET_RESEARCH_RECORDS
from dca_rebuild.models import Base, VaultArchiveRecord, VaultArchiveAssertion

PUBLICATION_STATUS = "private"
COLLECTIONS = {
    "historical_claim": "history",
    "move_info": "moves",
    "dancer_profile": "people",
    "event": "events",
    "battle_result": "events",
    "source_link": "media",
    "award_info": "awards",
}
CLAIM_LABELS = ("Claim Text",)
SUMMARY_LABELS = ("Claim Text", "Move Origin / Context", "Known For", "Source Context")


def _slug(value):
    compact = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return compact[:105] or "archival-record"


def staged_rows():
    """Translate source facts while retaining all source details internally."""
    results = []
    seen = set()
    for item in LITEFEET_RESEARCH_RECORDS:
        title = item["title"].strip()
        kind = item["submission_type"]
        details = [(key, value) for key, value in item.get("details", ()) if value]
        original_status = item.get("review_status", "")
        key = "legacy-research:" + hashlib.sha256((kind + ":" + title.casefold()).encode()).hexdigest()[:20]
        if key in seen:
            raise ValueError(f"Duplicate source research key: {title}")
        seen.add(key)
        slug = _slug(title) + "-" + key.split(":")[1][:8]
        summary = next((value for label, value in details if label in SUMMARY_LABELS), "")
        if not summary:
            summary = f"Research notes for {title}. Details require editorial review."
        claim = next((value for label, value in details if label in CLAIM_LABELS), "")
        results.append({
            "source_key": key,
            "slug": slug,
            "title": title,
            "record_type": kind,
            "collection": COLLECTIONS.get(kind, "history"),
            "summary": summary,
            "source_url": item.get("source_url", ""),
            "raw_details_json": json.dumps({
                "legacy_review_status": original_status,
                "legacy_related_to": item.get("related_to", ""),
                "details": [{"label": label, "value": value} for label, value in details],
            }, ensure_ascii=False),
            # "Community Supported" is a historical seed label, NOT verified.
            "editorial_status": "under_review",
            "visibility": PUBLICATION_STATUS,
            "assertion": claim if kind == "historical_claim" else "",
        })
    return results


def apply_private_import(session_factory, engine):
    # Creation is limited to additive Vault tables. Never mutate DCA tables.
    Base.metadata.create_all(engine, tables=[
        VaultArchiveRecord.__table__, VaultArchiveAssertion.__table__,
    ])
    created = existing = assertions = 0
    with session_factory.begin() as db:
        for row in staged_rows():
            source_key = row["source_key"]
            found = db.query(VaultArchiveRecord).filter_by(source_key=source_key).first()
            if found:
                existing += 1
                continue
            assert_text = row.pop("assertion")
            record = VaultArchiveRecord(**row)
            db.add(record)
            db.flush()
            created += 1
            if assert_text:
                db.add(VaultArchiveAssertion(
                    record_id=record.id,
                    source_key=source_key + ":claim",
                    statement=assert_text,
                    assertion_type="factual",
                    visibility=PUBLICATION_STATUS,
                ))
                assertions += 1
    return created, existing, assertions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Stage records privately in the configured database.")
    parser.add_argument("--confirm", default="", help="Must be exactly IMPORT_PRIVATE_RESEARCH when applying.")
    args = parser.parse_args(argv)
    rows = staged_rows()
    print(f"{len(rows)} historical research seed entries; all private and under review.")
    if not args.apply:
        for row in rows:
            print(f"[PRIVATE] {row['collection']}: {row['title']}")
        print("Dry-run only. Nothing was written.")
        return 0
    if args.confirm != "IMPORT_PRIVATE_RESEARCH":
        parser.error("--apply requires --confirm IMPORT_PRIVATE_RESEARCH")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from dca_rebuild.config import DATABASE_URL
    engine = create_engine(DATABASE_URL)
    try:
        created, skipped, assertions = apply_private_import(sessionmaker(bind=engine), engine)
        print(f"Staged {created} new private entries, skipped {skipped} existing, attached {assertions} private assertions.")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
