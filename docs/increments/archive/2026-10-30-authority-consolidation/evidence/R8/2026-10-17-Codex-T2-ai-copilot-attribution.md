# Codex T-2: ai_copilot dirty-item attribution

Date: 2026-10-17 (Asia/Shanghai). Scope: the #155 instruction to declare authorship for the remaining AI Copilot dirty items; this is an attribution report, not authorization to discard or rewrite them.

## Git state observed

- Modified but uncommitted: `datara-backend/pyproject.toml`, `datara-backend/Dockerfile`.
- Untracked AI sources: `datara-backend/ai_copilot/{__init__.py,adapter.py,config.py}`.
- Untracked tests: `datara-backend/tests/ai_copilot/{__init__.py,test_adapter_sovereignty.py,test_skeleton.py}`.
- Untracked AI support assets: `requirements-ai-copilot.in`, `requirements-ai-copilot.lock`, `data/ai_copilot/chromadb/{.gitignore,.gitkeep}`, `vendor/ai_copilot/README.md`, and `vendor/ai_copilot/wheels/vanna-2.0.2-py3-none-any.whl`.
- `git log --all --oneline --` for the AI source/test/dependency/vendor paths returns no commit anchors. The source/test/dependency assets are not tracked in the current canonical history.

## Attribution declaration

**Original author: unknown / not verifiable from repository evidence.** File timestamps and the fact these files sit in the Codex-assigned domain do not prove who authored the bytes. This Codex turn did not create or modify any of these assets; it ran the existing tests and inspected their state. I accept responsibility for the current verification and safe continuation, but do not retroactively claim original authorship.

## T-2 disposition

Preserve the files in place. Do not stage, delete, overwrite, or move them until the original author or an authoritative source supplies a verifiable attribution/ownership decision. This evidence does not touch adjacent `docker-compose.yml` state and does not authorize cleanup of any worktree or branch.
