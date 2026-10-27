# FE-MERGE-B4 review-fix2
- Status: DONE.
- Tag project switch synchronously clears assets and selection; loading disables project-scoped write controls and handlers.
- Failed AssetMap summaries remain unknown (`—`), are not cached, and retry on the next category activation.
- AssetMap metric and standard links preserve `projectId` query.
- Lineage project switch immediately advances `lineageSeq`, clears graph/error/selection, and suppresses stale success or failure.
- RED: 3 files failed; 4 failed / 19 passed.
- GREEN targeted: 3 files / 23 tests.
- Full Vitest: 96 files / 816 tests.
- vue-tsc: PASS. Diff check: PASS.
