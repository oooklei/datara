# FE-MERGE-B3 local verification

- RED: `red-vitest.log` — 2 expected assertion failures (missing B3 assets; `meta` not yet wired to `GovernanceHubView`).
- Targeted GREEN: `targeted-vitest.log` — 9 test files, 42 tests passed.
- Full Vitest: `full-vitest.log` — 96 test files, 797 tests passed.
- Vue TypeScript: `vue-tsc.log` — `vue-tsc --noEmit` exited 0.
- Diff checks: `git-diff-check.log` clean; `asset-diff-check.log` confirms all 11 imported assets are source-equal after newline normalization.
- Legacy/demo scan: no `services/*` imports outside `services/rebuild/**`, mock/demo datasets, localhost endpoints, port 8000, or `LEGACY_BASE` in the imported assets.
- Scope: no D-drive write, stash, commit, or AOCI command; no remote deployment/E2E.
