# The LiteFeet Vault — Unabridged Archive Research Source Export

**Repository source snapshot: November 6, 2026.** Contents are reproduced from source files for internal archive research. No code executed. Historical claims, planned events, aliases and unverified notes are not automatically suitable for public publication. Source record labels are retained as written.

**This file does not include the 900k-character original app implementation**, which is application code rather than an archival research dataset. Read its `verification_votes` and `/verify` handlers in the repository instead.

## litefeet_seed_data.py

[Open original file](https://github.com/teethecreative/litefeet-archive/blob/main/litefeet_seed_data.py)

```python
LITEFEET_RESEARCH_RECORDS = [
    {
        "submission_type": "historical_claim",
        "title": "LiteFeet / Get Lite Emerged from Harlem and the Bronx",
        "related_to": "LiteFeet origins, Get Lite, Harlem, Bronx",
        "review_status": "Community Supported",
        "source_url": "https://daily.redbullmusicacademy.com/2013/05/new-york-stories-emma-warren/",
        "details": [
            ("Claim Text", "LiteFeet, also written Lite Feet and often described as getting lite, is a New York street dance culture connected to Harlem and the Bronx in the early-to-mid 2000s."),
            ("Confidence", "High based on multiple public sources, but still open to community context and correction."),
            ("Sources to Review", "Red Bull Music Academy Daily, Vulture, STEEZY, CBS/Paramount, and academic writing on LiteFeet."),
            ("Archive Note", "Community members can add details about early dancers, crews, courts, parties, battles, and borough-specific history."),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "The Real Harlem Shake Predates LiteFeet",
        "related_to": "Harlem Shake, LiteFeet roots, Al B, Rucker Park",
        "review_status": "Community Supported",
        "source_url": "https://www.smithsonianmag.com/smart-news/presenting-the-real-harlem-shake-21838530/",
        "details": [
            ("Claim Text", "The real Harlem Shake predates LiteFeet and helped shape the movement vocabulary, feeling, and cultural lineage connected to LiteFeet."),
            ("Confidence", "High, but exact origin details vary by source and community memory."),
            ("Sources to Review", "Smithsonian, DNAinfo, IUDance, AllHipHop, and Vulture."),
            ("Archive Note", "This claim should collect memories and sources around Al B / Al Cisco / Albert Boyce, Rucker Park, Go Crazy Boyz, music videos, and Harlem dance history."),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "The 2013 Harlem Shake Meme Is Not the Real Harlem Shake",
        "related_to": "Harlem Shake meme, real Harlem Shake, cultural confusion",
        "review_status": "Community Supported",
        "source_url": "https://www.dance-enthusiast.com/features/view/Lite-Feet-Chrybaby-Cozie/",
        "details": [
            ("Claim Text", "The 2013 viral Harlem Shake meme is not the real Harlem Shake and was criticized by Harlem dancers for disconnecting the name from the actual Harlem dance."),
            ("Confidence", "High based on first-person and media sources."),
            ("Sources to Review", "Dance Enthusiast interview with Chrybaby Cozie, Wired, and AllHipHop."),
            ("Archive Note", "This record should preserve the difference between the real Harlem Shake and the internet meme."),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "LiteFeet and Subway Showtime Criminalization",
        "related_to": "LiteFeet, Showtime, subway dancing, criminalization, public space",
        "review_status": "Community Supported",
        "source_url": "https://i-d.co/article/documenting-new-yorks-recently-criminalised-subculture-of-subway-dancing/",
        "details": [
            ("Claim Text", "LiteFeet became strongly associated with subway Showtime performance culture, and public coverage in the mid-2010s connected subway dance policing to broken-windows enforcement, race, class, and public-space politics."),
            ("Confidence", "High based on documentary, journalism, and academic sources."),
            ("Sources to Review", "i-D/Vice, Viewing NYC, The Nation, Katie Beswick academic chapter, and Urban Democracy Lab."),
            ("Archive Note", "This record should collect community experiences and sources around performance, policing, arrests, safety debates, and public-space culture."),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "Get Lite to LiteFeet Music Evolution",
        "related_to": "Get Lite, LiteFeet music, 107 BPM, producers",
        "review_status": "Community Supported",
        "source_url": "https://www.vice.com/en/article/litefeet-hann-kid-the-wiz-m-live-new-york-subway-dancers-showtime-music/",
        "details": [
            ("Claim Text", "Public music coverage describes a shift around 2011 where a newer generation of dancers and producers refreshed Get Lite into LiteFeet music by raising tempo, adding layered sound, chants, samples, and call-and-response energy."),
            ("Confidence", "Supported by VICE/Noisey source, but specific producer timelines need community verification."),
            ("Sources to Review", "VICE/Noisey, Pond5 LiteFeet music brief, related music/video sources."),
            ("Archive Note", "Needs producers, tracks, DJs, tags, BPMs, and music lineage added as separate records."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Bad One / Badone",
        "related_to": "Bad One, Badone, LiteFeet move vocabulary",
        "review_status": "Pending Review",
        "source_url": "https://www.youtube.com/watch?v=rpmEoTVcmoo",
        "details": [
            ("Move / Style Name", "Bad One / Badone"),
            ("Move Origin / Context", "Bad One/Badone appears in LiteFeet tutorial titles, move lists, and music callouts, but public written sources do not clearly confirm the originator, first crew, first year, original spelling, or earliest known use."),
            ("Confidence", "Medium for the claim that Bad One/Badone is a recognized LiteFeet move. Low/unknown for origin details."),
            ("Needs Verification", "Originator, first known year, borough/crew/event, original spelling, whether Bad One and Badone are historically the same, and any older names or variations."),
            ("Archive Question", "Who taught you Bad One? What year did you first see it? What crew or borough did you connect it with? Was it called Bad One, Badone, Bad Bad One, or something else?"),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "Bad One / Badone Is a Recognized LiteFeet Move",
        "related_to": "Bad One, Badone, LiteFeet basics",
        "review_status": "Pending Review",
        "source_url": "https://www.youtube.com/watch?v=rpmEoTVcmoo",
        "details": [
            ("Claim Text", "Bad One/Badone is a recognized LiteFeet move used in Get Lite/LiteFeet vocabulary."),
            ("Confidence", "Medium. Supported by tutorial/video evidence, but still needs community confirmation and source expansion."),
            ("Sources to Review", "YouTube tutorials, YouTube Bad One playlists, and Pond5 Litefeet music brief."),
            ("Archive Note", "This should remain open for community verification until origin and lineage details are stronger."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Harlem Shake",
        "related_to": "Harlem Shake, LiteFeet roots",
        "review_status": "Community Supported",
        "source_url": "https://www.smithsonianmag.com/smart-news/presenting-the-real-harlem-shake-21838530/",
        "details": [
            ("Move / Style Name", "Harlem Shake"),
            ("Move Origin / Context", "Older Harlem dance commonly connected to Al B / Al Cisco / Albert Boyce, Rucker Park, and early-2000s music video exposure. It is part of the cultural lineage feeding LiteFeet."),
            ("Sources to Review", "Smithsonian, DNAinfo, IUDance, AllHipHop, and Vulture."),
            ("Archive Note", "Exact origin details and personal accounts should be community-reviewed."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Tone Wop / Tone Whop",
        "related_to": "Tone Wop, Tone Whop, LiteFeet movement vocabulary",
        "review_status": "Pending Review",
        "source_url": "https://www.steezy.co/posts/learn-about-lite-feet-the-newest-evolution-in-hip-hop-dance",
        "details": [
            ("Move / Style Name", "Tone Wop / Tone Whop"),
            ("Move Origin / Context", "Listed in public LiteFeet education sources as a foundational or popular LiteFeet move, often connected with Rev Up/Whop vocabulary."),
            ("Confidence", "Supported as a recognized term, but origin and lineage details need community verification."),
            ("Archive Note", "Needs first-person dancer context, video links, and history from people who learned or taught the move."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Rev Up / Whop",
        "related_to": "Rev Up, Whop, LiteFeet movement vocabulary",
        "review_status": "Pending Review",
        "source_url": "https://www.youtube.com/watch?v=CJvCzHksm54",
        "details": [
            ("Move / Style Name", "Rev Up / Whop"),
            ("Move Origin / Context", "Appears in LiteFeet tutorials and is often connected to Tone Wop vocabulary."),
            ("Confidence", "Supported by tutorial evidence; origin and historical context need community verification."),
            ("Archive Note", "Needs details on names, variations, who popularized it, and how dancers describe it."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Lock In",
        "related_to": "Lock In, LiteFeet routine punctuation",
        "review_status": "Pending Review",
        "source_url": "https://www.steezy.co/posts/learn-about-lite-feet-the-newest-evolution-in-hip-hop-dance",
        "details": [
            ("Move / Style Name", "Lock In"),
            ("Move Origin / Context", "Described by STEEZY as a move used like an exclamation point ending routines."),
            ("Confidence", "Supported by public dance-education source; origin and popularization need community verification."),
            ("Archive Note", "Needs examples, dancer explanations, and source links."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Shoe Tricks",
        "related_to": "LiteFeet performance vocabulary, Showtime",
        "review_status": "Community Supported",
        "source_url": "https://www.steezy.co/posts/learn-about-lite-feet-the-newest-evolution-in-hip-hop-dance",
        "details": [
            ("Move / Style Name", "Shoe Tricks"),
            ("Move Origin / Context", "Shoe tricks are part of the visual and performance vocabulary connected to LiteFeet, battles, cyphers, and Showtime-style performance."),
            ("Confidence", "Supported by public sources and visible performance practice."),
            ("Archive Note", "Specific tricks, originators, variations, and notable examples should be added separately."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Hat Tricks",
        "related_to": "LiteFeet performance vocabulary, Showtime",
        "review_status": "Community Supported",
        "source_url": "https://www.steezy.co/posts/learn-about-lite-feet-the-newest-evolution-in-hip-hop-dance",
        "details": [
            ("Move / Style Name", "Hat Tricks"),
            ("Move Origin / Context", "Hat tricks are part of the visual and performance vocabulary connected to LiteFeet, battles, cyphers, and Showtime-style performance."),
            ("Confidence", "Supported by public sources and visible performance practice."),
            ("Archive Note", "Specific tricks, originators, variations, and notable examples should be added separately."),
        ],
    },
    {
        "submission_type": "dancer_profile",
        "title": "Al B / Al Cisco / Albert Boyce",
        "related_to": "Real Harlem Shake, Rucker Park",
        "review_status": "Pending Review",
        "source_url": "https://www.smithsonianmag.com/smart-news/presenting-the-real-harlem-shake-21838530/",
        "details": [
            ("Dancer Name / Alias", "Al B / Al Cisco / Albert Boyce"),
            ("Known For", "Widely credited in public sources as central to the original Harlem Shake / Albee origin story connected to Rucker Park."),
            ("Confidence", "Supported by public sources, but exact origin details and family/community accounts should be reviewed carefully."),
            ("Archive Note", "Needs community context, source links, and careful distinction between documented sources and oral history."),
        ],
    },
    {
        "submission_type": "dancer_profile",
        "title": "Mr. YouTube",
        "related_to": "LiteFeet origins, LiteFeet education",
        "review_status": "Pending Review",
        "source_url": "https://www.steezy.co/posts/learn-about-lite-feet-the-newest-evolution-in-hip-hop-dance",
        "details": [
            ("Dancer Name / Alias", "Mr. YouTube"),
            ("Known For", "Identified by STEEZY as one of the original creators of Lite Feet and instructor of an Intro to Lite Feet program; also appears in Vulture's early LiteFeet history coverage."),
            ("Confidence", "Supported by public sources; deeper timeline and community details need verification."),
            ("Archive Note", "Needs source links, profile details, battle/event history, and community context."),
        ],
    },
    {
        "submission_type": "dancer_profile",
        "title": "Chrybaby Cozie / Daniel Holloway",
        "related_to": "LiteFeet pioneer, Harlem Lite Feet, preservation",
        "review_status": "Community Supported",
        "source_url": "https://www.dance-enthusiast.com/features/view/Lite-Feet-Chrybaby-Cozie/",
        "details": [
            ("Dancer Name / Alias", "Chrybaby Cozie / Daniel Holloway"),
            ("Known For", "Described in public sources as a Harlem Lite Feet pioneer/forefather, cultural educator, and organizer connected to Lite Feet Nation, The Breakfast Club E.A.T., Chrysolation, and preservation work."),
            ("Confidence", "High based on interview and institutional sources."),
            ("Archive Note", "Additional event, teaching, battle, and community history can be added over time."),
        ],
    },
    {
        "submission_type": "dancer_profile",
        "title": "Goofy / W.A.F.F.L.E.",
        "related_to": "W.A.F.F.L.E., Showtime, subway LiteFeet",
        "review_status": "Pending Review",
        "source_url": "https://www.vulture.com/2015/09/how-litefeet-moved-from-subway-to-mainstream.html",
        "details": [
            ("Dancer Name / Alias", "Goofy / W.A.F.F.L.E."),
            ("Known For", "Vulture describes Goofy, leader of W.A.F.F.L.E., as a major promoter who helped turn LiteFeet into subway It’s Showtime performance culture."),
            ("Confidence", "Supported by public source; profile details need community verification."),
            ("Archive Note", "Needs W.A.F.F.L.E. timeline, member context, battles, videos, and event links."),
        ],
    },
    {
        "submission_type": "dancer_profile",
        "title": "Kid The Wiz / Randy Vargas",
        "related_to": "LiteFeet music, production, dance",
        "review_status": "Pending Review",
        "source_url": "https://www.vice.com/en/article/litefeet-hann-kid-the-wiz-m-live-new-york-subway-dancers-showtime-music/",
        "details": [
            ("Dancer Name / Alias", "Kid The Wiz / Randy Vargas"),
            ("Known For", "VICE/Noisey describes Kid The Wiz as part of the LiteFeet producer/dancer ecosystem and credits him with helping push the energy of LiteFeet music."),
            ("Confidence", "Supported by public music source; deeper profile details need verification."),
            ("Archive Note", "Needs source links for music, battles, performances, productions, and community history."),
        ],
    },
]

```

## seed_litefeet_research.py

[Open original file](https://github.com/teethecreative/litefeet-archive/blob/main/seed_litefeet_research.py)

```python
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
                "related_to": record.get("related_to", ""),
                "source_url": record.get("source_url", ""),
                "submitter_name": "LiteFeet Ledger",
                "submitter_role": "Archive Research Seed",
                "contact": "",
                "needs_verification": 1,
                "review_status": record["review_status"],
                "details_json": clean_details(record["details"]),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )


RECORDS = [
    {
        "submission_type": "historical_claim",
        "title": "LiteFeet / Get Lite Emerged from Harlem and the Bronx",
        "related_to": "LiteFeet origins, Get Lite, Harlem, Bronx",
        "review_status": "Community Supported",
        "source_url": "https://daily.redbullmusicacademy.com/2013/05/new-york-stories-emma-warren/",
        "details": [
            ("Claim Text", "LiteFeet, also written Lite Feet and often described as getting lite, is a New York street dance culture connected to Harlem and the Bronx in the early-to-mid 2000s."),
            ("Confidence", "High based on multiple public sources, but still open to community context and correction."),
            ("Sources to Review", "Red Bull Music Academy Daily, Vulture, STEEZY, CBS/Paramount, academic writing on LiteFeet."),
            ("Archive Note", "Community members can add details about early dancers, crews, courts, parties, battles, and borough-specific history."),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "The Real Harlem Shake Predates LiteFeet",
        "related_to": "Harlem Shake, LiteFeet roots, Al B, Rucker Park",
        "review_status": "Community Supported",
        "source_url": "https://www.smithsonianmag.com/smart-news/presenting-the-real-harlem-shake-21838530/",
        "details": [
            ("Claim Text", "The real Harlem Shake predates LiteFeet and helped shape the movement vocabulary, feeling, and cultural lineage connected to LiteFeet."),
            ("Confidence", "High, but exact origin details vary by source and community memory."),
            ("Sources to Review", "Smithsonian, DNAinfo, IUDance, AllHipHop, Vulture."),
            ("Archive Note", "This claim should collect memories and sources around Al B / Al Cisco / Albert Boyce, Rucker Park, Go Crazy Boyz, music videos, and Harlem dance history."),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "The 2013 Harlem Shake Meme Is Not the Real Harlem Shake",
        "related_to": "Harlem Shake meme, real Harlem Shake, cultural confusion",
        "review_status": "Community Supported",
        "source_url": "https://www.dance-enthusiast.com/features/view/Lite-Feet-Chrybaby-Cozie/",
        "details": [
            ("Claim Text", "The 2013 viral Harlem Shake meme is not the real Harlem Shake and was criticized by Harlem dancers for disconnecting the name from the actual Harlem dance."),
            ("Confidence", "High based on first-person and media sources."),
            ("Sources to Review", "Dance Enthusiast interview with Chrybaby Cozie, Wired, AllHipHop."),
            ("Archive Note", "This record should preserve the difference between the real Harlem Shake and the internet meme."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Bad One / Badone",
        "related_to": "Bad One, Badone, LiteFeet move vocabulary",
        "review_status": "Needs Verification",
        "source_url": "https://www.youtube.com/watch?v=rpmEoTVcmoo",
        "details": [
            ("Move / Style Name", "Bad One / Badone"),
            ("Move Origin / Context", "Bad One/Badone appears in LiteFeet tutorial titles, move lists, and music callouts, but public written sources do not clearly confirm the originator, first crew, first year, original spelling, or earliest known use."),
            ("Confidence", "Medium for the claim that Bad One/Badone is a recognized LiteFeet move. Low/unknown for origin details."),
            ("Needs Verification", "Originator, first known year, borough/crew/event, original spelling, whether Bad One and Badone are historically the same, and any older names or variations."),
            ("Archive Question", "Who taught you Bad One? What year did you first see it? What crew or borough did you connect it with? Was it called Bad One, Badone, Bad Bad One, or something else?"),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "Bad One / Badone Is a Recognized LiteFeet Move",
        "related_to": "Bad One, Badone, LiteFeet basics",
        "review_status": "Needs Verification",
        "source_url": "https://www.youtube.com/watch?v=rpmEoTVcmoo",
        "details": [
            ("Claim Text", "Bad One/Badone is a recognized LiteFeet move used in Get Lite/LiteFeet vocabulary."),
            ("Confidence", "Medium. Supported by tutorial/video evidence, but still needs community confirmation and source expansion."),
            ("Sources to Review", "YouTube tutorials, YouTube Bad One playlists, Pond5 Litefeet music brief."),
            ("Archive Note", "This should remain open for community verification until origin and lineage details are stronger."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Harlem Shake",
        "related_to": "Harlem Shake, LiteFeet roots",
        "review_status": "Community Supported",
        "source_url": "https://www.smithsonianmag.com/smart-news/presenting-the-real-harlem-shake-21838530/",
        "details": [
            ("Move / Style Name", "Harlem Shake"),
            ("Move Origin / Context", "Older Harlem dance commonly connected to Al B / Al Cisco / Albert Boyce, Rucker Park, and early-2000s music video exposure. It is part of the cultural lineage feeding LiteFeet."),
            ("Sources to Review", "Smithsonian, DNAinfo, IUDance, AllHipHop, Vulture."),
            ("Archive Note", "Exact origin details and personal accounts should be community-reviewed."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Tone Wop / Tone Whop",
        "related_to": "Tone Wop, Tone Whop, LiteFeet movement vocabulary",
        "review_status": "Needs Verification",
        "source_url": "https://www.steezy.co/posts/learn-about-lite-feet-the-newest-evolution-in-hip-hop-dance",
        "details": [
            ("Move / Style Name", "Tone Wop / Tone Whop"),
            ("Move Origin / Context", "Listed in public LiteFeet education sources as a foundational or popular LiteFeet move, often connected with Rev Up/Whop vocabulary."),
            ("Confidence", "Supported as a recognized term, but origin and lineage details need community verification."),
            ("Archive Note", "Needs first-person dancer context, video links, and history from people who learned or taught the move."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Rev Up / Whop",
        "related_to": "Rev Up, Whop, LiteFeet movement vocabulary",
        "review_status": "Needs Verification",
        "source_url": "https://www.youtube.com/watch?v=CJvCzHksm54",
        "details": [
            ("Move / Style Name", "Rev Up / Whop"),
            ("Move Origin / Context", "Appears in LiteFeet tutorials and is often connected to Tone Wop vocabulary."),
            ("Confidence", "Supported by tutorial evidence; origin and historical context need community verification."),
            ("Archive Note", "Needs details on names, variations, who popularized it, and how dancers describe it."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Lock In",
        "related_to": "Lock In, LiteFeet routine punctuation",
        "review_status": "Needs Verification",
        "source_url": "https://www.steezy.co/posts/learn-about-lite-feet-the-newest-evolution-in-hip-hop-dance",
        "details": [
            ("Move / Style Name", "Lock In"),
            ("Move Origin / Context", "Described by STEEZY as a move used like an exclamation point ending routines."),
            ("Confidence", "Supported by public dance-education source; origin and popularization need community verification."),
            ("Archive Note", "Needs examples, dancer explanations, and source links."),
        ],
    },
    {
        "submission_type": "move_info",
        "title": "Shoe Tricks / Hat Tricks",
        "related_to": "LiteFeet performance vocabulary, Showtime",
        "review_status": "Community Supported",
        "source_url": "https://www.steezy.co/posts/learn-about-lite-feet-the-newest-evolution-in-hip-hop-dance",
        "details": [
            ("Move / Style Name", "Shoe tricks / hat tricks"),
            ("Move Origin / Context", "Core visual vocabulary in LiteFeet and Showtime-style performance, especially connected to battles, cyphers, and subway performances."),
            ("Confidence", "Supported by public sources and visible performance practice."),
            ("Archive Note", "Specific tricks, originators, variations, and notable examples should be added separately."),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "LiteFeet and Subway Showtime Criminalization",
        "related_to": "LiteFeet, Showtime, subway dancing, criminalization, public space",
        "review_status": "Community Supported",
        "source_url": "https://i-d.co/article/documenting-new-yorks-recently-criminalised-subculture-of-subway-dancing/",
        "details": [
            ("Claim Text", "LiteFeet became strongly associated with subway Showtime performance culture, and public coverage in the mid-2010s connected subway dance policing to broken-windows enforcement, race, class, and public-space politics."),
            ("Confidence", "High based on documentary, journalism, and academic sources."),
            ("Sources to Review", "i-D/Vice, Viewing NYC, The Nation, Katie Beswick academic chapter, Urban Democracy Lab."),
            ("Archive Note", "This record should collect community experiences and sources around performance, policing, arrests, safety debates, and public-space culture."),
        ],
    },
    {
        "submission_type": "dancer_profile",
        "title": "Al B / Al Cisco / Albert Boyce",
        "related_to": "Real Harlem Shake, Rucker Park",
        "review_status": "Needs Verification",
        "source_url": "https://www.smithsonianmag.com/smart-news/presenting-the-real-harlem-shake-21838530/",
        "details": [
            ("Dancer Name / Alias", "Al B / Al Cisco / Albert Boyce"),
            ("Known For", "Widely credited in public sources as central to the original Harlem Shake / Albee origin story connected to Rucker Park."),
            ("Confidence", "Supported by public sources, but exact origin details and family/community accounts should be reviewed carefully."),
            ("Archive Note", "Needs community context, source links, and careful distinction between documented sources and oral history."),
        ],
    },
    {
        "submission_type": "dancer_profile",
        "title": "Mr. YouTube",
        "related_to": "LiteFeet origins, LiteFeet education",
        "review_status": "Needs Verification",
        "source_url": "https://www.steezy.co/posts/learn-about-lite-feet-the-newest-evolution-in-hip-hop-dance",
        "details": [
            ("Dancer Name / Alias", "Mr. YouTube"),
            ("Known For", "Identified by STEEZY as one of the original creators of Lite Feet and instructor of an Intro to Lite Feet program; also appears in Vulture's early LiteFeet history coverage."),
            ("Confidence", "Supported by public sources; deeper timeline and community details need verification."),
            ("Archive Note", "Needs source links, profile details, battle/event history, and community context."),
        ],
    },
    {
        "submission_type": "dancer_profile",
        "title": "Chrybaby Cozie / Daniel Holloway",
        "related_to": "LiteFeet pioneer, Harlem Lite Feet, preservation",
        "review_status": "Community Supported",
        "source_url": "https://www.dance-enthusiast.com/features/view/Lite-Feet-Chrybaby-Cozie/",
        "details": [
            ("Dancer Name / Alias", "Chrybaby Cozie / Daniel Holloway"),
            ("Known For", "Described in public sources as a Harlem Lite Feet pioneer/forefather, cultural educator, and organizer connected to Lite Feet Nation, The Breakfast Club E.A.T., Chrysolation, and preservation work."),
            ("Confidence", "High based on interview and institutional sources."),
            ("Archive Note", "Additional event, teaching, battle, and community history can be added over time."),
        ],
    },
    {
        "submission_type": "dancer_profile",
        "title": "Goofy / W.A.F.F.L.E.",
        "related_to": "W.A.F.F.L.E., Showtime, subway LiteFeet",
        "review_status": "Needs Verification",
        "source_url": "https://www.vulture.com/2015/09/how-litefeet-moved-from-subway-to-mainstream.html",
        "details": [
            ("Dancer Name / Alias", "Goofy / W.A.F.F.L.E."),
            ("Known For", "Vulture describes Goofy, leader of W.A.F.F.L.E., as a major promoter who helped turn LiteFeet into subway It’s Showtime performance culture."),
            ("Confidence", "Supported by public source; profile details need community verification."),
            ("Archive Note", "Needs W.A.F.F.L.E. timeline, member context, battles, videos, and event links."),
        ],
    },
    {
        "submission_type": "dancer_profile",
        "title": "Kid The Wiz / Randy Vargas",
        "related_to": "LiteFeet music, production, dance",
        "review_status": "Needs Verification",
        "source_url": "https://www.vice.com/en/article/litefeet-hann-kid-the-wiz-m-live-new-york-subway-dancers-showtime-music/",
        "details": [
            ("Dancer Name / Alias", "Kid The Wiz / Randy Vargas"),
            ("Known For", "VICE/Noisey describes Kid The Wiz as part of the LiteFeet producer/dancer ecosystem and credits him with helping push the energy of LiteFeet music."),
            ("Confidence", "Supported by public music source; deeper profile details need verification."),
            ("Archive Note", "Needs source links for music, battles, performances, productions, and community history."),
        ],
    },
    {
        "submission_type": "historical_claim",
        "title": "Get Lite to LiteFeet Music Evolution",
        "related_to": "Get Lite, LiteFeet music, 107 BPM, producers",
        "review_status": "Community Supported",
        "source_url": "https://www.vice.com/en/article/litefeet-hann-kid-the-wiz-m-live-new-york-subway-dancers-showtime-music/",
        "details": [
            ("Claim Text", "Public music coverage describes a shift around 2011 where a newer generation of dancers and producers refreshed Get Lite into LiteFeet music by raising tempo, adding layered sound, chants, samples, and call-and-response energy."),
            ("Confidence", "Supported by VICE/Noisey source, but specific producer timelines need community verification."),
            ("Sources to Review", "VICE/Noisey, Pond5 LiteFeet music brief, related music/video sources."),
            ("Archive Note", "Needs producers, tracks, DJs, tags, BPMs, and music lineage added as separate records."),
        ],
    },
    {
        "submission_type": "source_link",
        "title": "Red Bull — Litefeet: New York's New Dance Step",
        "related_to": "LiteFeet history source",
        "review_status": "Community Supported",
        "source_url": "https://daily.redbullmusicacademy.com/2013/05/new-york-stories-emma-warren/",
        "details": [
            ("Source Title", "Litefeet: New York's New Dance Step"),
            ("Source Platform", "Red Bull Music Academy Daily"),
            ("Source Context", "Strong general LiteFeet history source connecting LiteFeet to Harlem/Bronx, mid-2000s, Harlem Shake, Chicken Noodle Soup, and popping."),
        ],
    },
    {
        "submission_type": "source_link",
        "title": "Vulture — The Rise of Litefeet",
        "related_to": "LiteFeet history source",
        "review_status": "Community Supported",
        "source_url": "https://www.vulture.com/2015/09/how-litefeet-moved-from-subway-to-mainstream.html",
        "details": [
            ("Source Title", "The Rise of Litefeet: How the Dance Genre Moved From Subway to Mainstream"),
            ("Source Platform", "Vulture"),
            ("Source Context", "Narrative source for Mr. YouTube, Chrybaby Cozie, Goofy, W.A.F.F.L.E., subway Showtime, and mainstream crossover."),
        ],
    },
    {
        "submission_type": "source_link",
        "title": "VICE/Noisey — Sound of the Underground",
        "related_to": "LiteFeet music source",
        "review_status": "Community Supported",
        "source_url": "https://www.vice.com/en/article/litefeet-hann-kid-the-wiz-m-live-new-york-subway-dancers-showtime-music/",
        "details": [
            ("Source Title", "Sound of the Underground: How New York's Litefeet Producers Are Making Sure It’s Showtime in the City"),
            ("Source Platform", "VICE / Noisey"),
            ("Source Context", "Important music-production source on tempo, chants, dancers, producers, and how Get Lite became LiteFeet music."),
        ],
    },
    {
        "submission_type": "source_link",
        "title": "STEEZY — Learn About Lite Feet",
        "related_to": "LiteFeet education source",
        "review_status": "Community Supported",
        "source_url": "https://www.steezy.co/posts/learn-about-lite-feet-the-newest-evolution-in-hip-hop-dance",
        "details": [
            ("Source Title", "Learn About Lite Feet – The Newest Evolution in Hip Hop Dance"),
            ("Source Platform", "STEEZY"),
            ("Source Context", "Modern educational source explaining Get Lite, weightless footwork, battles, cyphers, tricks, Mr. YouTube, and learning culture/history/music together."),
        ],
    },
]


def main():
    init_db()

    created = 0
    skipped = 0

    for record in RECORDS:
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

```

## seed_archive.py

[Open original file](https://github.com/teethecreative/litefeet-archive/blob/main/seed_archive.py)

```python
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
        "submitter_name": "LiteFeet Ledger",
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
        "submitter_name": "LiteFeet Ledger",
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
        "submitter_name": "LiteFeet Ledger",
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
        "submitter_name": "LiteFeet Ledger",
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
        "submitter_name": "LiteFeet Ledger",
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
        "submitter_name": "LiteFeet Ledger",
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
        "submitter_name": "LiteFeet Ledger",
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
        "submitter_name": "LiteFeet Ledger",
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
        "submitter_name": "LiteFeet Ledger",
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
        "submitter_name": "LiteFeet Ledger",
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

```

## ghost_dancer_seed_data.py

[Open original file](https://github.com/teethecreative/litefeet-archive/blob/main/ghost_dancer_seed_data.py)

```python
GHOST_DANCER_PROFILES = [
    {"dance_name": "Wes the MAB", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "UnkDes", "aliases": "", "source_note": "Mentioned as a form respondent / dancer card interest."},
    {"dance_name": "Greklite", "aliases": "", "source_note": "Mentioned as a form respondent / dancer card interest."},
    {"dance_name": "DC", "aliases": "", "source_note": "Mentioned as a form respondent / dancer card interest and battle record."},
    {"dance_name": "Haz Money", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "E Solo", "aliases": "", "source_note": "Mentioned as a form respondent and battle record."},
    {"dance_name": "SHOWDEM", "aliases": "Slim-Goodies", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Bre Dash", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Paul Gee", "aliases": "", "source_note": "Mentioned as a form respondent / music contributor."},
    {"dance_name": "Visionsz", "aliases": "", "source_note": "Mentioned as Flex dance name in form response."},
    {"dance_name": "BSNYEA", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "PRockz", "aliases": "P Rockz", "source_note": "Mentioned as a form respondent and battle record."},
    {"dance_name": "BOLITE", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Sah", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Future", "aliases": "", "source_note": "Mentioned as a form respondent and battle record."},
    {"dance_name": "Strike Litening", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Note", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "ICEMAN", "aliases": "", "source_note": "Mentioned as a form respondent / dancer card interest."},
    {"dance_name": "Koopa", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Ty Shotz", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Nhim Lite", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Hype Baby", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Smoove Biz", "aliases": "Chubz", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Na Na", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Seed", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "SammyC", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Kid Smoove", "aliases": "K Smoove", "source_note": "Mentioned as a form respondent, featured dancer suggestion, and battle record."},
    {"dance_name": "Fox Lite", "aliases": "", "source_note": "Mentioned as a form respondent and battle record."},
    {"dance_name": "Venom", "aliases": "", "source_note": "Mentioned as a form respondent and battle record."},
    {"dance_name": "Ray-Dot", "aliases": "", "source_note": "Mentioned as a form respondent."},
    {"dance_name": "Phresh Tune", "aliases": "", "source_note": "Mentioned as a form respondent / music contributor."},
    {"dance_name": "Ginger Spice", "aliases": "", "source_note": "Mentioned as a form respondent and battle record."},
    {"dance_name": "K Cosmic", "aliases": "", "source_note": "Mentioned as a form respondent and battle record."},

    {"dance_name": "Giz Da Wiz", "aliases": "Giz the Wiz, Gizmo", "source_note": "Mentioned in battle records."},
    {"dance_name": "Tweek Baby", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Dot Lite", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Tokyo", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Man From Da Video", "aliases": "Man From The Video", "source_note": "Mentioned in battle records."},
    {"dance_name": "Mr YouTube", "aliases": "Mr. YouTube", "source_note": "Mentioned in battle records and LiteFeet history responses."},
    {"dance_name": "Hype Star", "aliases": "Hypestar", "source_note": "Mentioned in battle records."},
    {"dance_name": "Teeth", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Ky Butta", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Jay Wavvy", "aliases": "Jay Wavy", "source_note": "Mentioned in battle records."},
    {"dance_name": "Noah Lot", "aliases": "", "source_note": "Mentioned in battle records and music responses."},
    {"dance_name": "J Black", "aliases": "Jay Black", "source_note": "Mentioned in battle records."},
    {"dance_name": "Larry Smoove", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "40 Pounds", "aliases": "40 Poundz", "source_note": "Mentioned in battle records."},
    {"dance_name": "K Smoove", "aliases": "Kid Smoove", "source_note": "Mentioned in battle records."},
    {"dance_name": "DuckSauce", "aliases": "Duck Sauce", "source_note": "Mentioned in battle records."},
    {"dance_name": "O Wizard", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Matt Live", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember and battle record."},
    {"dance_name": "Jada Chanel", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Money Mase", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Dope", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Sha Money X", "aliases": "", "source_note": "Mentioned as a connected dancer."},
    {"dance_name": "Slim Baby", "aliases": "", "source_note": "Mentioned as a connected dancer."},
    {"dance_name": "Vick Live", "aliases": "", "source_note": "Mentioned as a connected dancer."},
    {"dance_name": "D Lite", "aliases": "", "source_note": "Mentioned in battle records and dancer suggestions."},
    {"dance_name": "Kid The Wiz", "aliases": "KidTheWiz", "source_note": "Mentioned in battle records and history/music responses."},
    {"dance_name": "T Rex", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Buzz Lite", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Rell Smoove", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Supa Nova", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Robbie Rob", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Tah Swag", "aliases": "", "source_note": "Mentioned in music/battle responses."},
    {"dance_name": "Sparkz Rah", "aliases": "", "source_note": "Mentioned in music responses."},
    {"dance_name": "Uncle Gz", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "B Lyve", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "SNS", "aliases": "Sns", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Lady Live", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Tee The Creative", "aliases": "TEE THE CREATIVE", "source_note": "Mentioned as a dancer/community figure to feature/remember."},
    {"dance_name": "Ash Rocket", "aliases": "ASH ROCKET", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Xo Wavy", "aliases": "", "source_note": "Mentioned as a dancer to feature/remember."},
    {"dance_name": "Sky Boogz", "aliases": "", "source_note": "Mentioned in arena/battle responses."},
    {"dance_name": "Spank", "aliases": "", "source_note": "Mentioned in arena responses."},
    {"dance_name": "Spider Jackson", "aliases": "", "source_note": "Mentioned in dancer card battle/moment response."},
    {"dance_name": "Young Pop", "aliases": "", "source_note": "Mentioned in battle/moment responses."},
    {"dance_name": "X Live", "aliases": "", "source_note": "Mentioned in battle/moment responses."},
    {"dance_name": "Flii Boogie", "aliases": "Fli Boogie, Flii boogie", "source_note": "Mentioned in battle records."},
    {"dance_name": "Moe Black", "aliases": "", "source_note": "Mentioned in battle/moment responses."},
    {"dance_name": "Mr Jones", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Jo Smooth", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Trell Mix", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Mel Butta", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Nae Davis", "aliases": "Nay Davis", "source_note": "Mentioned in battle records."},
    {"dance_name": "Supreme", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Jay Bullet", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "K Shakes", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Tee Slims", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "So Q", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Top Star", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Tugz", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Zebb Live", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Kid Patt", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Chrybaby", "aliases": "Chrybaby Cozie, Daniel Holloway", "source_note": "Mentioned in battle records and LiteFeet history responses."},
    {"dance_name": "Sylencer", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Crazy C", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "40 Kal", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Mel Live", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Moon Live", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "2 Eazy", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Melly Mellz", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Richie Rich", "aliases": "", "source_note": "Mentioned in battle records."},
    {"dance_name": "Trebuckz", "aliases": "", "source_note": "Mentioned in battle/moment responses."},
    {"dance_name": "Rich Dollaz", "aliases": "", "source_note": "Mentioned in battle/moment responses."},
    {"dance_name": "Kid Mix", "aliases": "", "source_note": "Mentioned as a clash/counter dancer."},
    {"dance_name": "Top Villian", "aliases": "Top Villain", "source_note": "Mentioned as a clash/counter dancer."},
    {"dance_name": "Smoove Eazy", "aliases": "", "source_note": "Mentioned as a clash/counter dancer."},
    {"dance_name": "Top Fliqht", "aliases": "Top Flight", "source_note": "Mentioned as a clash/counter dancer."},
    {"dance_name": "Kid Fox", "aliases": "", "source_note": "Mentioned as a clash/counter dancer."},
    {"dance_name": "Splash Ocean", "aliases": "", "source_note": "Mentioned as a clash/counter dancer."}
]

```

## seed_beats_bodies_people.py

[Open original file](https://github.com/teethecreative/litefeet-archive/blob/main/seed_beats_bodies_people.py)

```python
from datetime import datetime

from app import engine, init_db, ensure_person_role_columns, unique_profile_slug
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
                "profile_slug": unique_profile_slug(person["dance_name"]),
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

```

## seed_bodybag_events.py

[Open original file](https://github.com/teethecreative/litefeet-archive/blob/main/seed_bodybag_events.py)

```python
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

```

## data/imports/dancers_choice_august_2023_official_results.json

[Open original file](https://github.com/teethecreative/litefeet-archive/blob/main/data/imports/dancers_choice_august_2023_official_results.json)

```json
[
  {"page": 1, "category": "Best Trickster", "winner": "Kid Smoove", "affiliation": "Bombsquad", "location": "Harlem, New York"},
  {"page": 2, "category": "Best Hat Tricker", "winner": "Kid Smoove", "affiliation": "Bombsquad", "location": "Harlem, New York"},
  {"page": 3, "category": "Best Shoe Tricker", "winner": "D Astro", "affiliation": "2RealBoys + WAFFLE", "location": "The Bronx, New York"},
  {"page": 4, "category": "Best Footwork", "winner": "Kid Smoove", "affiliation": "Bombsquad", "location": "Harlem, New York"},
  {"page": 5, "category": "Best Battle Moment", "winner": "Noahlot - Red Bull", "affiliation": "Bombsquad", "location": "Harlem, New York"},
  {"page": 6, "category": "Best Tag Team", "winner": "Tati B & Tah Swag", "affiliation": "", "location": ""},
  {"page": 7, "category": "Best Collab", "winner": "Tati B & Tah Swag", "affiliation": "", "location": ""},
  {"page": 8, "category": "Best Entertainer", "winner": "Tah Swag", "affiliation": "Bombsquad", "location": "Harlem, New York"},
  {"page": 9, "category": "Best Ankle Bender", "winner": "Iron Man", "affiliation": "Live Zombies", "location": "The Bronx, New York"},
  {"page": 10, "category": "Life of the Party", "winner": "K Shakes", "affiliation": "Team Rocket", "location": "Brooklyn, New York"},
  {"page": 11, "category": "Best “Lite” Feet Energy", "winner": "Jada Chanel", "affiliation": "2Crafty", "location": "New York"},
  {"page": 12, "category": "Best Team Video", "winner": "Bombsquad", "affiliation": "", "location": "Harlem, New York", "result_status": "official_co_winner"},
  {"page": 13, "category": "Best Team Video", "winner": "2Crafty", "affiliation": "", "location": "New York", "result_status": "official_co_winner"},
  {"page": 14, "category": "Most Passionate", "winner": "Jada Chanel", "affiliation": "2Crafty", "location": "New York"},
  {"page": 15, "category": "Most Versatile", "winner": "Noahlot", "affiliation": "Bombsquad", "location": "Harlem, New York"},
  {"page": 16, "category": "Most Involved", "winner": "E Solo", "affiliation": "Team Rocket", "location": "Brooklyn, New York"},
  {"page": 17, "category": "Most Fearless", "winner": "Wild N Out", "affiliation": "2 Crafty", "location": "New York"},
  {"page": 18, "category": "Most Improved", "winner": "Jizzi Jazz", "affiliation": "Bombsquad", "location": "Harlem, New York"},
  {"page": 19, "category": "Most Improved Producer", "winner": "LadyMoSoFou", "affiliation": "LyveTyme", "location": "New York"},
  {"page": 20, "category": "Most Consistent Producer", "winner": "BsnYea", "affiliation": "", "location": ""},
  {"page": 21, "category": "Most Consistent Dancer", "winner": "Kid Smoove", "affiliation": "Bombsquad", "location": "Harlem, New York"},
  {"page": 22, "category": "Battle Song of the Year", "winner": "Tek 9 - LadyMoSoFou", "affiliation": "", "location": ""},
  {"page": 23, "category": "Content Song of the Year", "winner": "Tek 9 - LadyMoSoFou", "affiliation": "", "location": ""},
  {"page": 24, "category": "Best Content Creator", "winner": "Lucky Banks", "affiliation": "Breakfast Club", "location": ""},
  {"page": 25, "category": "Best Combo Dancer", "winner": "Fox Lite", "affiliation": "Live Zombies", "location": "Harlem, New York"},
  {"page": 26, "category": "Best Balance", "winner": "D Astro", "affiliation": "2RealBoys + WAFFLE", "location": "The Bronx, New York"},
  {"page": 27, "category": "Best Musicality", "winner": "K Shakes", "affiliation": "Team Rocket", "location": "Brooklyn, New York"},
  {"page": 28, "category": "Best Out of State Dancer", "winner": "Jay Bull", "affiliation": "LyveTyme", "location": "United Kingdom"},
  {"page": 29, "category": "Best Event 2023", "winner": "Litefeet Awards Weekend", "affiliation": "", "location": ""},
  {"page": 30, "category": "Best Big Man", "winner": "Sound Cloud", "affiliation": "2LiveKrew", "location": "New York"},
  {"page": 31, "category": "Best Junior Dancer", "winner": "Tah Swag", "affiliation": "Bombsquad", "location": "Harlem, New York"},
  {"page": 32, "category": "Youngest in Charge", "winner": "Tah Swag", "affiliation": "Bombsquad", "location": "Harlem, New York"}
]

```

## data/imports/dancers_choice_august_2023_all_nominee_fixed_votes.csv

[Open original file](https://github.com/teethecreative/litefeet-archive/blob/main/data/imports/dancers_choice_august_2023_all_nominee_fixed_votes.csv)

```csv
Award Show,Category,Rank,Nominee,Original Vote Option,Fixed Public Votes,Official Result,PDF Page,Public Status,Total Public Votes In Category,Total Counted Responses,Notes
Dancer’s Choice Awards — August 2023,Best Trickster,1,Kid Smoove,Kid Smoove,44,official_winner,1,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Trickster,2,Richie Rich,Richie Rich,30,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Trickster,3,Larry Smoove,Larry Smoove,25,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Trickster,4,FLii BOOGiiE,FLii BOOGiiE,24,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Trickster,5,D Astro,D Astro,9,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Hat Tricker,1,Kid Smoove,Kid Smoove,44,official_winner,2,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Hat Tricker,2,40 Pounds,40 Pounds,35,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Hat Tricker,3,Kid The Wiz,Kid The Wiz,27,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Hat Tricker,4,Larry Smoove,Larry Smoove,20,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Hat Tricker,5,Kid Star,Kid Star,7,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Shoe Tricker,1,D Astro,D Astro,30,official_winner,3,official_pdf_category,133,133,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Best Shoe Tricker,2,E Solo,E Solo,29,nominee,,official_pdf_category,133,133,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Best Shoe Tricker,2,Kid Smoove,Kid Smoove,29,nominee,,official_pdf_category,133,133,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Best Shoe Tricker,4,Matt Live,Matt Live,25,nominee,,official_pdf_category,133,133,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Best Shoe Tricker,5,Richie Rich,Richie Rich,20,nominee,,official_pdf_category,133,133,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Best Footwork,1,Kid Smoove,Kid Smoove,45,official_winner,4,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Footwork,2,K Slic,K Slic,34,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Footwork,3,40 Pounds,40 Pounds,32,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Footwork,4,D Rillz,D Rillz,10,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Footwork,5,Radar,Radar,9,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Footwork,6,Mok Lite,Mok lite,1,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Footwork,6,Noahlot,Noahlot,1,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Battle Moment,1,Noahlot - Red Bull,Noahlot (Red Bull),70,official_winner,5,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Battle Moment,2,Kid Smoove vs 40 Pounds,Kid Smoove vs 40 Pounds,26,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Battle Moment,3,Larry Smoove vs 40 Pounds,Larry Smoove vs 40 Pounds,20,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Battle Moment,4,SoundCloud vs Fire Flamez,SoundCloud vs Fire Flamez,12,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Battle Moment,5,Crazy C Shoulder,Crazy C Shoulder,5,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Tag Team,1,Tati B & Tah Swag,Tah Swag & Tati B,58,official_winner,6,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Tag Team,2,Noahlot & Kid Smoove,Noahlot & Kid Smoove,42,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Tag Team,3,40 Pounds & K Smoove,40 Pounds & K Smoove,17,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Tag Team,4,2Crafty,2 Crafty,10,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Tag Team,5,FLii Robot,FLii Robot,5,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Best Collab,1,Tati B & Tah Swag,Tah Swag & Tati B,65,official_winner,7,official_pdf_category,130,131,
Dancer’s Choice Awards — August 2023,Best Collab,2,Noahlot & Kid Smoove,Noahlot & Kid Smoove,31,nominee,,official_pdf_category,130,131,
Dancer’s Choice Awards — August 2023,Best Collab,3,Artefakt 2023 Lf Cypher,ARTEFAKT 2023 LF CYPHER,18,nominee,,official_pdf_category,130,131,
Dancer’s Choice Awards — August 2023,Best Collab,4,Jay Wavy & Red Ink,Jay Wavy & Red Ink,8,nominee,,official_pdf_category,130,131,
Dancer’s Choice Awards — August 2023,Best Collab,4,Lucky Banks & K Shakes,Lucky Banks & K Shakes,8,nominee,,official_pdf_category,130,131,
Dancer’s Choice Awards — August 2023,Best Entertainer,1,Tah Swag,Tah Swag,63,official_winner,8,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Entertainer,2,K Shakes,K Shakes,33,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Entertainer,3,Crazy C,Crazy C,14,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Entertainer,4,E Solo,E Solo,13,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Entertainer,5,Mr Jones,Mr Jones,9,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Entertainer,6,Lucky luck,Lucky luck,1,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Ankle Bender,1,Iron Man,Iron Man,46,official_winner,9,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Ankle Bender,2,E Solo,E Solo,32,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Ankle Bender,3,Kid Smoove,Kid Smoove,26,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Ankle Bender,4,K Smoove,K Smoove,15,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Ankle Bender,5,D Rillz,D Rillz,13,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Life of the Party,1,K Shakes,K Shakes,64,official_winner,10,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Life of the Party,2,Noahlot,Noahlot,39,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Life of the Party,3,Jay Wavy,JAY WAVY,21,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Life of the Party,4,Bbq,BBQ,5,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Life of the Party,5,Mr Jones,MR JONES,4,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best “Lite” Feet Energy,1,Jada Chanel,Jada Chanel,48,official_winner,11,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best “Lite” Feet Energy,2,Noahlot,Noahlot,42,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best “Lite” Feet Energy,3,Jay Wavy,Jay Wavy,21,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best “Lite” Feet Energy,4,Moe Black,Moe Black,16,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best “Lite” Feet Energy,5,Mr Jones,Mr Jones,5,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Team Video,1,2Crafty,2 Crafty,49,official_co_winner,13,official_pdf_category,131,131,Official PDF co-winner.
Dancer’s Choice Awards — August 2023,Best Team Video,1,Bombsquad,Bombsquad,49,official_co_winner,12,official_pdf_category,131,131,Official PDF co-winner.
Dancer’s Choice Awards — August 2023,Best Team Video,3,God Of Shoe Tricks,God Of Shoe Tricks,16,nominee,,official_pdf_category,131,131,
Dancer’s Choice Awards — August 2023,Best Team Video,4,Lyve Rockets,LYVE ROCKETS,10,nominee,,official_pdf_category,131,131,
Dancer’s Choice Awards — August 2023,Best Team Video,5,Lyvetyme,Lyvetyme,7,nominee,,official_pdf_category,131,131,
Dancer’s Choice Awards — August 2023,Most Passionate,1,Jada Chanel,Jada Chanel,48,official_winner,14,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Most Passionate,2,Kid Smoove,Kid Smoove,37,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Most Passionate,3,E Solo,E Solo,26,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Most Passionate,4,Noahlot,Noahlot,18,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Most Passionate,5,Mr Jones,Mr Jones,3,nominee,,official_pdf_category,132,133,
Dancer’s Choice Awards — August 2023,Most Versatile,1,Noahlot,Noahlot,75,official_winner,15,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Versatile,2,E Solo,E Solo,19,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Versatile,3,FLii BOOGiiE,FLii BOOGiiE,13,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Versatile,4,Kid Smoove,Kid Smoove,12,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Versatile,5,Jay Wavy,Jay Wavy,11,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Versatile,6,SoundCloud,SoundCloud,2,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Involved,1,E Solo,E Solo,45,official_winner,16,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Most Involved,2,Bombsquad,Bombsquad,38,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Most Involved,3,Chrybaby,Chrybaby,26,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Most Involved,4,Tee / Litefeet ESPN,Tee / Litefeet ESPN,21,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Most Involved,5,Kid Smoove,Kid Smoove,3,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Most Fearless,1,Wild N Out,Wild N Out,47,official_winner,17,official_pdf_category,131,131,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Most Fearless,2,Kid Smoove,Kid Smoove,46,nominee,,official_pdf_category,131,131,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Most Fearless,3,Larry Smoove,Larry Smoove,16,nominee,,official_pdf_category,131,131,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Most Fearless,4,Mok Lite,Mok Lite,15,nominee,,official_pdf_category,131,131,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Most Fearless,5,Billie Bucks,Billie Bucks,7,nominee,,official_pdf_category,131,131,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Most Improved,1,Jizzi Jazz,Jizzi Jazz,48,official_winner,18,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Improved,2,Unolot,Unolot,27,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Improved,3,Tre Bucks,Tre Bucks,26,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Improved,4,Red Ink,Red Ink,20,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Improved,5,Baby Sparkz,BABY SPARKZ,11,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Improved Producer,1,LadyMoSoFou,LADYMOSOFOU,94,official_winner,19,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Improved Producer,2,BigWav3,BIGWAV3,15,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Improved Producer,3,AyeJaeBeats,AYEJAEBEATS,11,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Improved Producer,4,KennDot,KENNDOT,7,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Improved Producer,5,Phresh Tune,PHRESH TUNE,5,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Most Consistent Producer,1,BsnYea,BSNYEA,49,official_winner,20,official_pdf_category,134,134,
Dancer’s Choice Awards — August 2023,Most Consistent Producer,2,LadyMoSoFou,LADYMOSOFOU,47,nominee,,official_pdf_category,134,134,
Dancer’s Choice Awards — August 2023,Most Consistent Producer,3,BigWav3,BIGWAV3,15,nominee,,official_pdf_category,134,134,
Dancer’s Choice Awards — August 2023,Most Consistent Producer,3,Jay Black,JAY BLACK,15,nominee,,official_pdf_category,134,134,
Dancer’s Choice Awards — August 2023,Most Consistent Producer,5,Speightsrawkid (Buckwheat),SPEIGHTSRAWKID (BUCKWHEAT),8,nominee,,official_pdf_category,134,134,
Dancer’s Choice Awards — August 2023,Most Consistent Dancer,1,Kid Smoove,Kid Smoove,49,official_winner,21,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Most Consistent Dancer,2,Jada Chanel,Jada Chanel,40,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Most Consistent Dancer,3,E Solo,E Solo,21,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Most Consistent Dancer,4,Noahlot,Noahlot,18,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Most Consistent Dancer,5,Jay Wavy,Jay Wavy,5,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Battle Song of the Year,1,Tek 9 - LadyMoSoFou,TEK 9 - LADYMOSOFOU,69,official_winner,22,official_pdf_category,131,131,
Dancer’s Choice Awards — August 2023,Battle Song of the Year,2,So Disrespectful - LadyMoSoFou,SO DISRESPECTFUL - LADYMOSOFOU,34,nominee,,official_pdf_category,131,131,
Dancer’s Choice Awards — August 2023,Battle Song of the Year,3,Damson - PhreshTune,DAMSON - PHRESHTUNE,13,nominee,,official_pdf_category,131,131,
Dancer’s Choice Awards — August 2023,Battle Song of the Year,4,Sheesh Bo - SpeightsRawKid,SHEESH BO - SPEIGHTSRAWKID,8,nominee,,official_pdf_category,131,131,
Dancer’s Choice Awards — August 2023,Battle Song of the Year,5,GG - KennDot,GG - KENNDOT,7,nominee,,official_pdf_category,131,131,
Dancer’s Choice Awards — August 2023,Content Song of the Year,1,Tek 9 - LadyMoSoFou,TEK 9 - LADYMOSOFOU,61,official_winner,23,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Content Song of the Year,2,So Disrespectful - LadyMoSoFou,SO DISRESPECTFUL - LADYMOSOFOU,47,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Content Song of the Year,3,Powerstep - LadyMoSoFou,POWERSTEP - LADYMOSOFOU,12,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Content Song of the Year,4,Damson - PhreshTune,DAMSON - PHRESHTUNE,7,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Content Song of the Year,5,Mafioso - BigWav3,MAFIOSO - BIGWAV3,5,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Content Creator,1,Lucky Banks,LUCKY BANKS (@LUCKYBANKS),56,official_winner,24,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Content Creator,2,Kid The Wiz,KID THE WIZ (@KIDTHEWIZ),37,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Content Creator,3,Mr. YouTube,MR. YOUTUBE (@MRYOUTUBE),21,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Content Creator,4,Aero Ace,AERO ACE (@WAFFLEKOZIK),13,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Content Creator,5,Boy Smoove,BOY SMOOVE (@FEETWORKWITHARIES),5,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Content Creator,6,Esolo,Esolo,1,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Combo Dancer,1,Fox Lite,FOX LITE,39,official_winner,25,official_pdf_category,133,133,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Best Combo Dancer,2,Noahlot,NOAHLOT,37,nominee,,official_pdf_category,133,133,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Best Combo Dancer,3,Kid Smoove,KID SMOOVE,34,nominee,,official_pdf_category,133,133,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Best Combo Dancer,4,Moe Black,MOE BLACK,14,nominee,,official_pdf_category,133,133,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Best Combo Dancer,5,Ty Blaze,TY BLAZE,9,nominee,,official_pdf_category,133,133,Fixed public count adjusted to match PDF winner.
Dancer’s Choice Awards — August 2023,Best Balance,1,D Astro,D Astro,38,official_winner,26,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Balance,2,Kid Smoove,Kid Smoove,33,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Balance,3,K Shakes,K Shakes,31,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Balance,4,FLii BOOGiiE,Flii Boogiie,21,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Balance,5,Mok Lite,Mok Lite,9,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Musicality,1,K Shakes,K SHAKES,50,official_winner,27,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Musicality,2,Kid Smoove,KID SMOOVE,44,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Musicality,3,Noahlot,NOAHLOT,37,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Musicality,4,Sound Cloud,SOUNDCLOUD,2,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Out of State Dancer,1,Jay Bull,JAY BULL,71,official_winner,28,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Out of State Dancer,2,Red Ink,RED INK,59,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Out of State Dancer,3,8 Legx,8 Legx,1,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Out of State Dancer,3,D Phantom,D PHANTOM,1,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Out of State Dancer,3,Speedforce,Speedforce,1,nominee,,official_pdf_category,133,133,
Dancer’s Choice Awards — August 2023,Best Event 2023,1,Litefeet Awards Weekend,LITEFEET AWARDS,88,official_winner,29,official_pdf_category,130,130,
Dancer’s Choice Awards — August 2023,Best Event 2023,2,Body Bag 2,BODY BAG 2,21,nominee,,official_pdf_category,130,130,
Dancer’s Choice Awards — August 2023,Best Event 2023,3,LiteFeet Day 3,LITEFEET DAY 3,15,nominee,,official_pdf_category,130,130,
Dancer’s Choice Awards — August 2023,Best Event 2023,4,DEFCON,DEFCON,6,nominee,,official_pdf_category,130,130,
Dancer’s Choice Awards — August 2023,Best Big Man,1,Sound Cloud,SOUNDCLOUD,76,official_winner,30,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Big Man,2,Crazy C,CRAZY C,50,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Big Man,3,A Wright,A WRIGHT,6,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Junior Dancer,1,Tah Swag,TAH SWAG,85,official_winner,31,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Junior Dancer,2,Taylah Gang,TAYLAH GANG,32,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Best Junior Dancer,3,Oh Baby,OH BABY,15,nominee,,official_pdf_category,132,132,
Dancer’s Choice Awards — August 2023,Youngest in Charge,1,Tah Swag,TAH SWAG,92,official_winner,32,official_pdf_category,131,131,
Dancer’s Choice Awards — August 2023,Youngest in Charge,2,Taylah Gang,TAYLAH GANG,23,nominee,,official_pdf_category,131,131,
Dancer’s Choice Awards — August 2023,Youngest in Charge,3,XO Wavy,XO WAVY,16,nominee,,official_pdf_category,131,131,

```

## data/homepage_prompt_questions.txt

[Open original file](https://github.com/teethecreative/litefeet-archive/blob/main/data/homepage_prompt_questions.txt)

```text
What is LiteFeet?
Where did LiteFeet come from?
Why is it called LiteFeet?
What makes LiteFeet different from other dance styles?
What are the basic LiteFeet moves?
What is a Tone Whop?
What is Chicken Noodle Soup?
What is a Lock In?
What is a Rev Up?
What does “getting lite” mean?
How do you know when someone is really getting lite?
Who helped create LiteFeet?
What borough did LiteFeet come from?
What role did Harlem play in LiteFeet?
What role did the Bronx play in LiteFeet?
What role did Queens play in LiteFeet?
What role did Staten Island play in LiteFeet?
What role did New Jersey play in LiteFeet?
What role did Upstate New York play in LiteFeet?
What role did Connecticut play in LiteFeet?
How did LiteFeet spread through New York?
How did YouTube help LiteFeet grow?
What were the early LiteFeet teams?
What battles helped shape LiteFeet?
What events were important in LiteFeet history?
How did train dancing connect to LiteFeet?
Why was LiteFeet so visible in subway culture?
How did LiteFeet change from the 2000s to now?
What LiteFeet moments should every new dancer know?
What is one forgotten moment in LiteFeet history?
What does LiteFeet mean to New York culture?
Who are some LiteFeet legends?
Who are the most influential LiteFeet dancers?
Who are the best LiteFeet battlers?
Who are the best LiteFeet performers?
Who are the best LiteFeet teachers?
Who helped push LiteFeet outside of New York?
What LiteFeet teams should people know?
What dancer changed the way people battle?
What dancer changed the way people perform?
Who deserves more credit in LiteFeet history?
Who has one of the most original LiteFeet styles?
Who is known for clean footwork?
Who is known for musicality?
Who is known for energy?
Who is known for hat tricks?
What makes a hat trick clean?
Who is known for shoe tricks?
What makes a shoe trick hit in a round?
Who is known for prop tricks?
What kinds of props have dancers used in LiteFeet?
Who is known for shirt tricks?
What makes a shirt trick land without looking forced?
What is the difference between a clean trick and a wild trick?
What trick should every LiteFeet fan know about?
What trick changed the way people looked at LiteFeet?
What is the hardest type of trick to pull off in a battle?
When does a trick help a round, and when does it hurt the round?
How do LiteFeet battles get judged?
What makes a LiteFeet round good?
What makes someone win a LiteFeet battle?
What is more important: moves, musicality, or energy?
What are the biggest LiteFeet battles?
What was the best LiteFeet battle ever?
What battle should every beginner watch?
What makes a battle legendary?
What is a callout in LiteFeet?
What is battle etiquette?
What should someone know before entering their first battle?
What is the difference between a cypher and a battle?
What makes a LiteFeet event successful?
What event helped bring the community together?
Who are important LiteFeet producers?
What songs helped define LiteFeet?
What is a classic LiteFeet track?
What makes a beat good for LiteFeet?
What is the difference between LiteFeet music and regular club music?
What songs should every LiteFeet dancer know?
What tracks are used in battles the most?
What LiteFeet song deserves more attention?
Who produced some of the most important LiteFeet tracks?
What new LiteFeet music should people listen to?
What makes a LiteFeet remix hit?
What music videos helped spread LiteFeet?
What song instantly makes dancers get lite?
How do you start learning LiteFeet?
What should beginners practice first?
How long does it take to get good at LiteFeet?
What should you practice every day?
What mistakes do new LiteFeet dancers make?
How do you build LiteFeet stamina?
How do you get faster footwork?
How do you make your LiteFeet look cleaner?
How do you find your own LiteFeet style?
How do you freestyle better?
How do you dance on beat?
How do you learn from battle footage?
Should beginners learn history before battling?
How do you know when you are ready to battle?
What is the best way to train for a LiteFeet event?
What does LiteFeet need more of right now?
What does LiteFeet need less of right now?
What is missing from LiteFeet history online?
What should the next generation know about LiteFeet?
What is one LiteFeet moment you wish was documented?
What dancer should be added to the Ledger?
What event should be added to the Ledger?
What song should be added to the Ledger?
What battle should be archived first?
What is the most underrated LiteFeet era?
What makes someone part of the LiteFeet community?
What questions do new people always ask about LiteFeet?
What does the public misunderstand about LiteFeet?
What should people know before speaking on LiteFeet?

```
