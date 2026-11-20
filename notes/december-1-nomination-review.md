# December 1 nomination review — prepared November 20, 2026

This branch is for review; merging main triggers production deployment and needs owner approval.

- Default exclusive cutoff: December 1, 2026 00:00 America/New_York (05:00 UTC). Accept submissions through the entire November 30 11:59 PM minute.
- Before release, inspect DCA_2026_NOMINATIONS_CLOSE_AT in Render. A nonempty override wins over the code default and must agree with the intended deadline. Public schedule text uses the effective configured deadline.
- Keep provisional standings visible. Do not merge approval-only publication PR #118.
- After closing, review nominees and reasons in the existing admin queue. Missing reasons are review items, not automatic disqualifications. Verify activity during November 2025–November 2026, aliases/duplicates, category eligibility and supporting evidence.
- Review write-in thresholds before manually confirming qualified categories. The existing confirmation endpoint requires nominations to be closed.
- Finalists and final voting require a separate owner decision. This change does not automatically approve nominees, select finalists, start voting or send email.
- Before any structural database changes, verify a backup and restoration procedure. Production health, environment overrides, permissions and restoration have not been verified by these local tests.

Stabilization changes adapted from PR #116 retain newer verification/follow-up fixtures, run the full suite in CI, remove the tracked local SQLite artifact, and reject tracked databases. No production database operation is included.
