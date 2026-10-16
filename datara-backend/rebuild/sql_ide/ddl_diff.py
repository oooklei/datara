"""Textual definition diffing for non-executable DDL previews."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff


@dataclass(frozen=True)
class DdlDefinitionDiff:
    changed: bool
    added_lines: int
    removed_lines: int
    unified_diff: str


def build_definition_diff(current_definition: str | None, expected_definition: str) -> DdlDefinitionDiff:
    current = current_definition or ""
    old_lines = current.splitlines(keepends=True)
    new_lines = expected_definition.splitlines(keepends=True)
    delta = tuple(
        unified_diff(
            old_lines,
            new_lines,
            fromfile="current-definition",
            tofile="expected-definition",
        )
    )
    return DdlDefinitionDiff(
        changed=current != expected_definition,
        added_lines=sum(1 for line in delta if line.startswith("+") and not line.startswith("+++")),
        removed_lines=sum(1 for line in delta if line.startswith("-") and not line.startswith("---")),
        unified_diff="".join(delta),
    )
