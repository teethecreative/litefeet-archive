import csv
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from app import (
    engine,
    init_db,
    ensure_person_role_columns,
    ensure_profile_slug_column,
    unique_profile_slug,
)


COLUMN_MAP = {
    "name": "24. What is your LiteFeet name?",
    "aliases": "25. Do you have any aliases, nicknames, or older names people know you by?",
    "team": "26. What team(s)/ fam(s)/ organization(s) are you part of?",
    "location": "27. What borough/city do you represent?",
    "era": "29. What era/generation do you feel most connected to?",
    "style": "30. How would you describe your LiteFeet style?",
    "moves": "35. What are your signature moves, tricks, habits, or moments people know you for?",
    "battle_moment": "47. What battle, event, cypher, or moment represents you best?",
    "battle_feats": "48. What are your strongest battle feats or accomplishments?",
    "bio": "54. What should your card description/bio mention?",
    "legacy": "55. What do you want people to remember you for in LiteFeet?",
}


def clean(value):
    return " ".join((value or "").strip().split())


def ensure_profile_enrichment_columns():
    dialect = engine.dialect.name

    new_columns = {
        "aliases": "TEXT",
        "era": "TEXT",
        "style_notes": "TEXT",
        "signature_moves": "TEXT",
        "battle_history": "TEXT",
        "legacy_notes": "TEXT",
        "csv_source_note": "TEXT",
        "updated_from_csv_at": "TEXT",
    }

    with engine.begin() as conn:
        if dialect == "postgresql":
            for column, column_type in new_columns.items():
                conn.execute(
                    text(f"ALTER TABLE dancer_profiles ADD COLUMN IF NOT EXISTS {column} {column_type}")
                )
        else:
            existing_columns = {
                row[1] for row in conn.execute(text("PRAGMA table_info(dancer_profiles)")).fetchall()
            }

            for column, column_type in new_columns.items():
                if column not in existing_columns:
                    conn.execute(text(f"ALTER TABLE dancer_profiles ADD COLUMN {column} {column_type}"))


def merge_text(existing, incoming):
    existing = clean(existing)
    incoming = clean(incoming)

    if not incoming:
        return existing

    if not existing:
        return incoming

    if incoming.lower() in existing.lower():
        return existing

    return f"{existing}\n\n{incoming}"


def table_columns(conn):
    if engine.dialect.name == "postgresql":
        rows = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'dancer_profiles'
            """)
        ).fetchall()
        return {row[0] for row in rows}

    rows = conn.execute(text("PRAGMA table_info(dancer_profiles)")).fetchall()
    return {row[1] for row in rows}


def find_existing_profile(conn, name, aliases):
    names_to_check = [name]

    if aliases:
        for alias in aliases.replace("/", ",").split(","):
            alias = clean(alias)
            if alias:
                names_to_check.append(alias)

    for possible_name in names_to_check:
        result = conn.execute(
            text("""
                SELECT *
                FROM dancer_profiles
                WHERE lower(dance_name) = lower(:name)
                LIMIT 1
            """),
            {"name": possible_name},
        ).mappings().first()

        if result:
            return result

    return None


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python import_profiles_from_yearbook_csv.py path/to/file.csv")

    csv_path = Path(sys.argv[1])

    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    init_db()
    ensure_person_role_columns()
    ensure_profile_slug_column()
    ensure_profile_enrichment_columns()

    created = 0
    updated = 0
    skipped = 0

    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        missing_columns = [
            column
            for column in COLUMN_MAP.values()
            if column not in (reader.fieldnames or [])
        ]

        if missing_columns:
            print("Missing columns:")
            for column in missing_columns:
                print("-", column)
            raise SystemExit("CSV columns do not match the expected form export.")

        rows = list(reader)

    with engine.begin() as conn:
        columns = table_columns(conn)

        for row in rows:
            name = clean(row.get(COLUMN_MAP["name"]))
            aliases = clean(row.get(COLUMN_MAP["aliases"]))
            team = clean(row.get(COLUMN_MAP["team"]))
            location = clean(row.get(COLUMN_MAP["location"]))
            era = clean(row.get(COLUMN_MAP["era"]))
            style = clean(row.get(COLUMN_MAP["style"]))
            moves = clean(row.get(COLUMN_MAP["moves"]))
            battle_moment = clean(row.get(COLUMN_MAP["battle_moment"]))
            battle_feats = clean(row.get(COLUMN_MAP["battle_feats"]))
            bio = clean(row.get(COLUMN_MAP["bio"]))
            legacy = clean(row.get(COLUMN_MAP["legacy"]))

            if not name:
                skipped += 1
                continue

            battle_history = "\n\n".join(
                value for value in [battle_moment, battle_feats] if value
            )

            existing = find_existing_profile(conn, name, aliases)

            if existing:
                data = {
                    "dance_name": existing["dance_name"] or name,
                    "aliases": merge_text(existing.get("aliases"), aliases),
                    "team_affiliation": merge_text(existing.get("team_affiliation"), team),
                    "borough_scene": merge_text(existing.get("borough_scene"), location),
                    "era": merge_text(existing.get("era"), era),
                    "style_notes": merge_text(existing.get("style_notes"), style),
                    "signature_moves": merge_text(existing.get("signature_moves"), moves),
                    "battle_history": merge_text(existing.get("battle_history"), battle_history),
                    "bio": merge_text(existing.get("bio"), bio),
                    "legacy_notes": merge_text(existing.get("legacy_notes"), legacy),
                    "role_tags": existing.get("role_tags") or "Dancer",
                    "csv_source_note": "Imported from LiteFeet Yearbook / Archive / Lock In form responses.",
                    "updated_from_csv_at": datetime.now().isoformat(timespec="seconds"),
                    "id": existing["id"],
                }

                update_fields = [
                    key for key in data.keys()
                    if key in columns and key != "id"
                ]

                set_clause = ", ".join(f"{key} = :{key}" for key in update_fields)

                conn.execute(
                    text(f"""
                        UPDATE dancer_profiles
                        SET {set_clause}
                        WHERE id = :id
                    """),
                    data,
                )

                updated += 1
                continue

            data = {
                "dance_name": name,
                "profile_slug": unique_profile_slug(name),
                "aliases": aliases,
                "team_affiliation": team,
                "borough_scene": location,
                "era": era,
                "style_notes": style,
                "signature_moves": moves,
                "battle_history": battle_history,
                "bio": bio,
                "legacy_notes": legacy,
                "source_url": "",
                "status": "Ghost Profile",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "role_tags": "Dancer",
                "csv_source_note": "Imported from LiteFeet Yearbook / Archive / Lock In form responses.",
                "updated_from_csv_at": datetime.now().isoformat(timespec="seconds"),
            }

            insert_data = {
                key: value
                for key, value in data.items()
                if key in columns
            }

            col_names = ", ".join(insert_data.keys())
            bind_names = ", ".join(f":{key}" for key in insert_data.keys())

            conn.execute(
                text(f"""
                    INSERT INTO dancer_profiles ({col_names})
                    VALUES ({bind_names})
                """),
                insert_data,
            )

            created += 1

    print(f"Done. Created {created}. Updated {updated}. Skipped {skipped}.")


if __name__ == "__main__":
    main()
