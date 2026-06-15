from datetime import datetime

from app import engine, init_db, ensure_person_role_columns
from sqlalchemy import text


PEOPLE = [
    {
        "dance_name": "Fox 5",
        "role_tags": "Producer",
        "bio": "Ghost producer profile created from Beats & Bodies Pt. 2.",
    },
    {
        "dance_name": "Kari",
        "role_tags": "Producer",
        "bio": "Ghost producer profile created from Beats & Bodies Pt. 2.",
    },
    {
        "dance_name": "Coma",
        "role_tags": "Producer",
        "bio": "Ghost producer profile created from Beats & Bodies Pt. 2.",
    },
    {
        "dance_name": "Talented Sparkz",
        "role_tags": "Producer",
        "bio": "Ghost producer profile created from Beats & Bodies Pt. 2.",
    },
    {
        "dance_name": "KennDot",
        "role_tags": "Producer",
        "bio": "Ghost producer profile created from Beats & Bodies Pt. 2.",
    },
    {
        "dance_name": "Phresh Tune",
        "role_tags": "Producer",
        "bio": "Ghost producer profile created from Beats & Bodies Pt. 2.",
    },
    {
        "dance_name": "BSN",
        "role_tags": "Producer",
        "bio": "Ghost producer profile created from Beats & Bodies Pt. 2.",
    },
    {
        "dance_name": "Lil Live",
        "role_tags": "Producer",
        "bio": "Ghost producer profile created from Beats & Bodies Pt. 2.",
    },
    {
        "dance_name": "Kid Smoove",
        "role_tags": "Dancer, Producer, Host, Judge",
        "bio": "Ghost profile connected to Beats & Bodies Pt. 2 as host and judge.",
    },
    {
        "dance_name": "Reel Hectic",
        "role_tags": "Dancer, Judge",
        "bio": "Ghost profile connected to Beats & Bodies Pt. 2 as a judge.",
    },
    {
        "dance_name": "Kid The Wiz",
        "role_tags": "Dancer, Judge",
        "bio": "Ghost profile connected to Beats & Bodies Pt. 2 as a judge.",
    },
    {
        "dance_name": "Flight",
        "role_tags": "Dancer, Judge",
        "bio": "Ghost profile connected to Beats & Bodies Pt. 2 as a judge.",
    },
    {
        "dance_name": "Black The Beast",
        "role_tags": "Dancer, Judge",
        "bio": "Ghost profile connected to Beats & Bodies Pt. 2 as a judge.",
    },
]


def merge_roles(existing_roles, new_roles):
    roles = []

    for role in (existing_roles or "").split(",") + (new_roles or "").split(","):
        role = role.strip()

        if role and role not in roles:
            roles.append(role)

    return ", ".join(roles)


def table_columns(conn):
    dialect = engine.dialect.name

    if dialect == "postgresql":
        rows = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'dancer_profiles'
                """
            )
        ).fetchall()
        return {row[0] for row in rows}

    rows = conn.execute(text("PRAGMA table_info(dancer_profiles)")).fetchall()
    return {row[1] for row in rows}


def main():
    init_db()
    ensure_person_role_columns()

    created = 0
    updated = 0

    with engine.begin() as conn:
        columns = table_columns(conn)

        for person in PEOPLE:
            existing = conn.execute(
                text(
                    """
                    SELECT *
                    FROM dancer_profiles
                    WHERE lower(dance_name) = lower(:dance_name)
                    LIMIT 1
                    """
                ),
                {"dance_name": person["dance_name"]},
            ).mappings().first()

            if existing:
                merged_roles = merge_roles(existing.get("role_tags"), person["role_tags"])

                conn.execute(
                    text(
                        """
                        UPDATE dancer_profiles
                        SET role_tags = :role_tags
                        WHERE id = :id
                        """
                    ),
                    {
                        "role_tags": merged_roles,
                        "id": existing["id"],
                    },
                )

                updated += 1
                continue

            data = {
                "dance_name": person["dance_name"],
                "team_affiliation": "",
                "borough_scene": "",
                "bio": person["bio"],
                "source_url": "",
                "status": "Ghost Profile",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "role_tags": person["role_tags"],
            }

            insert_data = {
                key: value
                for key, value in data.items()
                if key in columns
            }

            col_names = ", ".join(insert_data.keys())
            bind_names = ", ".join(f":{key}" for key in insert_data.keys())

            conn.execute(
                text(
                    f"""
                    INSERT INTO dancer_profiles ({col_names})
                    VALUES ({bind_names})
                    """
                ),
                insert_data,
            )

            created += 1

    print(f"Done. Created {created}. Updated {updated}.")


if __name__ == "__main__":
    main()
