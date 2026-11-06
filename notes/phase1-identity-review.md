# Phase 1 identity and public foundation — review

## In scope
- Homepage: concise cultural introduction; What's New; one real archive editorial feature; Explore the Vault; Awards & Recognition; contribution invitation.
- Founder message: approved Dear LiteFeet letter on About; clear entry from homepage and About navigation.
- Editorial styles: existing navy, gold, white and both themes; responsive and scoped public CSS.
- SEO metadata for Home/About and correction of a duplicated brand article.
- Four regression tests: section order, founder letter, public update filtering and unchanged public entry routes.

## What What's New does now
Uses only existing published, explicitly public BetaChangelog records (maximum four), and otherwise displays a clear fallback. It is **not yet** the future full community/editorial content service. Do not claim that community-submitted articles, music, video or event posts are automatically published here.

## Preserved intentionally
- Existing archives and historical display names; DCA and other award routes.
- Nomination/cooldown behavior, moderation, admin, auth, database models, newsletter and contribution handlers.
- No stock/AI portraits, placeholder profiles or invented historical information.
- People, Stories & Media, account registration, claiming, and social features remain for later implementation.

## Review before merging
1. Run: `pytest -q tests/test_phase1_identity.py tests/test_information_architecture.py`.
2. Run full project suite, including browser tests when the configured Chromium environment is available.
3. Review desktop/mobile screens and light/dark modes, especially menu focus, paragraph readability, card spacing and no horizontal overflow.
4. Confirm Home, About, Awards, Archive and Community links; ensure the exact founder letter appears.
5. Confirm no private/beta updates show in What's New.
6. Review search metadata and live routes after approved deployment.
7. Verify sitewide visitor-facing wording, keeping historical original titles intact.

This branch is review-only. Do not merge, deploy or publish without the owner's approval.
