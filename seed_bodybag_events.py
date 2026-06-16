import os
import json
from datetime import datetime
from sqlalchemy import text

if not os.environ.get("DATABASE_URL") and os.environ.get("ALLOW_LOCAL_SEED") != "1":
    raise SystemExit(
        "DATABASE_URL is not set. Run this in Render Shell to seed the live database. "
        "For local only, run: ALLOW_LOCAL_SEED=1 python3 seed_bodybag_events.py"
    )

import app

SEED_PREFIX = "seed:bodybag-event-sequence"

EVENTS = [
    {
        "seed_key": "body-bag-vol-1",
        "title": "Body Bag Vol. 1",
        "related_to": "Body Bag / Body Baggers",
        "review_status": "Needs Verification",
        "needs_verification": 1,
        "details": {
            "event_date": "",
            "date": "Needs confirmation",
            "time": "Needs confirmation",
            "location": "Needs confirmation",
            "battles": [],
            "notes": ["Missing flyer/info", "Battles need confirmation"],
            "sequence_order": 1,
            "series": "Body Bag",
            "confirmation_needed": [
                "Body Bag Vol. 1 details",
                "Date",
                "Time",
                "Location",
                "Battles",
            ],
        },
    },
    {
        "seed_key": "body-bag-vol-2",
        "title": "The Body Baggers Vol. 2",
        "related_to": "Body Bag / Body Baggers",
        "review_status": "Community Supported",
        "needs_verification": 1,
        "details": {
            "event_date": "2023-05-27",
            "date": "May 27, 2023",
            "time": "6 PM – 10 PM",
            "entry": "Free admission",
            "hosted_by": ["Chris Gzz", "Bito", "P.Cole", "Jayway"],
            "location": "New Cali",
            "address": "2026 Third Ave, New York, NY 10029",
            "food_drinks": "Food & drinks will be sold",
            "merch": "Body Bag merch will be sold",
            "producer_note": "Tee will be playing producer challenge beats",
            "sequence_order": 2,
            "series": "Body Bag",
            "battles": [
                {"name": "Flii Boogie vs Kid Smoove", "note": "TKO Belt on the Line"},
                {"name": "E-Solo vs D Rillz"},
                {"name": "Tyke Star & X Lyve vs Noah Lot & Red Ink"},
                {"name": "Crazy Cee vs Billie Buckz"},
                {"name": "Soundcloud vs Fire Flames"},
                {"name": "Flee Scrilla vs Trey Otto"},
                {"name": "Tah Swag vs BBQ", "note": "Shake Battle"},
                {"name": "Soundwave vs Mo The Dancer"},
                {"name": "Body Bag Cypher Vol. 2", "note": "Producer Battle"},
            ],
        },
    },
    {
        "seed_key": "body-bag-vol-3",
        "title": "Body Bag Vol. 3",
        "related_to": "Body Bag / Body Baggers",
        "review_status": "Community Supported",
        "needs_verification": 1,
        "details": {
            "event_date": "2023-08-18",
            "date": "August 18, 2023",
            "time": "6 PM – 10 PM",
            "entry": "Free admission",
            "location": "611 East 13th St",
            "merch": "Merch will be available",
            "rules": [
                "No food or drinks allowed in the gym",
                "Only sneakers allowed",
            ],
            "sequence_order": 3,
            "series": "Body Bag",
            "battles": [
                {"name": "E-Solo vs D Rillz", "note": "Main Event"},
                {"name": "Mel Live vs Mr Jones"},
                {"name": "Jada Chanell vs Jizzi Jazz"},
                {"name": "Cashew vs Soundcloud"},
                {"name": "Trey Otto vs Bentley"},
                {"name": "Body Bag Cypher Vol. 3"},
            ],
        },
    },
    {
        "seed_key": "body-bag-vol-4",
        "title": "Body Bag Vol. 4",
        "related_to": "Body Bag / Body Baggers",
        "review_status": "Community Supported",
        "needs_verification": 1,
        "details": {
            "event_date": "2024-02-23",
            "date": "February 23, 2024",
            "time": "6 PM – 10 PM",
            "entry": "Free admission",
            "venue": "Studio 259",
            "location": "Studio 259",
            "address": "259 East 134th St, Bronx, NY 10470",
            "message": "Please come drama free",
            "ig_note": "Follow @litefeetawards for all details",
            "sequence_order": 4,
            "series": "Body Bag",
            "battles": [
                {"name": "Bomb Squad vs 2 Crafty"},
                {"name": "Jay Wavyy / Mel Live vs Soundcloud / Doomzday"},
                {"name": "Deaf Boy vs Kid O"},
                {"name": "Lek Smoove vs Moon Lite"},
                {"name": "Tre Buckz vs Reem Lite"},
            ],
        },
    },
    {
        "seed_key": "bodybag-5-outside-edition",
        "title": "Bodybag 5: Outside Edition",
        "related_to": "Body Bag / Body Baggers",
        "review_status": "Community Supported",
        "needs_verification": 1,
        "details": {
            "event_date": "",
            "date": "Needs confirmation",
            "time": "4 PM – 9 PM sharp",
            "battles_start": "4:30 PM sharp",
            "host": "Jada Chanell",
            "location": "Sakura Park, Harlem, NY",
            "address": "500 Riverside Dr, New York, NY",
            "message": "We Outsideeeeeee",
            "sequence_order": 5,
            "series": "Body Bag",
            "confirmation_needed": ["Bodybag 5 date/year"],
            "rules": [
                "Each round is 1 min 30 secs",
                "It is a 3 twerk rule",
                "Give the dancer space on the dance floor",
                "Everybody come and have fun",
                "Leave all the drama home",
                "Body Bag Cypher will happen",
                "All of these battles will be on YouTube",
            ],
            "battles": [
                {"name": "M Nauti vs Trey Buckz"},
                {"name": "Boy Nice vs Moon Lite"},
                {"name": "Doomz Day vs Yakk Live"},
                {"name": "Kid O vs Baby Sparkz"},
                {"name": "Looney vs Looney"},
                {"name": "Bodybag Cypher"},
            ],
        },
    },
    {
        "seed_key": "body-bag-6",
        "title": "Body Bag 6",
        "related_to": "Body Bag / Body Baggers",
        "review_status": "Community Supported",
        "needs_verification": 1,
        "details": {
            "event_date": "2024-08-23",
            "date": "Friday, August 23, 2024",
            "time": "6 PM – Till",
            "host": "Jada Chanell",
            "location": "Sakura Park, Harlem, NY",
            "address": "500 Riverside Dr, New York, NY 10027",
            "note": "Venue can possibly change due to weather",
            "message": "Come through drama free",
            "sequence_order": 6,
            "series": "Body Bag",
            "battles": [
                {"name": "E Chakra vs Lexii", "note": "She-KO Championship"},
                {"name": "Kid Mix vs Red Ink"},
                {"name": "Tah Swag vs Uno Lot"},
                {"name": "Tay Tonic vs Tay Millz"},
                {"name": "Soundwave vs Baby Sparkz"},
                {"name": "Soundcloud vs Q Tip"},
                {"name": "Tazz vs Freshy"},
                {"name": "Yakk Live vs BBQ"},
                {"name": "BSN vs Reel Hectic", "note": "Producer Battle"},
            ],
        },
    },
    {
        "seed_key": "body-bag-7-royal-rumble",
        "title": "Body Bag 7: Royal Rumble",
        "related_to": "Body Bag / Body Baggers",
        "review_status": "Community Supported",
        "needs_verification": 1,
        "details": {
            "event_date": "2025-02-22",
            "date": "February 22, 2025",
            "time": "6 PM – 10 PM",
            "venue": "Ripley Grier Studios",
            "location": "Ripley Grier Studios",
            "address": "520 8th Avenue, New York, NY 10018",
            "entry": "$10 till 8 PM, $25 after",
            "requirement": "Must have ID to enter",
            "host": "Jada Chanell",
            "sequence_order": 7,
            "series": "Body Bag",
            "battles": [
                {"name": "E Solo vs Noah Lot"},
                {"name": "2 Crafty vs Groove Era"},
                {"name": "Doomz Day & QTip vs Deaf Boy & Sparkz Rah"},
                {
                    "name": "The Royal Rumble",
                    "featuring": [
                        "Jedi",
                        "Cashew",
                        "Moon Lite",
                        "Iceman",
                        "Tay Tonic",
                        "Yak Live",
                        "Fresh Juice",
                        "Playdoh",
                    ],
                },
            ],
        },
    },
    {
        "seed_key": "body-bag-8",
        "title": "Body Bag 8",
        "related_to": "Body Bag / Body Baggers",
        "review_status": "Community Supported",
        "needs_verification": 1,
        "details": {
            "event_date": "2025-07-26",
            "date": "July 26, 2025",
            "time": "Needs confirmation",
            "entry": "Needs confirmation",
            "location": "Sakura Park",
            "address": "500 Riverside Dr, New York, NY",
            "sequence_order": 8,
            "series": "Body Bag",
            "confirmation_needed": ["Body Bag 8 time and entry"],
            "battles": [
                {"name": "Moon Lite vs Radar"},
                {"name": "Sparkz Rah vs Q-Tip"},
                {"name": "Trackstar vs Wild N Out"},
                {"name": "Money Mase vs Ash Rocket", "note": "Krucible Finals"},
            ],
        },
    },
    {
        "seed_key": "body-bag-9",
        "title": "Body Bag 9",
        "related_to": "Body Bag / Body Baggers",
        "review_status": "Community Supported",
        "needs_verification": 1,
        "details": {
            "official_title_note": "Flyer/title needs confirmation as Bodybag / Body Bag 9",
            "event_date": "2025-08-29",
            "date": "August 29, 2025",
            "time": "6 PM – 10 PM",
            "entry": "Free before 8:30 PM, $10 after",
            "venue": "Pearl Studios",
            "location": "Pearl Studios",
            "room": "Room 414",
            "address": "500 8th Ave, New York, NY",
            "sequence_order": 9,
            "series": "Body Bag",
            "confirmation_needed": [
                "Whether the August 29, 2025 Pearl Studios event should officially be listed as Body Bag 9"
            ],
            "battles": [
                {"name": "40 Pounds vs Moe Black"},
                {"name": "Jayy Wavy vs Kid Smoove"},
                {"name": "D Rillz vs Wild Realz"},
                {"name": "Doomz Day vs Sparkz Ra"},
                {"name": "XO Wavey vs Tay Millz"},
                {"name": "Yaffi vs Redy Rell"},
            ],
        },
    },
    {
        "seed_key": "body-bag-10-elimination-chamber",
        "title": "Body Bag 10: Elimination Chamber",
        "related_to": "Body Bag / Body Baggers",
        "review_status": "Community Supported",
        "needs_verification": 1,
        "details": {
            "event_date": "2026-04-25",
            "date": "April 25, 2026",
            "time": "6 PM – 10 PM",
            "entry": "$10 before 7:30 PM, $20 after",
            "venue": "Pearl Studios",
            "location": "Pearl Studios",
            "room": "3rd Floor, Room 301",
            "address": "500 8th Ave, New York, NY 10018",
            "hosted_by": ["40 Pounds"],
            "music_by": ["Juanye"],
            "sequence_order": 10,
            "series": "Body Bag",
            "main_event": "Jay Wavvy vs Crazy C",
            "elimination_chamber_match": [
                "Kid Smoove",
                "Noah Lot",
                "Soundcloud",
                "Sparkz Ra",
                "Jay Bull",
                "Cashew",
                "Moon Lite",
                "Diggy",
            ],
            "bonus_battle": {
                "name": "Lady Live vs Nae Berry",
                "note": "One Round of Fire",
            },
            "special_guest_judges": [
                "Spaceman",
                "Larry Smoove",
                "Mr Jones",
                "Kid The Wiz",
                "P Rockz",
                "Kid Robot",
            ],
            "battles": [
                {"name": "Jay Wavvy vs Crazy C", "note": "Main Event"},
                {
                    "name": "Elimination Chamber Match",
                    "featuring": [
                        "Kid Smoove",
                        "Noah Lot",
                        "Soundcloud",
                        "Sparkz Ra",
                        "Jay Bull",
                        "Cashew",
                        "Moon Lite",
                        "Diggy",
                    ],
                },
                {"name": "Lady Live vs Nae Berry", "note": "One Round of Fire"},
            ],
        },
    },
    {
        "seed_key": "smallroom-sundays-420-edition",
        "title": "Smallroom Sundays: 4/20 Edition",
        "related_to": "Smallroom Sundays / Body Bag Related",
        "review_status": "Community Supported",
        "needs_verification": 1,
        "details": {
            "event_date": "2026-04-19",
            "date": "April 19, 2026",
            "time": "4 PM – 7 PM",
            "location": "Bronx, NY",
            "address": "Purchased entry for location",
            "entry": "Purchased entry required",
            "sequence_order": 10.5,
            "series": "Related / Special Events",
            "confirmation_needed": [
                "Whether Smallroom Sundays should be listed as part of the Body Bag-related sequence or kept as a separate related event"
            ],
            "battles": [
                {"name": "Trey Otto vs Tre Buckz"},
                {"name": "Red Ink vs H", "note": "H listed as UK"},
                {"name": "Nem Lite vs Ty", "note": "Ty listed as UK"},
            ],
        },
    },
    {
        "seed_key": "money-in-the-bank-2026",
        "title": "Money in the Bank",
        "related_to": "Body Bag",
        "review_status": "Community Supported",
        "needs_verification": 1,
        "details": {
            "presented_by": "Body Bag",
            "event_date": "2026-06-06",
            "date": "June 6, 2026",
            "time": "6 PM – 10 PM",
            "entry": "$10 before 7:30 PM, $20 after",
            "venue": "New Heat Studios",
            "location": "New Heat Studios",
            "address": "2 Prince St, Brooklyn, NY",
            "sequence_order": 11,
            "series": "Related / Special Events",
            "battles": [
                {"name": "Jada Chanell vs Ty Shotz", "note": "One Round of Fire"},
                {"name": "Boy Q vs Nem Lite"},
                {"name": "Moon Lite vs Hype Star"},
                {
                    "name": "Tah Swag vs BBQ vs Kid Smoove vs Radar",
                    "note": "Fatal 4 Way for the Money in the Bank",
                },
                {"name": "Noah Lot vs D Rillz", "note": "Main Event"},
            ],
        },
    },
]

