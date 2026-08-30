from dca_rebuild.app import SessionLocal
from dca_rebuild.models import DCAEdition, DCACategory


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

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()
