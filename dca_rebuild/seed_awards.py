from dca_rebuild.app import SessionLocal
from dca_rebuild.models import DCAEdition, DCACategory, LFARecord
from dca_rebuild.lfa_2026_data import LFA_2026_WINNERS, LFA_2026_SOURCE


HISTORICAL_CATEGORIES = [
    "Best Trickster",
    "Best Hat Trick",
    "Best Shoe Trick",
    "Best Footwork",
    "Best Battle Moment",
    "Best Tag Team",
    "Best Collab",
    "Best Entertainer",
    "Best Ankle Bender",
    "Life of the Party",
    'Best "Lite" Feet Energy',
    "Best Team Video",
    "Most Passionate",
    "Most Versatile",
    "Most Involved",
    "Most Fearless (Risk Taker)",
    "Most Improved Dancer",
    "Most Improved Producer",
    "Most Consistent Producer",
    "Most Consistent Dancer",
    "Battle Song of the Year",
    "Content Song of the Year",
    "Best Content Creator",
    "Best Combo Dancer",
    "Best Balance",
    "Best Musicality",
    "Best Out of NY Dancer",
    "Best Event of 2023",
    "Best Big Man",
    "Best Junior Dancer",
    "Youngest in Charge",
    "Best Producer Collab",
    "Most Underrated",
    "Most Battles",
    "Dancehall",
    "Most Overrated",
    "Most TKOs",
    "Most Battle Wins",
    "Most Resilient",
    "Best Lite Feet Flipper",
    "Best Harlem Lite Feet Team",
    "Most Anticipated Battle",
    "Litefeeter of the Year",
    "Best Chant",
    "Most Spanky",
    "King/Queen of Lite Award",
    "Track Killer Award",
    "Best Nomad",
    "Shy Dancer",
]


def get_or_create_edition(db, year):
    edition = (
        db.query(DCAEdition)
        .filter_by(year=year)
        .first()
    )

    if edition:
        return edition

    title = (
        "Dancer's Choice Awards 2023"
        if year == 2023
        else "Dancer's Choice Awards 2026"
    )

    edition = DCAEdition(
        year=year,
        title=title,
    )

    db.add(edition)
    db.flush()

    return edition


def _lfa_category_key(value):
    return " ".join((value or "").casefold().split())


def seed_lfa_2026(db):
    """Import confirmed 2026 LFA winners without duplicating records.

    Preserve the original community submission when correcting the
    previously approved Lady of Lite entry; do not rewrite that submission.
    """
    existing = (
        db.query(LFARecord)
        .filter_by(year=2026, record_type="award_winner")
        .all()
    )
    by_category = {}
    for record in existing:
        by_category.setdefault(_lfa_category_key(record.category_name), []).append(record)

    added = 0
    corrected = 0
    for category, winner in LFA_2026_WINNERS:
        matches = by_category.get(_lfa_category_key(category), [])
        if len(matches) > 1:
            raise RuntimeError(f"Duplicate 2026 LFA winner records need review: {category}")
        if matches:
            record = matches[0]
            if record.person_name.strip().casefold() == winner.casefold():
                continue
            # The archived 2026 Lady of Lite entry was an approved
            # community submission naming Jada Chanell, not the final result.
            if category != "Lady of Lite" or record.person_name.strip().casefold() != "jada chanell":
                raise RuntimeError(f"Conflicting 2026 LFA winner needs review: {category}")
            prior_submission = record.source_submission_id
            correction = (
                "Correction (2026-11-23): the prior record named JADA CHANELL "
                f"(source submission #{prior_submission or 'unknown'}). "
                "The Vault administrator confirmed TY SHOTZ as the 2026 "
                "Lady of Lite winner. The original community submission "
                "is retained separately for historical review."
            )
            record.additional_details = "\n".join(
                part for part in (record.additional_details, correction) if part
            )
            record.category_name = category
            record.person_name = winner
            record.team_name = None
            record.source_submission_id = None
            record.source_information = LFA_2026_SOURCE
            corrected += 1
        else:
            db.add(LFARecord(
                year=2026,
                record_type="award_winner",
                category_name=category,
                person_name=winner,
                team_name=winner if category == "Best Team" else None,
                additional_details="5th Annual LiteFeet Awards ceremony: November 22, 2026.",
                source_information=LFA_2026_SOURCE,
                source_submission_id=None,
            ))
            added += 1
    return added, corrected


def seed():
    db = SessionLocal()

    try:
        historical = get_or_create_edition(db, 2023)
        get_or_create_edition(db, 2026)

        existing = {
            category.name
            for category in (
                db.query(DCACategory)
                .filter(
                    DCACategory.edition_id
                    == historical.id
                )
                .all()
            )
        }

        added = 0

        for name in HISTORICAL_CATEGORIES:
            if name in existing:
                continue

            normalized_name = " ".join(
                name.lower().split()
            )

            db.add(
                DCACategory(
                    edition_id=historical.id,
                    name=name,
                    normalized_name=normalized_name,
                    source_type="historical_2023",
                    status="candidate",
                )
            )

            added += 1

        lfa_added, lfa_corrected = seed_lfa_2026(db)
        db.commit()

        total = (
            db.query(DCACategory)
            .filter(
                DCACategory.edition_id
                == historical.id
            )
            .count()
        )

        print("2023 EDITION: READY")
        print("2026 EDITION: READY")
        print("CATEGORIES ADDED:", added)
        print("2023 CATEGORY TOTAL:", total)
        print("2026 LFA WINNERS ADDED:", lfa_added)
        print("2026 LFA WINNERS CORRECTED:", lfa_corrected)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()