now = datetime.now().isoformat(timespec="seconds")

with app.engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY,
            submission_type TEXT,
            title TEXT,
            related_to TEXT,
            source_url TEXT,
            submitter_name TEXT,
            submitter_role TEXT,
            contact TEXT,
            needs_verification INTEGER DEFAULT 0,
            review_status TEXT DEFAULT 'Pending Review',
            details_json TEXT,
            created_at TEXT NOT NULL
        )
    """))

    for event in EVENTS:
        conn.execute(
            text("""
                DELETE FROM submissions
                WHERE submission_type = 'event'
                AND source_url = :source_url
            """),
            {"source_url": f"{SEED_PREFIX}:{event['seed_key']}"},
        )

    for event in EVENTS:
        conn.execute(
            text("""
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
            """),
            {
                "submission_type": "event",
                "title": event["title"],
                "related_to": event["related_to"],
                "source_url": f"{SEED_PREFIX}:{event['seed_key']}",
                "submitter_name": "Tee TheCreative",
                "submitter_role": "Ledger Admin / Archivist",
                "contact": "teethecreative@gmail.com",
                "needs_verification": event["needs_verification"],
                "review_status": event["review_status"],
                "details_json": json.dumps(event["details"], ensure_ascii=False),
                "created_at": now,
            },
        )

    total = conn.execute(text("""
        SELECT COUNT(*)
        FROM submissions
        WHERE submission_type = 'event'
        AND source_url LIKE :prefix
    """), {"prefix": f"{SEED_PREFIX}:%"}).scalar()

print(f"Seeded {total} Body Bag / related event records.")
