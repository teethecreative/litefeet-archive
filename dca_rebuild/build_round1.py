from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dca_rebuild.config import DATABASE_URL
from dca_rebuild.models import Base, DCACategory, DCAEdition


OLD_CATEGORIES = [
    # Original fixed 2023 categories
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
    "Best Producer Collab",
    "Best Balance",
    "Best Out of NY Dancer",
    "Most Underrated",
    "Best Musicality",
    "Best Event of 2023",

    # Unique additional 2023 suggestions
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


def normalize(value):
    return " ".join(value.lower().strip().split())


engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

try:
    historical = db.query(DCAEdition).filter_by(year=2023).first()

    if not historical:
        historical = DCAEdition(
            year=2023,
            title="Dancer's Choice Awards — August 2023",
            phase="archived",
            is_public=True,
        )
        db.add(historical)
        db.flush()

    current = db.query(DCAEdition).filter_by(year=2026).first()

    if not current:
        current = DCAEdition(
            year=2026,
            title="Dancer's Choice Awards 2026",
            phase="category_suggestions",
            is_public=True,
        )
        db.add(current)
        db.flush()

    # Make local historical pool exactly match our cleaned 46.
    existing = (
        db.query(DCACategory)
        .filter(DCACategory.edition_id == historical.id)
        .all()
    )

    wanted = {normalize(name): name for name in OLD_CATEGORIES}

    for category in existing:
        if category.normalized_name not in wanted:
            db.delete(category)

    db.flush()

    for normalized, name in wanted.items():
        category = (
            db.query(DCACategory)
            .filter(
                DCACategory.edition_id == historical.id,
                DCACategory.normalized_name == normalized,
            )
            .first()
        )

        if category:
            category.name = name
            category.source_type = "historical"
            category.status = "historical"
        else:
            db.add(
                DCACategory(
                    edition_id=historical.id,
                    name=name,
                    normalized_name=normalized,
                    source_type="historical",
                    status="historical",
                )
            )

    db.commit()

    total = (
        db.query(DCACategory)
        .filter(DCACategory.edition_id == historical.id)
        .count()
    )

    print()
    print("======================================")
    print(" DCA ROUND 1 DATA BUILD COMPLETE")
    print("======================================")
    print(f"Old categories: {total}")
    print("2026 edition: ready")
    print()

finally:
    db.close()
