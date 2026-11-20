# P1 historical identity reconciliation — review only

November 20, 2026. Builds on merged archive foundation PR #117.

## Read-only production aggregates
The live PostgreSQL dancer_profiles table has **138 rows**, **136 distinct case-folded/trimmed dance names**, **138 distinct case-folded/trimmed profile slugs**, **0 missing names**, **0 missing slugs**, and **138 missing source URLs**. Every profile has status Active. Matching labels are not evidence of duplicate people.
The ledger_lfa_archive_submissions table holds **5 rows**; the source_information field is blank for each. This does not establish that supporting evidence is absent elsewhere.
No identifying row values, contacts, private notes, account IDs, or raw profiles were exported: only aggregate SQL queries ran.

## Development-only implementation
- archive_reconciliation.py derives deterministic matching hints among separate person source rows using normalized names and explicit aliases. Catalog-only slash-separated names can be review hints, not confirmed aliases.
- Every original (system, key) source locator stays independent; duplicate locators fail closed.
- By default results contain aggregate counts, normalized collision keys and review-required labels. Detailed candidate lists require explicit include_candidates=True in an access-controlled editorial setting.
- An aggregate-only legacy-export function avoids returning individual names or identifying records.
- Test coverage includes read-only behavior, source separation, private-field exclusion, duplicate-name hints, and invalid input.

## Interpretation and release gates
No identities, teams, awards, battles or footage are approved by a matching name. No graph edges are created; no canonical profiles are merged, no redirects are assigned, and nothing is published. Editors must review source evidence, contradictory testimonies, dates and identity consent.
An authorized field-minimized export and individual source review are still necessary. Production backup restoration must be verified separately under issue #127 before production schema changes. This PR must remain in review until tests complete; it does not change production.
