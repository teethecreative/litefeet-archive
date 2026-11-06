# Vault nomination corrections: review and rollout

Development branch only. No production deployment or merge is authorized.

## Modified components

- `models.py`, `nomination_service.py`, `nomination_migration.py`, `phase9e.py`: append-only nominations, atomic per-category cooldowns, idempotent historical import, email-first identity and eligibility/history.
- `dca_rebuild/app.py`: consistent transaction handling and accurate moderation confirmation.
- Nomination templates and `dca-phase9e.js`/`.css`: all 25 official categories in a responsive grid, separate write-ins, history, approved totals, countdowns, summary, normal link/form navigation and preserved browser drafts.
- Both homepages: four main sections; curated media remains available in the alternate archive homepage and historical awards links remain in the rebuild.
- Both sitewide JS/CSS copies and related templates: remove header nomination promotion, retain branding/theme/menu, consistent visited-link styling, visible keyboard focus, persisted theme and SVG arrows instead of platform emoji glyphs.
- `tests/`, `requirements-dev.txt`: backend, migration, concurrency, admin and Chromium checks.

## Additive database changes

New tables:

- `ledger_dca_nomination_entries`: append-only submissions, with unique nullable `legacy_submission_id` for idempotent historical import.
- `ledger_dca_nomination_cooldowns`: primary key `(edition_id, category_id, submitter_hash)` and UTC `next_eligible_at`.
- `ledger_dca_nomination_entry_details`: details linked to the new submission IDs.

Legacy submissions, details, daily claims, categories, stages, nominees and all historical tables remain intact. The legacy table's lifetime `(nominee_id, submitter_hash)` uniqueness constraint remains untouched; the new ledger allows repeat nominations after cooldown. Admin counts and public totals read the new ledger including imported history. Write-in qualification continues to count unique supporters, so repeated support does not inflate qualification.

Startup creates missing tables and imports legacy entries/details in one transaction with `ON CONFLICT DO NOTHING`. No source rows or IDs change. Repeated or simultaneous historical imports do not duplicate support. Historical timestamps are preserved and affect eligibility. New timestamps are explicit UTC stored in the existing naive-UTC column convention.

A conditional database UPDATE reserves each category/email-hash claim. The claim, nominee and submission share a transaction; failures roll back together. Historical eligibility is checked while holding that claim. This protects direct POSTs and concurrent requests independently of frontend buttons.

## Deployment considerations — only after owner approval

1. Back up the database and verify the hosting entrypoint. This repository contains `app:app` (full archive) and `dca_rebuild.app:app` (awards rebuild). Hosting configuration is not stored here. Preserve existing domain/path routing.
2. Pause nomination writes and stop old workers before starting new workers. Do not mix old and new writers: the old application writes to the legacy table with the obsolete daily rule.
3. Preserve `DCA_HASH_SALT`, session signing secrets, nomination enable/deadline settings and confirmed category stages. Changing the hash salt breaks historical identity matching.
4. Start one new worker to initialize additive tables/import history. Reconcile the queries below before scaling and reopening writes. Existing `create_all` startup initialization should run once before multiple workers start.
5. Verify all 25 official categories, eligible write-ins, approved totals, historical records and moderation before accepting production submissions.

```sql
-- Both queries should return zero.
SELECT COUNT(*) FROM ledger_dca_nomination_submissions old
LEFT JOIN ledger_dca_nomination_entries entry ON entry.legacy_submission_id = old.id
WHERE entry.id IS NULL;

SELECT COUNT(*) FROM ledger_dca9e_nomination_details old
JOIN ledger_dca_nomination_entries entry ON entry.legacy_submission_id = old.submission_id
LEFT JOIN ledger_dca_nomination_entry_details detail ON detail.submission_id = entry.id
WHERE detail.id IS NULL;
```

Rollback must preserve new tables. Old code will not display new-ledger submissions. Pause writes and reconcile/export these submissions before reverting; never delete new records to make old code run.

## Existing archive routing limitation

The rebuild currently redirects legacy people/team/music/battle/event/contribution URLs to its homepage. Homepage links now target those existing archive URLs; this PR preserves route handlers and does not change the hosting entrypoint. Verify that existing domain/path routing reaches the full archive application for those URLs. If the rebuild alone serves the entire domain, the pre-existing redirects need archive routing integration. The full archive implementation remains in the root application. Historical awards links resolve within the rebuild.

## Validation

Install `pip install -r requirements-dev.txt`, then `playwright install chromium` (`--with-deps` on a fresh Linux runner).

- `python -m pytest tests/test_nominations.py -q`: 13 backend tests on isolated SQLite databases.
- `TEST_BROWSER=1 python -m pytest -q`: 15 checks including real Chromium at 390×844 and 1440×1000. Covers four homepage sections, email-first entry, all categories, submission/return to grid, independent status, no horizontal overflow, theme persistence, header/menu, Escape focus restoration and visible keyboard focus.
- `TEST_DATABASE_URL=postgresql+psycopg://.../vault_tests python -m pytest tests/test_nominations.py -q`: same 13 backend tests on disposable PostgreSQL 16. The fixture requires a database name ending `_tests` and removes that test database's fixture tables afterward. Never supply a production URL.

Backend coverage includes exact 24-hour boundaries, different categories on the same day, repeat nominations, same-category concurrency, concurrent supporters for one nominee, rollback, historical import/details/count preservation, concurrent imports, UTC, email privacy/validation, CSRF, moderation approvals/rejections, write-in qualification and preservation of the Top 25.

Existing `datetime.utcnow()` defaults elsewhere emit Python deprecation warnings. New cooldown calculations use explicit UTC.
