# The LiteFeet Vault — design system foundation

Status: Phase 1 foundation / Phase 2 component contract. **Not a complete
sitewide redesign.** All public page behavior, URLs, historical records,
nomination flow, and admin permissions must be preserved during migration.

## Source of truth

- `dca_rebuild/static/css/lfv-design-tokens.css`: canonical color, typography,
  spacing, layout, control, radius, and light/dark mode tokens.
- `dca_rebuild/static/css/lfv-ui-components.css`: shared, opt-in component CSS.
- `dca_rebuild/templates/_ui_components.html`: reusable public-page Jinja
  macros for heading and action-link markup.
- `dca_rebuild/static/css/litefeet-sitewide.css`: imports both files and retains
  site-wide navigation and legacy layout rules.
- Existing `--lfv-*` variables remain as compatibility aliases; **do not**
  duplicate their declarations in versioned editorial files.

## Approved visual identity

- Navy `#0A2C5F`, gold `#C9A127`, white `#FFFFFF`.
- Light background `#E9EDF4`; dark background `#0B1422`.
- Editorial sans typography, generous content width, restrained borders,
  slightly rounded corners, and consistent page hierarchy.
- Gold with navy text for primary actions. Secondary links should not look like
  primary actions. Dark mode must retain contrast and visible focus rings.

## Component contract

- `lfv-ui-page-header`: page introduction, distinct from cards and site chrome.
- `lfv-ui-kicker`: section/category label.
- `lfv-ui-lead`: explanatory intro text.
- `lfv-ui-section`, `lfv-ui-card`: content grouping.
- `lfv-ui-action --primary/--secondary`: action hierarchy.
- `lfv-ui-link`, `lfv-ui-field`: link and form styles.

Components are **opt-in** so existing archive, awards, game, and admin screens can
be migrated and visually verified section by section.

## Migration order

1. Consolidate tokens and remove competing declarations.
2. Use shared Jinja components on archive/awards overview pages.
3. Migrate homepage, timeline, profiles, awards, calendars, music, community,
   submissions, and specialized pages, preserving their information hierarchy.
4. Adapt admin UI separately: dense screens retain functional layout but use
   shared brand tokens and accessibility rules.
5. Remove legacy CSS generations only after page-by-page screenshot comparison.

## Required review gate

Check at desktop 1440px, tablet 768/1024px, mobile 390px; test both light and
dark mode. Check headings, contrast, links, forms, keyboard focus, navigation,
pagination, overflow, empty states, and error states. Run application and browser
tests before merging. Do not deploy automatically from a draft design PR.
