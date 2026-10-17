# Codex P1-6: BE A1 TDD timeline evidence

Date: 2026-10-17 (Asia/Shanghai). Scope: Git-anchored RED → GREEN timeline for `datara-backend/ai_copilot/` and `datara-backend/tests/ai_copilot/`.

## Evidence found

- The current canonical worktree reports `ai_copilot/__init__.py`, `adapter.py`, `config.py`, `tests/ai_copilot/__init__.py`, `test_adapter_sovereignty.py`, and `test_skeleton.py` as untracked; the AI dependency input/lock and `pyproject.toml` change are also uncommitted.
- `git log --all --oneline --` for the AI source and test paths returns no commit anchors. Consequently there is no Git-verifiable RED commit followed by a GREEN implementation commit.
- Current test result is green (10 targeted sovereignty tests and 12 total AI package tests passed), but a green snapshot alone does not establish the required TDD sequence.

## Conclusion

**A1 timeline: NOT VERIFIED / P1-6 closeout gap.** File timestamps and a later passing test run cannot substitute for source-bound commit evidence. The existing dirty/untracked implementation has unknown original authorship; do not stage, rewrite, or delete it as part of producing this report. A future clean TDD sequence must preserve distinct failing-test and passing-implementation Git anchors with pathspec-scoped commits.

## Post-hoc Git anchors (2026-10-17)

Supervisor #157 authorized promotion of the previously untracked source/test assets. The following commits establish supplemental provenance anchors; they do **not** establish a historical RED-to-GREEN sequence:

- `1b73388` — dependency input/lock and vendored Vanna wheel.
- `57dc73b` — ai_copilot source, tests, and Chroma runtime directory markers.
- `742bfd9` — optional dependency metadata and Docker lock installation (`pyproject.toml`, `Dockerfile`), plus the supervisor-authorized `docker-compose.yml` configuration batch. The compose diff also contains runtime credential hardening, the rebuild API service, and web verification port changes; those are not represented as AI-only changes.
- After promotion, `python -m pytest -q tests/ai_copilot` from `datara-backend/` → **12 passed in 0.20s**.

**Updated conclusion:** the source/test Git anchors and post-promotion GREEN run are now recorded as supplemental evidence. Historical RED commit remains unavailable, so A1 is **NOT VERIFIED as a TDD chronology**; no RED history is fabricated. Lock install and actual persistent Chroma isolation evidence are documented separately. Target Python 3.11 container build remains unverified because Docker is unavailable.
