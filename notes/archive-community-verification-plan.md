# The LiteFeet Vault — Archive records and community verification

Status: design and discovery in progress. Not a production release. No data migrations, publishing, or deployment.

## Intent
The archive must be more than static historical writeups. Every individual archival record should have a way for community members to add input, challenge a claim, agree or disagree with an interpretation, and attach supporting evidence. Neither community popularity nor one person's vote determines historical truth. Editorial moderators retain responsibility for validating and revising records, with an auditable correction history.

## Existing code / historical sources discovered
The repository includes TWO distinct Flask applications, not one shared production data model:

- `dca_rebuild/app.py` is the current production app. Its `/archive` page currently displays the August 2023 Dancer's Choice Awards archive and only published `LedgerEra` rows on the timeline.
- Root `app.py` contains an earlier `/verify/<submission_id>` workflow for `submissions` and `verification_votes`, with **true / false / debatable** votes, a context note, source URL, and optional contributor details. It also has a controversy queue. This code is historical reference, **not** evidence the feature exists in the current production app.
- `litefeet_seed_data.py` contains 18 seeded research records (origins, Harlem Shake, music evolution, moves, dancers). Many are explicitly marked Needs Verification, and some contain third-party citation URLs.
- `seed_archive.py` contains 10 broad collection/research queue records; these are starter placeholders, not completed historical entries.
- `ghost_dancer_seed_data.py` contains historical dancer aliases and source notes.
- `seed_bodybag_events.py` includes event research records.
- `data/imports/dancers_choice_august_2023_official_results.json` includes 32 recorded winners; the current public 2023 archive uses its own production content pipeline.
- `data/homepage_prompt_questions.txt` contains contributor/history questions (including a few legacy Ledger references).

Do **not** directly join these two applications' tables, expose raw seed notes or assume their database records are already present in the rebuild. Preserve all historical award records and links.

## Record types and the right interaction

### Factual historical claim — verification
Example: a proposed date, event outcome, dancer attribution or move origin.

Labels:
- **Accurate / True**
- **Inaccurate / False**
- **Needs context / Debatable**

Every response optionally includes a reason, firsthand account, credited source, and correction. The page shows the **record's editorial verification status** separately from the community response distribution. Example: *Under review* is not the same as *community majority agrees*.

### Interpretation, opinion, or community recollection — perspective
Example: whether an era was influential or a movement had a particular cultural impact.

Labels:
- **Agree**
- **Disagree**
- **Mixed / Add perspective**

Interpretations are clearly marked as perspectives, not treated as verifiable true/false claims. Personal memories can include context, dates, places, and contributor attribution.

### Other record classes
For a person, crew, song, battle, flyer, event or award, attach feedback to an **individual assertion/field** or item with a clear review purpose, not an amorphous 'vote on the person'. Example: on a dancer page, the claim *member of Crew A* can be challenged; the dancer's existence or identity is not put to a popularity vote.

## Proposed public record layout
1. Title, record type, time/era, published/under-review/disputed status, provenance and last-reviewed date.
2. The claim or archival description, clearly attributed to existing sources.
3. Evidence/citations and related people/events/moves.
4. Community review panel: the correct choice set by record type, counts if meaningful, and a clear disclaimer that votes don't establish historical truth.
5. Optional evidence URL, first-person context, correction, and credit preference. Guests can participate without creating an account; optional account creation is separate and future-facing.
6. Related records, corrections/version history and source-review status.

## Integrity, abuse and privacy controls before public activation
- A stable record ID/slug; one current opinion per identified user or abuse-resistant guest identity per assertion, with the ability to change a response. Do not expose raw identity keys or email addresses.
- CSRF protection, rate limiting and spam prevention. The original implementation appends unrestricted votes; **do not port it unchanged**.
- Never publish private contact details, unpublished notes, evidence submissions, or allegations automatically.
- Community-supplied links and notes enter moderation. Handle safety/privacy complaints and contested claims through a correction/appeal path.
- Store provenance, published versions, editorial decision reasons, update times and record redirects for merges.
- Accessibility: descriptive buttons, keyboard support, fieldset/legend, clear confirmation/error states.
- Do not fabricate source counts, endorsement counts, photos or verified status.

## Archive landing page direction
Avoid an empty grid of fictional completed collections. Show (a) the **published 2023 historical award archive**, (b) published eras if any, and (c) a clearly separated **research in progress** browse area based on known seed categories:
- Origins and Evolution
- Moves and Technique
- Dancers and Crews
- Battles and Events
- Music and Media
- Awards and Recognition

Show specific research records only after source/privacy review; use 'Research under review' labels. Individual archive details + voting/moderation should be developed together, not a dead-end decorative mockup.

## Next implementation tasks
1. Audit actual public-ready records and sources; distinguish verified, needs verification, draft, and placeholder.
2. Implement additive, production-native archive record and response models; keep untouched award/nomination workflows and tables.
3. Build read-only search/browse and record detail pages; render only published records or explicitly labeled public review items.
4. Implement factual and opinion response forms + evidence submission + moderation in the same feature batch.
5. Write tests for guest participation, duplicate-vote protection, CSRF, moderation filtering, privacy, historical route stability, and mobile accessibility.
6. Prepare PR for owner review; no automatic merge/deploy.
