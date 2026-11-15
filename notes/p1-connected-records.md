# P1 connected records: second development milestone

November 15, 2026. Extends draft PR #117. Development staging only; no production
migration, merge or deployment is authorized by these changes.

## Result

The isolated staging database now has typed records and evidence-backed,
reviewable connections. The service and authenticated admin UI support proposing,
approving, rejecting, reversing and reopening connections with mandatory reasons
and retained decision history. The full dancer → team → event → battle → footage
journey is tested with synthetic fixtures, not invented historical relationships.

The repository import preserves all 314 source rows. Each source identity keeps
its own permanent UUID; matching names never combine rows. Existing source IDs,
slugs, labels, explicitly recorded aliases, date uncertainty and separate event/
upload dates stay available in immutable revisions. Canonical presentation is
provisional: reimports retain its initial label and add source labels for search,
rather than silently replacing it. A reviewed identity match is a reversible
assertion, not a destructive merge or an automatic canonical-profile resolution.

## Typed connections

| Relationship | From | To | Optional evidence context |
| --- | --- | --- | --- |
| Member of | Person | Team | From/until with year, month or day precision; date certainty |
| Participated in | Person or team | Event or battle | Dancer, judge, host, photographer, producer, organizer or team role |
| Contains battle | Event | Battle | Independent battle record |
| Documented by | Event or battle | Footage | Start/end timestamps in seconds |
| Produced | Person | Track | Source citation |
| Featured in | Track | Footage or battle | Source citation |
| Same identity | Person ↔ person or team ↔ team | Same record type | Explicit human decision; source rows remain separate |

Records also support preserved claims, moves and awards. A track is the music
unit in this milestone; a full release/album/credit hierarchy remains future work.
No battle winner is inferred from participants, footage or community sentiment.

## Review and recovery behavior

- Every connection starts pending and cites an immutable source revision.
- Type checks reject incompatible endpoints, self-links and unsupported fields.
- Multiple roles at one event/battle and multiple footage segments are distinct.
- Membership dates preserve their precision. A year-only end date is not treated
  as January 1. Invalid dates, reversed intervals and invalid timestamps fail.
- Decisions require an authenticated admin session at the HTTP boundary, a CSRF
  token, a reason and the expected connection version. Repeated or stale decisions
  return a conflict instead of overwriting another decision.
- Approval requires its evidence to be present in the latest input snapshot.
  Changed/removed evidence blocks approval until a new proposal cites current
  evidence. Prior approved decisions stay auditable and visibly stale; path
  exploration excludes stale connections without silently reversing the decision.
- Reversal removes the approved connection from paths but retains the connection,
  evidence, source records and decision history. Reopening returns a rejected or
  reversed connection to pending; a separate approval is required.
- Same-identity assertions do not contribute to path traversal or combine IDs.
- Every write backs up the recognized staging snapshot and is transactional.
  Version 1 snapshots receive an additive, backed-up upgrade to version 2.
- GET requests open snapshots read-only and never create or upgrade databases.

## Running against a development snapshot

```sh
python -m dca_rebuild.archive_foundation --stage /tmp/vault.staging.sqlite
```

This upgrades recognized version 1 snapshots and preserves UUIDs and history.
The built-in repository adapter currently supplies people, events, claims, moves
and the awards archive. It does not invent missing teams, battles, tracks or
footage. To import those from an inspected source export:

```sh
python -m dca_rebuild.archive_foundation --input /path/to/complete-source-export.json
python -m dca_rebuild.archive_foundation --input /path/to/complete-source-export.json --stage /tmp/vault.staging.sqlite
```

The input is an array of objects with `system`, `key`, `title`, `kind`, `visibility`
and `payload`. Use stable original source keys. Supported graph kinds include
`person`, `team`, `event`, `battle`, `track` and `footage`. Set private imported
records to `private_review`; the visibility field never publishes anything.
Payload may carry explicit `aliases`, `event_date`, `upload_date`, `date` and
`date_certainty`, along with its source evidence. Custom exports are private
staging inputs; inspect and minimize their fields before use.

`--input` is the complete current snapshot, not a delta. Sources missing from it
are preserved historically but count as absent when checking current evidence.
Keep the staging file and crosswalk; rebuilding a fresh file creates fresh UUIDs.
Source locator remapping/redirects still need an explicit reviewed migration.

The existing development Flask instance can opt in explicitly:

```python
app.config.update(
    VAULT_ARCHIVE_STAGING_PATH='/tmp/vault.staging.sqlite',
    VAULT_ARCHIVE_STAGING_REVIEW_ENABLED=True,
)
```

Then use `/admin/archive/connections` after administrator login. Without a path,
the page explains that staging is unconfigured. Without the review-enabled flag,
it is read-only and POST requests fail. No production database environment
variable is used for the graph, and no graph schema is registered with production
SQLAlchemy metadata or automatically created at startup.

The current site has shared administrator credentials. Audit attribution honestly
identifies a signed authenticated admin session, not an individually verified
human. Individual administrator accounts and departmental permissions are still
required before using this as a production editorial authority system.

## Validation and limits

Focused foundation/archive/admin regression selection: **59 passed, 2 optional
browser checks skipped**. Complete default suite: **235 passed, 11 failed, 10
skipped**. The 11 failures are the same test identities reproduced on unchanged
`main` in the first milestone; no additional default-suite failures were introduced.
Python compilation and `git diff --check` pass.

The actual repository snapshot was upgraded/reimported with its IDs preserved:
276 person source identities (not 276 unique people), 24 events, 6 claims, 7 moves
and 1 awards record. Foreign-key validation reports no errors. There are zero
approved historical graph links: this implementation does not manufacture the
teams, battles, tracks or footage absent from that source adapter.

Coverage includes the full approved path, reverse traversal, reversal/reopening,
source preservation, alias search, multiple roles, music connections, unknown
outcomes, event/upload date separation, stale evidence, optimistic concurrency,
reason-required rollback, schema upgrade/backups, malformed input, explicit export
imports, authentication, CSRF, read-only defaults and public isolation.

Real-browser tests are provided for 390px mobile and 1440px desktop review flows.
They were attempted locally but Chromium could not launch because this execution
environment denies its required socket operation. These visual/browser checks
are unverified, not passed. On a browser-capable machine:

```sh
TEST_BROWSER=1 python -m pytest -q tests/test_archive_graph.py -k browser
```

Set `CHROMIUM_EXECUTABLE` only when using a system browser rather than Playwright's
installed Chromium. Default tests skip these two opt-in browser checks.

Remaining production prerequisites: inspected source exports (including music,
teams, battles and footage), canonical identity/locator resolution, individual
permissions, full provenance/claim policies, PostgreSQL migration design, a
verified production backup and restore rehearsal, resolution of existing release
test failures, browser QA, and explicit cutover/deployment approval. Archive AI
does not crawl, analyze footage, create tasks or mutate records in this milestone.
