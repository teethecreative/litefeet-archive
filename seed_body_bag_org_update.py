import json
from app import engine
from sqlalchemy import text


def set_detail(details, label, value):
    for item in details:
        if item.get("label") == label:
            item["value"] = value
            return
    details.append({"label": label, "value": value})


with engine.begin() as conn:
    row = conn.execute(
        text("""
            SELECT id, details_json
            FROM submissions
            WHERE title = 'Beats & Bodies Pt. 2'
            LIMIT 1
        """)
    ).mappings().first()

    if not row:
        raise SystemExit("Beats & Bodies Pt. 2 not found.")

    details = json.loads(row["details_json"] or "[]")

    set_detail(details, "Organizer", "Body Bag")
    set_detail(details, "Event Host", "Body Bag")
    set_detail(details, "Organization Name", "Body Bag")
    set_detail(details, "Studio", "C.O.W. Studios")
    set_detail(details, "Borough", "Bronx")

    conn.execute(
        text("""
            UPDATE submissions
            SET details_json = :details_json
            WHERE id = :event_id
        """),
        {
            "details_json": json.dumps(details, ensure_ascii=False),
            "event_id": row["id"],
        },
    )

print("Updated Body Bag organizer fields.")
