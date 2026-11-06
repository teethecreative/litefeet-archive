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

## Follow-up: category and suggestion browser

The category grid now shows linked category names only. Category pages list all pending and approved suggestions, with a separate Nominate action; selecting a suggestion opens its team, location, Instagram and nomination reasons. A suggestion can be nominated again through a prefilled form, subject to the same category cooldown. No email-switch promotion or public approval classification appears. The existing change-identity endpoint remains available for compatibility, without a navigation button.

Rejected entries remain stored and hidden from other visitors. Qualification and administrative counts continue using the existing moderation rules; public suggestion totals now include pending submissions. Only public nominee fields are rendered in details, with no supporter email, hash or IP. Existing nomination histories, browser drafts and summary counts are preserved. This follow-up changes no database schema and requires no additional migration.

Validation: 17 checks with SQLite and mobile/desktop Chromium, plus the 15-test backend suite against PostgreSQL 16. New checks cover category-name-only tiles, immediate pending visibility, suggestion details and prefilled nomination, category isolation, hidden rejected entries, private identities, and unchanged write-in qualification.

## Follow-up: archive placeholders and scrollable category results

The rebuild's homepage destinations for People & dancers, Crews & teams, Music, Battles and Events now render distinct public “In development” pages at their existing URLs instead of redirecting home. Existing People/Teams/Events aliases share the relevant placeholder. Historical awards routes and the full archive application's records/handlers remain unchanged. This resolves the homepage loops with the requested placeholder approach; a full archive integration can replace these placeholders later.

Returning-category results and new-category ideas now use semantic tables with native scrolling, sticky column headings and a sticky category column. Approximately five rows are visible, measured from the actual row heights. Search filters the entire table without pagination, reports matching counts and handles no matches. Full descriptions remain accessible in expandable details. Mobile supports scrolling within the table without page-wide horizontal overflow; keyboard focus and light/dark themes remain supported. Vote counts, sorting and calculations are unchanged.

Validation: `TEST_BROWSER=1 python -m pytest -q` passed all 25 checks, including distinct placeholder routes, retained result rows/table semantics, five-row viewport sizing, keyboard scrolling, search/empty/reset behavior, mobile/desktop layouts and themes, plus all existing nomination regressions. `git diff --check` passed. No database migration is needed for this follow-up.

The 2026 awards landing page is now shortened to one sentence, one Nominate action, one Category results action, and a compact 2023 archive link. The repeated entry cards and oversized Current Edition panel are removed; participation instructions remain on the nomination page. All nine targeted route/mobile/desktop checks passed after this change.

## Follow-up: community nominee standings after submission

Successful nomination now redirects to `?view=results`, displaying community-wide nominee names and totals grouped by category rather than the visitor's personal dashboard. Visitors can also choose Done / View nominee standings, view results without entering an email, open nominee details, or return to nominate in another category. Pending suggestions remain visible and rejected entries remain hidden. Result/detail views do not render personal history or eligibility counters; personal activity is collapsed in the nomination picker. No identity, cooldown or counting rules change, and no database migration is needed. All 27 backend and mobile/desktop Chromium checks passed, including combined totals from different emails, private-history isolation and continuation to other categories.

## Follow-up: compact nominee standings

The standings page now uses a small DCA 2026 label, compact title and short Nominate action. Category results form one column of closely spaced groups, with plain nominee links and right-aligned counts instead of large cards, gold nominee buttons and repeated visible table headers. Table captions/column headings remain available to screen readers, links retain 44px touch targets and keyboard focus, and nominee details/totals remain unchanged. No backend or database change. The 18 nomination/backend/mobile/desktop checks passed; mobile screenshots were inspected and the inherited dark-mode card borders were removed with a scoped style.

## Follow-up: show every category in standings

Standings now include all 25 official categories and all eligible write-in categories, including those without nominees. Empty categories show “No nominations yet.” Existing nominee names, support totals and compact styling remain unchanged. No backend/database changes. Tests cover all categories before and after a nomination, plus mobile/desktop visibility of empty categories.

## Follow-up: process, categories, then email

The nomination entry page now explains the process, lists all 25 configured official categories (with available write-ins separately expandable), and then asks for email. The category preview scrolls locally to keep the form reachable on mobile. Continue still validates email and checks eligibility before any submission; historical identity hashes, independent cooldowns, category configuration, standings and moderation remain unchanged. This updates the earlier email-first presentation to the owner's requested introduction order. No schema or database migration is required.

The introduction is additionally condensed to a small title, three short process steps, a 200px scrollable category preview (all categories retained), and the email field/Continue action with one short privacy line. Remove the enclosing card and excess top padding. Targeted route and mobile/desktop checks passed; the email form begins within 850px at both tested widths.
