# T14 SQL IDE variable adapter recheck

Scope: ${scope.name} expansion using the R2 VariableContext authority; missing, malformed/unclosed, and cyclic references fail closed.

Command (from `datara-backend`):
`rtk pytest tests/sql_ide/test_variables.py -q`

Output locator: Codex exec result, 2026-10-19 turn continuation after assignment `8e4f2a91`; exit code 0; summarized output: `Pytest: 6 passed`.

This is a takeover recheck of the existing implementation and test file; no historical RED artifact was available in this workspace, so this evidence does not claim a RED run.
