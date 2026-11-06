# The LiteFeet Vault — Archive data foundation (staging only)

**Status:** Work in progress for owner review. Not merged, deployed, imported, or publicly exposed.

## What's implemented
- Added three independent, additive SQLAlchemy data models for an archival record, a verifiable factual assertion within a record, and a moderated visitor response.
- Added a **manual** legacy research staging script, `python -m dca_rebuild.stage_archive_research`, which defaults to a dry run that makes no database connection.
- Explicit opt-in `python -m dca_rebuild.stage_archive_research --apply --confirm IMPORT_PRIVATE_RESEARCH` would create archive-only tables and import the 18 existing core seed records as **private, under review**, with original notes preserved in an internal JSON field. No changes are made to any existing awards, nominations or admin records.
- The importer is idempotent: it skips an existing source key instead of overwriting a reviewed record.
- Added automated tests covering the 18 seed records, private visibility defaults, default dry-run behavior, and idempotency. Tests were authored but **not run in this connector-only environment**.

## How the UI should look
1. Archive home: compact editorial search and category links; substantive sourced list rows, not giant placeholder cards.
2. Detail: title, era, research status, short historical account, original sources and related content; a small inline response row.
3. Community verification: True | False | Debatable. Choosing Debatable reveals a short optional explanation. Do not store or publish visitor submissions until anti-abuse and moderation APIs are reviewed.
4. Dancer page: reference text and verified/attributed source claims, authentic or no portraits. Don't ask visitors to vote on a person's identity.
5. Event page: event date/venue/source, planned lineup distinct from verified outcomes.

## Still required prior to merge/public activation
- Source validation and owner/editorial review of private records.
- Database versioning/migration, field-level source links and publication workflow.
- Search and detail API routes, pagination, actual responsive templates and accessibility checks.
- Moderated vote endpoint with CSRF, deduplication/rate-limits, consent/privacy notices, evidence URL validation.
- Tests for server-side publication filters, guest idempotency, data integrity, CSRF, abuse and admin moderation.
- Desktop/mobile and light/dark visual tests.
- **No deployment or production data import without explicit approval.**

The owner asked to see realistic examples first; this branch is deliberately only the data foundation.
