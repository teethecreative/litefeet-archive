from sqlalchemy import text

from app import (
    engine,
    init_db,
    ensure_person_role_columns,
    ensure_profile_enrichment_columns,
    normalize_profile_match_name,
)


def clean(value):
    return " ".join((value or "").strip().split())


def merge_alias(existing, incoming):
    final = []

    for part in f"{existing or ''},{incoming or ''}".replace("|", ",").split(","):
        part = clean(part)
        if part and part not in final:
            final.append(part)

    return ", ".join(final)


def looks_like_same_person(name, value):
    name_key = normalize_profile_match_name(name)
    value_key = normalize_profile_match_name(value)

    if not name_key or not value_key:
        return False

    if name_key == value_key:
        return True

    if name_key in value_key or value_key in name_key:
        return True

    return False


def main():
    init_db()
    ensure_person_role_columns()
    ensure_profile_enrichment_columns()

    updated = 0

    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT id, dance_name, aliases, team_affiliation
                FROM dancer_profiles
                WHERE team_affiliation IS NOT NULL
                  AND trim(team_affiliation) != ''
            """)
        ).mappings().all()

        for row in rows:
            name = row["dance_name"]
            team = row["team_affiliation"]

            if not looks_like_same_person(name, team):
                continue

            new_aliases = merge_alias(row.get("aliases"), team)

            conn.execute(
                text("""
                    UPDATE dancer_profiles
                    SET aliases = :aliases,
                        team_affiliation = ''
                    WHERE id = :id
                """),
                {
                    "id": row["id"],
                    "aliases": new_aliases,
                },
            )

            print("MOVED TEAM TO ALIAS:", name, "=>", team)
            updated += 1

    print("Updated:", updated)


if __name__ == "__main__":
    main()
