# Phase 1 audit (before implementation)

## Architecture and existing content

The repository contains two independent Flask entrypoints: `app:app` (large original archive application, people/music/media/auth and many legacy route overrides) and `dca_rebuild.app:app` (the current production application, confirmed in prior live route checks). They use different models/table namespaces. Do not mount the original application or infer that its records are publicly available through the rebuild.

Production uses SQLAlchemy and the existing DATABASE_URL; awards, nominations, admin authentication, category configuration/moderation/merging, write-in qualification, newsletter subscriptions and historical-contribution review are implemented in the rebuild. `phase9e.py` replaces the public nomination handler and enforces hashing/per-category rolling cooldowns. The JSON-backed 2023 archive contains 31 categories, 152 nominee entries and 32 winners. `LedgerEra` has an explicit published/draft state; source_notes are internal. `BetaChangelog` has separate publication and public/beta visibility controls.

The public menu currently discovers legacy links in HTML and promotes individual award programs and Admin. It lacks section hierarchy, breadcrumbs and back controls. The alternate original application's navigation and routes must remain intact until it is explicitly migrated. Existing root `templates/about.html` provides mission and review language plus the published contact address. The rebuild's people/music/battle/event URLs are placeholders; many other legacy paths redirect to the homepage. They must remain reachable but should not be promoted as working archive features.

## Preserved URLs / behavior

- `/`, all `/awards/dancers-choice/*` routes, query-based nominee standings/details, category surveys/results, historical results, `/awards/litefeet-awards*`, `/awards/hypeitup`, and old `/dca*`, `/litefeet-awards`, `/hypeitup-awards` aliases.
- Every `/admin*` route and its authorization, CSRF, moderation, merge and configuration behavior. Keep protected administration links available in the existing authenticated toolbar, not public navigation.
- Existing newsletter, historical submission, beta feedback and other POST destinations. No new upload or moderation workflow.
- Existing people/team/music/events/battles placeholders and legacy detail routes, plus the separate original app's public URLs.
- Existing indexed award URLs and sitemaps; new section hubs are additive. Adapt `/awards` from its current edition redirect to a section hub and `/about` from its homepage redirect to meaningful mission/process/contact content.

## Phase 1 decisions

The seven-section catalog order is Home, The Archive, People, Stories & Media, Awards, Community, About. Activate only five ready sections in that order: Home, The Archive, Awards, Community, About. People and Stories & Media stay out of active production navigation; their existing public URLs are preserved. Incomplete DJs/crews/profile/editorial/upload/milestone/event sections are not given empty new pages. HypeItUpTV's existing page remains accessible but is not promoted as a complete program.

Reuse the 2023 archive as a featured historical collection; show only published eras on a public timeline, and only explicitly public/published changelog entries as community updates. Use the current historical-contribution form for award records/corrections and the already-published contact address for general enquiries. No private notes, draft eras, pending submissions or beta-only updates may be exposed.

Risks to test: accidental hiding of the admin toolbar; nested menu focus/keyboard/back behavior; query-sensitive active states and canonical/share metadata; exposing unfinished sections or unpublished records; regressions in nomination eligibility/CSRF and existing URLs; stale client-side link discovery; layout/theme compatibility; share crawlers needing server-rendered metadata and a public PNG.

The previously requested standings dropdown/Done reset belongs to separate PR #8 and is not included in this navigation migration. The outstanding standings link-preview improvement will be implemented without changing nomination business logic.
