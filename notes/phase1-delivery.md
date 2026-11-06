# Phase 1 delivery

## Public navigation and routes

| Section | Route | Phase 1 content |
| --- | --- | --- |
| Home | `/` | Editorial introduction, 2026 news, 2023 archive, community updates |
| The Archive | `/archive` | Existing 2023 collection; timeline linked only when published eras exist |
| Awards | `/awards` | Dancer’s Choice and LiteFeet Awards hubs, historical results |
| Community | `/community` | Existing historical contribution workflow, contact and published public updates |
| About | `/about` | Mission, archive process and existing contact |

The reusable catalog reserves People and Stories & Media in their requested positions, but does not promote them until real production content and publication rules are connected. Existing placeholder URLs remain accessible. No empty new profile, article, media or milestone pages were created. HypeItUpTV's existing route remains available without promotion as a complete program.

New program landing page: `/awards/dancers-choice`. Existing 2026 participation, category results, 2023 historical results, LiteFeet Awards contribution form, admin and authentication URLs remain intact. `/archive/timeline` reads published eras only and returns 404 when none exist. Legacy submission GET shortcuts now lead to `/community#contribute`; existing submission POST handlers are unchanged.

## Reused content and protection

Reused the structured 2023 archive, LiteFeet Awards contribution form, published `LedgerEra` entries, explicitly public and published `BetaChangelog` updates, and existing published contact address. Drafts, private source notes and beta-only updates remain private. The original independent Flask application's routes, templates and models were not migrated or mounted.

No database migration, schema change or data rewrite is required. Nomination service, phase9e nomination handlers, cooldown enforcement, hashing, moderation, category merging and authentication code are unchanged. The existing authenticated admin toolbar remains visible while Admin is excluded from public navigation. Previously proposed standings disclosure/Done-reset work remains separate in PR #8.

## Main modified files

- `information_architecture.py`: section catalog, read-only public content, hubs and context.
- `_navigation.html`, `_site_chrome.html`, `vault_section.html`, home and footer: navigation, breadcrumbs, program links and reused content.
- Production `litefeet-sitewide.js` and CSS: right drawer, submenus/back controls, keyboard/focus behavior and both themes.
- `seo.py`, `_seo_head.html`, nomination template head includes and `static/social/`: server-rendered standings share description and hand-authored navy/gold PNG, with canonical query handling.
- Tests and audit/delivery notes.

The share image is a public 1200×630 PNG with SVG source. Messaging services may retain previously cached previews after deployment. No image-generation service was used.

## Validation

Full suite: 42 passed, including browser tests. After final scoped styling and metadata refinements, all 7 information-architecture tests passed again. Coverage includes every promoted link/anchor, preserved routes, private-content filtering, admin toolbar/authentication, nomination regression tests, share metadata/image, mobile and desktop navigation, keyboard focus, no-JavaScript fallback, both themes and overflow checks. Existing datetime deprecation warnings remain.

Python compilation, JavaScript syntax and `git diff --check` passed. No separate frontend build, lint or type-check command is configured. Visual screenshots were reviewed for the mobile drawer, desktop dark awards hub and share card. Production deployment and messaging-platform cache refresh have not been performed.

## Recommended Phase 2

1. Audit publication/consent rules and actual content in the original people/media application before introducing a read-only integration with the production rebuild.
2. Add reviewed profile identity links to existing awards and events, preserving historical display labels; avoid automatic fuzzy-name merging.
3. Publish sourced timelines, events and cultural milestones through the existing review infrastructure.
4. Connect real articles/interviews/media and their publication controls; activate People and Stories & Media only when each offers meaningful content.

Deploy through the existing application process only after review and approval. No new infrastructure or database preparation is necessary for this phase.
