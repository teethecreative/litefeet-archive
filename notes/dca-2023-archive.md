# Dancer’s Choice Awards — August 2023 archive

Scope: replace only `/awards/dancers-choice/2023` in the awards rebuild with its complete historical archive. Other edition routes, navigation, authentication, nomination rules and database records are unchanged.

## Structured data and provenance

`dca_rebuild/data/dca_2023_archive.json` stores all 31 categories and 152 nominee entries with explicit boolean winner designations. There are 32 winning entries; Best Team Video has both 2Crafty and Bombsquad as co-winners. Winners remain nominee entries in the data and are displayed only once within their category.

The complete labels and designations supplied by the owner match the existing repository CSV `data/imports/dancers_choice_august_2023_all_nominee_fixed_votes.csv`; all 32 winners also match `data/imports/dancers_choice_august_2023_official_results.json`. Neither source is modified. Only category/name/winner fields were copied into the public archive data; no counts, rankings, affiliations, biographies or descriptions were added.

Source caveats are retained in the JSON's internal `source` block:

- The archived spreadsheet labels winner designations as official PDF results. The underlying PDF has not been independently rechecked.
- Spreadsheet totals for Best Shoe Tricker, Most Fearless and Best Combo Dancer were adjusted to match recorded PDF winners. Totals must not be published as original voting records.
- Nominee ordering follows the supplied records and is not independently verified ranking. Names, casing, punctuation and distinct spellings remain verbatim, including E Solo/Esolo and SoundCloud/Sound Cloud.

The data file lives outside Flask's static directory. The read-only loader exposes only explicit category/nominee fields to the template. It validates 31 categories, 152 entries, 32 winners, one co-winner category and both expected Best Team Video co-winners. Frozen data classes prevent accidental mutation of cached archive records.

## Presentation and contribution workflow

The new page uses the existing Vault navigation, footer, theme controls and navy/gold/white/gray palette. It includes the supplied introduction, overview counts, category search, All categories reset, and native keyboard-accessible accordions. Winners are prominent in each category summary; the open content shows only other nominees in an unranked list. A bounded scroll region keeps all categories available without making the page excessively long. Native accordions also work without JavaScript.

The supplied Help Preserve LiteFeet History text links to the existing `/awards/litefeet-awards#contribute` form. Its POST destination, fields and pending-review behavior remain unchanged. The archive's SEO title and description are updated only for the 2023 Dancer’s Choice route.

## Modified files

- `dca_rebuild/app.py`: 2023 route renders the dedicated archive template.
- `dca_rebuild/archive_2023.py`: immutable, validated read-only loader.
- `dca_rebuild/data/dca_2023_archive.json`: complete structured records and internal provenance.
- `dca_rebuild/templates/dca_2023_archive.html`: archive, counts, accordions and contribution link.
- `dca_rebuild/static/css/dca-2023-archive.css`: page-scoped responsive styling.
- `dca_rebuild/static/js/dca-2023-archive.js`: local category filtering/reset.
- `dca_rebuild/seo.py`: route-specific title/description.
- `tests/test_dca_2023_archive.py`: integrity, presentation, workflow and browser regressions.
- This implementation note.

## Validation

- Full suite: `TEST_BROWSER=1 PLAYWRIGHT_BROWSERS_PATH=/workspace/pw-browsers python -m pytest -q --disable-warnings` — **34 passed**.
- Data checks compare every label and winner flag against the original CSV, check all winners against the separate winner source, preserve exact spellings, verify the co-winners, and ensure public rendering contains 32 winners plus 120 other nominees with no within-category duplication.
- Route checks confirm that the archive is read-only, unrelated historical pages retain their original behavior, and the existing contribution form still accepts a 2023 submission as pending review.
- Chromium at 390px and 1440px validates counts, search/no matches/reset, individual accordion expansion/collapse, keyboard scrolling, dark/light theme persistence, no page-wide horizontal overflow, contribution navigation and native accordions with scripts disabled. Screenshots inspected.
- Python compilation, `node --check` for the new JavaScript and `git diff --check` passed. This Flask repository has no separate configured frontend build or lint command. Existing datetime deprecation warnings remain outside this change.

No schema migration, reseeding, hosting configuration or new dependencies are required. Include the new JSON alongside the application code during deployment. This branch is prepared for review only; it has not been merged or deployed.
