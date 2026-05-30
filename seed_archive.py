import json
from datetime import datetime

from app import engine, init_db
from sqlalchemy import text


def clean_details(items):
    return json.dumps(
        [{"label": label, "value": value} for label, value in items if value],
        ensure_ascii=False,
    )


STARTER_RECORDS = [
    {
        "submission_type": "historical_claim",
        "title": "LiteFeet Origins Research Queue",
        "related_to": "LiteFeet history",
        "review_status": "Needs Verification",
        "source_url": "",
        "submitter_name": "LiteFeet Archive",
        "submitter_role": "Archive System",
        "contact": "",
        "details": [
            ("Claim Text", "The archive is collecting community-verified information about LiteFeet origins, early dancers, crews, battles, music, moves, and cultural evolution."),
            ("Claim Confidence", "Needs community review"),
            ("Archive Note", "This is a starter research record. Community members can vote true, false, or debatable and submit source links or corrections."),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "Harlem Shake / Bad One / Get Lite Research Queue",
        "related_to": "Harlem Shake, Bad One, Get Lite, LiteFeet history",
        "review_status": "Needs Verification",
        "source_url": "",
        "submitter_name": "LiteFeet Archive",
        "submitter_role": "Archive System",
        "contact": "",
        "details": [
            ("Claim Text", "The archive is collecting source-backed context on Harlem Shake, Bad One, Get Lite, and their relationship to LiteFeet history and movement culture."),
            ("Claim Confidence", "Needs community review"),
            ("Archive Note", "This record is intentionally open for community verification, correction, and source submissions."),
        ],
    },
    {
        "submission_type": "award_info",
        "title": "LiteFeet Awards Archive",
        "related_to": "LiteFeet Awards",
        "review_status": "Community Supported",
        "source_url": "",
        "submitter_name": "LiteFeet Archive",
        "submitter_role": "Archive System",
        "contact": "",
        "details": [
            ("Award Category", "LiteFeet Awards Archive Overview"),
            ("Award Context", "This section will collect LiteFeet Awards winners, nominees, Hall of Fame records, ceremony updates, clips, flyers, and community-submitted corrections."),
            ("Archive Note", "Specific winners and nominees should be added as separate records with source links or community verification."),
        ],
    },
    {
        "submission_type": "event",
        "title": "Upcoming LiteFeet Events",
        "related_to": "LiteFeet events",
        "review_status": "Community Supported",
        "source_url": "",
        "submitter_name": "LiteFeet Archive",
        "submitter_role": "Archive System",
        "contact": "",
        "details": [
            ("Event Name", "Upcoming LiteFeet Events"),
            ("Event Details", "This section will collect upcoming battles, showcases, workshops, award updates, host announcements, flyers, battle cards, and result links."),
            ("Archive Note", "Event hosts can submit links and official results for review."),
        ],
    },
    {
        "submission_type": "battle_result",
        "title": "Battle Results Archive",
        "related_to": "LiteFeet battle records",
        "review_status": "Community Supported",
        "source_url": "",
        "submitter_name": "LiteFeet Archive",
        "submitter_role": "Archive System",
        "contact": "",
        "details": [
            ("Battle Event", "Battle Results Archive"),
            ("Battle Context", "This section will collect recorded LiteFeet battles, winners, event dates, judges, categories, source links, and community verification counts."),
            ("Archive Note", "Individual battle results should be added as separate records with video, flyer, host, or community confirmation."),
        ],
    },
    {
        "submission_type": "dancer_profile",
        "title": "Dancer Directory",
        "related_to": "LiteFeet dancers",
        "review_status": "Community Supported",
        "source_url": "",
        "submitter_name": "LiteFeet Archive",
        "submitter_role": "Archive System",
        "contact": "",
        "details": [
            ("Dancer Name / Alias", "Dancer Directory"),
            ("Known For", "This section will collect dancer profiles, aliases, crews, battle records, awards, videos, community context, and source links."),
            ("Archive Note", "Individual dancer profiles should be added as separate records and reviewed before becoming public."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "LiteFeet Move Library",
        "related_to": "LiteFeet moves and style vocabulary",
        "review_status": "Needs Verification",
        "source_url": "",
        "submitter_name": "LiteFeet Archive",
        "submitter_role": "Archive System",
        "contact": "",
        "details": [
            ("Move / Style Name", "LiteFeet Move Library"),
            ("Move Origin / Context", "This section will document LiteFeet steps, movement vocabulary, variations, examples, tutorials, and community explanations."),
            ("Archive Note", "Move origins and popularization claims should be verified through source links and community review."),
        ],
    },
    {
        "submission_type": "source_link",
        "title": "LiteFeet Source Library",
        "related_to": "LiteFeet media archive",
        "review_status": "Community Supported",
        "source_url": "",
        "submitter_name": "LiteFeet Archive",
        "submitter_role": "Archive System",
        "contact": "",
        "details": [
            ("Source Title", "LiteFeet Source Library"),
            ("Source Context", "This section will collect videos, flyers, interviews, recap posts, award clips, tutorials, articles, and other links that help document LiteFeet history and current activity."),
            ("Source Platform", "Links only for MVP"),
        ],
    },
    {
        "submission_type": "host_affiliation",
        "title": "Event Host Network",
        "related_to": "LiteFeet event hosts",
        "review_status": "Community Supported",
        "source_url": "",
        "submitter_name": "LiteFeet Archive",
        "submitter_role": "Archive System",
        "contact": "",
        "details": [
            ("Host / Organization Name", "Event Host Network"),
            ("Host Request", "This section will collect event host profiles, affiliated event pages, official results, flyers, recaps, and host-submitted updates."),
            ("Archive Note", "Hosts can submit event links and results for review."),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "Community Verification System",
        "related_to": "Archive verification",
        "review_status": "Needs Verification",
        "source_url": "",
        "submitter_name": "LiteFeet Archive",
        "submitter_role": "Archive System",
        "contact": "",
        "details": [
            ("Claim Text", "The archive uses community verification so users can mark claims true, false, or debatable and add context or source links."),
            ("Claim Confidence", "Archive policy"),
            ("Archive Note", "This record explains how public verification will support the archive."),
        ],
    },
]


def record_exists(title):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id FROM submissions WHERE title = :title LIMIT 1"),
            {"title": title},
        ).first()

    return result is not None


def insert_record(record):
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
                "needs_verification": 1,
                "review_status": record["review_status"],
                "details_json": clean_details(record["details"]),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )


def main():
    init_db()

    created = 0
    skipped = 0

    for record in STARTER_RECORDS:
        if record_exists(record["title"]):
            skipped += 1
            print(f"Skipped existing record: {record['title']}")
            continue

        insert_record(record)
        created += 1
        print(f"Created record: {record['title']}")

    print(f"Done. Created {created}. Skipped {skipped}.")


if __name__ == "__main__":
    main()
