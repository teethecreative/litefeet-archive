import json
import re
from datetime import datetime

from sqlalchemy import text

from app import (
    engine,
    init_db,
    ensure_person_role_columns,
    ensure_profile_slug_column,
    unique_profile_slug,
)


PERSON_FIELD_ROLES = {
    "Host": "Host",
    "Judges": "Judge",
    "Judge": "Judge",
    "Battle List": "Dancer",
    "Planned Battle List": "Dancer",
}


SKIP_NAMES = {
    "",
    "format",
    "label",
    "main event",
    "one round of fire",
    "fatal 4-way for the money in the bank",
    "affiliations shown",
    "producer battles",
    "pass the aux",
    "mixed",
    "tbd",
    "bronx",
    "body bag",
}


def clean_name(name):
    name = re.sub(r"\(.*?\)", "", name or "")
    name = re.sub(r"\bFormat:.*$", "", name, flags=re.I)
    name = re.sub(r"\bLabel:.*$", "", name, flags=re.I)
    name = re.sub(r"\bAffiliations shown:.*$", "", name, flags=re.I)
    name = name.replace("—", "-")
    name = name.strip(" -:,\n\r\t")

    return " ".join(name.split())


def split_people(value):
    value = value or ""
    value = value.replace("\r", "\n")

    chunks = []

    for line in value.split("\n"):
        line = clean_name(line)

        if not line:
            continue

        line = re.sub(r"\bdef\.?\b", " vs ", line, flags=re.I)
        line = re.sub(r"\bversus\b", " vs ", line, flags=re.I)
        parts = re.split(r"\s+\bvs\b\s+|\s+\bv\b\s+|\|", line, flags=re.I)

        for part in parts:
            part = clean_name(part)

            if " - " in part:
                part = clean_name(part.split(" - ")[0])

            if part and part.lower() not in SKIP_NAMES:
                chunks.append(part)

    cleaned = []

    for chunk in chunks:
        if chunk.lower() not in SKIP_NAMES and chunk not in cleaned:
            cleaned.append(chunk)

    return cleaned


def merge_roles(existing_roles, new_role):
    roles = []

    for role in (existing_roles or "").split(","):
        role = role.strip()
        if role and role not in roles:
            roles.append(role)

    for role in (new_role or "").split(","):
        role = role.strip()
        if role and role not in roles:
            roles.append(role)

    return ", ".join(roles)


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


def upsert_person(conn, name, role, source_note):
    name = clean_name(name)

    if not name or name.lower() in SKIP_NAMES:
        return "skipped"

    existing = conn.execute(
        text("""
            SELECT *
            FROM dancer_profiles
            WHERE lower(dance_name) = lower(:dance_name)
            LIMIT 1
        """),
        {"dance_name": name},
    ).mappings().first()

    if existing:
        merged_roles = merge_roles(existing.get("role_tags"), role)

        conn.execute(
            text("""
                UPDATE dancer_profiles
                SET role_tags = :role_tags
                WHERE id = :id
            """),
            {
                "role_tags": merged_roles,
                "id": existing["id"],
            },
        )

        return "updated"

    columns = table_columns(conn)

    data = {
        "dance_name": name,
        "profile_slug": unique_profile_slug(name),
        "team_affiliation": "",
        "borough_scene": "",
        "bio": f"Ghost profile created from Ledger records. First detected from: {source_note}",
        "source_url": "",
        "status": "Ghost Profile",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "role_tags": role,
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

    return "created"


def main():
    init_db()
    ensure_person_role_columns()
    ensure_profile_slug_column()

    records = []

    with engine.connect() as conn:
        records = conn.execute(
            text("""
                SELECT id, title, submission_type, details_json
                FROM submissions
                ORDER BY created_at ASC
            """)
        ).mappings().all()

    created = 0
    updated = 0
    skipped = 0

    with engine.begin() as conn:
        for record in records:
            details = json.loads(record["details_json"] or "[]")
            detail_map = {
                item.get("label", ""): item.get("value", "")
                for item in details
            }

            battle_type = detail_map.get("Battle Type", "")
            battle_role = "Producer" if "producer" in battle_type.lower() else "Dancer"

            for label, value in detail_map.items():
                if label in {"Host"}:
                    names = split_people(value)

                    for name in names:
                        result = upsert_person(conn, name, "Host", record["title"])
                        created += result == "created"
                        updated += result == "updated"
                        skipped += result == "skipped"

                elif label in {"Judges", "Judge"}:
                    for name in split_people(value.replace(",", "\n")):
                        result = upsert_person(conn, name, "Judge", record["title"])
                        created += result == "created"
                        updated += result == "updated"
                        skipped += result == "skipped"

                elif label in {"Battle List", "Planned Battle List"}:
                    for name in split_people(value):
                        result = upsert_person(conn, name, battle_role, record["title"])
                        created += result == "created"
                        updated += result == "updated"
                        skipped += result == "skipped"

    print(f"Done. Created {created}. Updated {updated}. Skipped {skipped}.")


if __name__ == "__main__":
    main()
