import json
from datetime import datetime

from sqlalchemy import text
from app import engine, init_db


def clean_details(items):
    return json.dumps(
        [{"label": label, "value": value} for label, value in items if value],
        ensure_ascii=False,
    )


def record_exists(title):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id FROM submissions WHERE title = :title LIMIT 1"),
            {"title": title},
        ).first()

    return result is not None


def insert_event(record):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO submissions (
                    submission_type,
                    title,
                    related_to,
                    source_url,
                    submitter_name,
                    submitter_role,
                    contact,
                    needs_verification,
                    review_status,
                    details_json,
                    created_at
                )
                VALUES (
                    :submission_type,
                    :title,
                    :related_to,
                    :source_url,
                    :submitter_name,
                    :submitter_role,
                    :contact,
                    :needs_verification,
                    :review_status,
                    :details_json,
                    :created_at
                )
                """
            ),
            {
                "submission_type": record["submission_type"],
                "title": record["title"],
                "related_to": record["related_to"],
                "source_url": record["source_url"],
                "submitter_name": record["submitter_name"],
                "submitter_role": record["submitter_role"],
                "contact": record["contact"],
                "needs_verification": record["needs_verification"],
                "review_status": record["review_status"],
                "details_json": clean_details(record["details"]),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )


EVENTS = [
    {
        "submission_type": "event",
        "title": "Beats & Bodies Pt. 2",
        "related_to": "Body Bag, LiteFeet producer battles, Beats & Bodies Pt. 2",
        "review_status": "Needs Verification",
        "source_url": "",
        "submitter_name": "LiteFeet Ledger",
        "submitter_role": "Archive System",
        "contact": "",
        "needs_verification": 1,
        "details": [
            ("Event Name", "Beats & Bodies Pt. 2"),
            ("Organization Name", "Body Bag"),
            ("Event Date", "2026-06-14"),
            ("Event Time", "7:00 PM"),
            ("Event Location", "2381 Belmont Ave, Bronx, NY"),
            ("Venue Notes", "2nd floor. Door on the left side."),
            ("Battle Type", "Producer Battles / Pass the Aux"),
            ("Age Restriction", "21+"),
            ("Entry", "$10 general. $20 smoking allowed. Ladies free until 7:30 PM."),
            ("Host", "Kid Smoove"),
            ("Judges", "Reel Hectic, Kid The Wiz, Flight, Black The Beast, Kid Smoove"),
            ("Event Results", "Fox 5 def. Kari | Coma def. Talented Sparkz, 2 Coma and 1 Tie | Phresh Tune def. KennDot, 2 Phresh and 1 Tie | BSN vs Lil Live ended in a Tie"),
            ("Results Status", "4 producer battle results added"),
            ("Needs Confirmation", "Exact venue or studio name. Special surprise 1v1 dance battle result. Full score for Fox 5 vs Kari."),
            ("Archive Note", "Seeded from community-submitted flyer and reported results. Keep marked Needs Verification until confirmed by host, judges, footage, or additional community sources."),
        ],
    }
]


def main():
    init_db()

    created = 0
    skipped = 0

    for event in EVENTS:
        if record_exists(event["title"]):
            skipped += 1
            print(f"Skipped existing event: {event['title']}")
            continue

        insert_event(event)
        created += 1
        print(f"Created event: {event['title']}")

    print(f"Done. Created {created}. Skipped {skipped}.")


if __name__ == "__main__":
    main()
