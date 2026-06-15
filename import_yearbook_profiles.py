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
    ensure_profile_enrichment_columns,
    unique_profile_slug,
)


COLUMNS = {
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
    "private_notes": "58. Is there anything you do NOT want included on your card?",
}


def clean(value):
    return " ".join((value or "").strip().split())


def merge_text(existing, incoming):
    existing = clean(existing)
    incoming = clean(incoming)

    if not incoming:
        return existing

    if not existing:
        return incoming

    if incoming.lower() in existing.lower():
        return existing

    return existing + "\n\n" + incoming


def split_aliases(value):
    value = clean(value)

    if not value:
        return []

    parts = []
    for chunk in value.replace("/", ",").replace("|", ",").split(","):
        chunk = clean(chunk)
        if chunk:
            parts.append(chunk)

    return parts


def find_profile(conn, name, aliases):
    search_names = [name] + split_aliases(aliases)

    for search_name in search_names:
        profile = conn.execute(
            text("""
                SELECT *
                FROM dancer_profiles
                WHERE lower(dance_name) = lower(:name)
                LIMIT 1
            """),
            {"name": search_name},
        ).mappings().first()

        if profile:
            return dict(profile)

    return None


def get_columns(conn):
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


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python import_yearbook_profiles.py path/to/yearbook.csv")

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
        fieldnames = reader.fieldnames or []

        required = [COLUMNS["name"]]
        missing_required = [col for col in required if col not in fieldnames]

        if missing_required:
            print("Missing required columns:")
            for col in missing_required:
                print("-", col)
            raise SystemExit("This does not look like the expected Yearbook CSV.")

        rows = list(reader)

    with engine.begin() as conn:
        existing_columns = get_columns(conn)

        for row in rows:
            name = clean(row.get(COLUMNS["name"]))

            if not name:
                skipped += 1
                continue

            aliases = clean(row.get(COLUMNS["aliases"]))
            team = clean(row.get(COLUMNS["team"]))
            location = clean(row.get(COLUMNS["location"]))
            era = clean(row.get(COLUMNS["era"]))
            style = clean(row.get(COLUMNS["style"]))
            moves = clean(row.get(COLUMNS["moves"]))
            battle_moment = clean(row.get(COLUMNS["battle_moment"]))
            battle_feats = clean(row.get(COLUMNS["battle_feats"]))
            bio = clean(row.get(COLUMNS["bio"]))
            legacy = clean(row.get(COLUMNS["legacy"]))
            private_notes = clean(row.get(COLUMNS["private_notes"]))

            battle_history = "\n\n".join(
                item for item in [battle_moment, battle_feats] if item
            )

            profile = find_profile(conn, name, aliases)

            if profile:
                values = {
                    "id": profile["id"],
                    "aliases": merge_text(profile.get("aliases"), aliases),
                    "team_affiliation": merge_text(profile.get("team_affiliation"), team),
                    "borough_scene": merge_text(profile.get("borough_scene"), location),
                    "era": merge_text(profile.get("era"), era),
                    "style_notes": merge_text(profile.get("style_notes"), style),
                    "signature_moves": merge_text(profile.get("signature_moves"), moves),
                    "battle_history": merge_text(profile.get("battle_history"), battle_history),
                    "bio": merge_text(profile.get("bio"), bio),
                    "legacy_notes": merge_text(profile.get("legacy_notes"), legacy),
                    "private_notes": merge_text(profile.get("private_notes"), private_notes),
                    "role_tags": profile.get("role_tags") or "Dancer",
                    "csv_source_note": "Imported from LiteFeet Yearbook / Archive / Lock In form responses.",
                    "updated_from_csv_at": datetime.now().isoformat(timespec="seconds"),
                }

                allowed_keys = [
                    key for key in values
                    if key in existing_columns and key != "id"
                ]

                set_clause = ", ".join(f"{key} = :{key}" for key in allowed_keys)

                conn.execute(
                    text(f"""
                        UPDATE dancer_profiles
                        SET {set_clause}
                        WHERE id = :id
                    """),
                    values,
                )

                updated += 1

            else:
                values = {
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
                    "private_notes": private_notes,
                    "source_url": "",
                    "status": "Ghost Profile",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "role_tags": "Dancer",
                    "csv_source_note": "Imported from LiteFeet Yearbook / Archive / Lock In form responses.",
                    "updated_from_csv_at": datetime.now().isoformat(timespec="seconds"),
                }

                insert_values = {
                    key: value
                    for key, value in values.items()
                    if key in existing_columns
                }

                conn.execute(
                    text(f"""
                        INSERT INTO dancer_profiles ({", ".join(insert_values.keys())})
                        VALUES ({", ".join(":" + key for key in insert_values.keys())})
                    """),
                    insert_values,
                )

                created += 1

    print(f"Done. Created {created}. Updated {updated}. Skipped {skipped}.")


if __name__ == "__main__":
    main()
