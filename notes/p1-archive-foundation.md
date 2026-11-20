# P1: historical data consolidation and review foundation

November 15, 2026. Source baseline: `main` at `9f9628d`.

This is the first P1 implementation milestone, not completion of the full P1 program.
The live database is not migrated and Archive AI is not deployed.

The subsequent [connected-records milestone](p1-connected-records.md) adds a
backed-up version 2 staging upgrade, typed graph records, explicit export import,
an opt-in admin decision UI and reversible connections. The details below record
the initial foundation baseline; consult that note for current behavior.

## Inventory and reconciliation findings

The preview reads actual repository snapshots, not the production database. The
earlier audit's count of 197 timeline entries is not reproduced by this catalog
inventory; do not use it as a migration row count.

| Source | Current evidence | Treatment |
| --- | --- | --- |
| `archive_catalog.all_records()` | 176 records: 24 events, 5 researched dancer profiles, 133 recovered identity pages, 6 historical claims, 7 move records, 1 awards archive | Preserve current labels, status, citations, dates and locators |
| `archive_recovery.recovery_candidates()` | 138 original profile IDs and legacy slugs | Private source rows; no generated biographies, private contacts or affiliation assertions |
| Legacy `app.py` | SQL definitions for dancer profiles, submissions, media, music projects, profile claims, calendar metadata, battle records, saved items and team access | Schema evidence only; production rows not accessed |
| Rebuild `models.py` | `LFARecord`, archive submissions, archive verification responses, gathering submissions and review history, awards models | Existing services retained; production extraction remains pending |
| Music service | Separate existing catalog/import workflow | Not ingested by this milestone; do not count as consolidated |

The legacy battle schema holds competitor, team, judge and winner strings.
Its event/submission integer fields do not by themselves establish validated
canonical relationships. The public catalog's `related_to` field is free text.
Neither is sufficient evidence to automatically attach a person or declare an outcome.

Current preview: 135 groups of normalized-name matches, 157 records without a
linked citation, 24 event date-certainty reviews, and 1 possible relationship.
Most name matches compare preserved source rows with existing public identity
pages. These are reconciliation candidates, not 135 confirmed duplicate people.
Missing links do not mean no source exists: existing source labels remain evidence.

## Implemented

1. Read-only deterministic consolidation preview, grouped by basics, sources,
   possible duplicates and possible relationships. Every suggestion includes
   source locators, a reason and supporting evidence. No external crawling,
   automatic research assignments, identity merges or publishing.
2. Private, authenticated admin research-review page with category filters and
   20 suggestions per page. Existing recovery and editorial notes remain available.
   This page previews the repository snapshot, not decisions made in a staging file.
3. Explicit, local staging importer with permanent UUID entity IDs independent of
   display labels, a source-system/key crosswalk, immutable distinct source
   revisions, snapshot membership, pending suggestions and foreign-key-backed
   suggestion/subject links. Each original profile ID stays separate until reviewed.
4. Idempotent reimports preserve entity IDs and do not duplicate revisions or
   suggestions. Previously seen sources are never deleted when absent from a new
   snapshot. Snapshot membership records removals and returns, including returns
   to an earlier revision.
5. Backups before updating a recognized staging snapshot, database identity checks,
   foreign-key validation and transactional imports. Existing production environment
   variables are ignored. No new table is registered with production `Base` or
   automatically created at application startup.

## Running the preview and staging import

```sh
python -m dca_rebuild.archive_foundation
python -m dca_rebuild.archive_foundation --stage /tmp/vault.staging.sqlite
```

The default command prints a preview and writes no database. The explicit import
accepts only regular local filenames ending in `.staging.sqlite`. Existing files
must have exactly the expected staging tables and schema version. Snapshots and
their uniquely named backups are ignored by git. Keep the same staging file and
crosswalk between imports; a fresh file generates a fresh ID set. A reviewed,
explicit locator-remapping operation is still needed before changing source slugs.

An approval status in this experimental schema is not a production publication
mechanism. This milestone intentionally provides no approval/mutation endpoint.
Source documents remain the source of truth until a reviewed cutover.

## Approved product requirements versus open implementation

| Decision | Product status | Implementation status |
| --- | --- | --- |
| Connected database before dependent releases | Approved | Isolated staging foundation implemented; full entity graph pending |
| All member/guest submissions require approval | Approved | Existing handlers retained; cross-feature enforcement audit still required |
| Authorized administrators resolve historical disputes | Approved | Existing review retained; new dispute decision/version service pending |
| AI suggests and explains; people approve changes | Approved | Deterministic suggestion foundation implemented; AI processing pending |
| Preserve uncertain dates, attribution and revisions | Approved | Source snapshots retained; structured claims/evidence/event dates pending |
| Department permissions, dispute thresholds, points values | Open | No defaults silently promoted to policy |
| Production data migration/cutover | Requires separate review and deployment approval | Not performed |

## Remaining P1 work in dependency order

| Milestone | Concrete work | Acceptance gate |
| --- | --- | --- |
| Production inventory | Obtain read-only exports with source IDs and schema versions; include music, events, teams, media and awards; reconcile counts and privacy fields | Every source row accounted for; sensitive fields excluded from public projections |
| Canonical graph | Typed people/teams, aliases, dated memberships, events/occurrences, independent battles, participants/roles, tracks/releases, media timestamps | Follow a sourced person → team → event → battle → footage path using foreign keys |
| Provenance and decisions | Claims, source attestations, evidence links, verification states, append-only decisions with reviewer/reason; reversible merges and locator redirects | Unknown winners stay unknown; conflicts coexist; reverse a merge without losing references |
| Admin workflow | Durable review queue, assignment, urgency/department sorting, escalation, role checks and source comparison | Unauthorized edits fail; owner and decision history visible; reviewed changes reversible |
| Archive AI | Change-triggered internal analysis, deduplicated suggestions, evidence-linked explanations, human decision audit, approved research-task creation | Rejected suggestion changes no canonical record; stale suggestion cannot overwrite newer evidence |
| Migration and cutover | Validate production backup and restore; rehearse on copy; compare row counts and references; transactional cutover and rollback | Restore successfully demonstrated; existing URLs and awards flows preserved |

No public browsing, nominations or gameplay is switched to the staging database.
No merge, production migration or deployment is included in this milestone.

## Verification

The focused foundation/archive/admin regression selection passes 35 tests,
including 9 new foundation checks. Python compilation and `git diff --check` pass.
The complete suite reports 211 passed, 11 failed, 8 skipped. Unchanged `main`
reports 202 passed, the identical 11 failed tests, and 8 skipped. Existing failures
cover music/awards text, sharing, the homepage calendar, the people word cloud,
and favicon expectations. This is not a green release baseline. Browser/device visual QA, PostgreSQL
staging compatibility and production restore testing are not verified here.
