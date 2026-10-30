"""Static checks for SQL / Python / Shell resource scripts.

Scope: the resource-management edit flow — validate a draft before appending a
new immutable version. Three layers:

1. ``syntax`` — SQL reuses :func:`rebuild.sql_ide.linter.lint_sql` (sqlglot,
   no connection, no execution); Python uses the stdlib ``ast`` parser; Shell
   shells out to ``bash -n`` / ``sh -n``, which parse without executing.
2. ``references`` — cross-resource references are ``${resource.<name>}``
   tokens (all kinds) plus kind-native references: SQL table names (sqlglot),
   Python imports, Shell ``source`` / ``.`` paths. An unknown
   ``${resource.*}`` is an error; unknown tables/imports/sources are warnings
   so a legitimate external dependency is never blocked.
Execution is handled by the selected SSH trial node or dbx SQL gateway.
"""

from __future__ import annotations

import ast
import os
import platform
import re
import shutil
import subprocess
import sys
from typing import Any, Sequence

import sqlglot
from sqlglot import exp

from rebuild.resources.repository import ResourceDomainError
from rebuild.sql_ide.linter import lint_sql

# ``${resource.<name>}`` is the only cross-kind reference syntax.
RESOURCE_REF_RE = re.compile(r"\$\{resource\.([A-Za-z0-9_.\-]+)\}")
SOURCE_LINE_RE = re.compile(r"^\s*(?:source|\.)\s+(\S.*)$")
SH_LINE_RE = re.compile(r"line (\d+)")

DIALECT_ALIASES = {"postgresql": "postgres"}



def _diag(
    code: str,
    message: str,
    *,
    severity: str = "error",
    line: int | None = None,
    column: int | None = None,
    source: str = "syntax",
) -> dict[str, Any]:
    return {
        "source": source,
        "code": code,
        "severity": severity,
        "line": line,
        "column": column,
        "message": message,
    }


def resolve_shell_binary() -> str | None:
    """Return a POSIX shell that can parse (``-n``) and run (``-c``) scripts."""
    override = os.getenv("REBUILD_SCRIPT_SHELL", "").strip()
    if override:
        return override
    for candidate in ("bash", "sh"):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def _known_resource_keys(names: Sequence[str]) -> set[str]:
    """Match both ``etl_job.sql`` and its stem ``etl_job`` (case-insensitive)."""
    keys: set[str] = set()
    for name in names:
        if not isinstance(name, str) or not name:
            continue
        keys.add(name.lower())
        dot = name.rfind(".")
        if dot > 0:
            keys.add(name[:dot].lower())
    return keys


# -- SQL ---------------------------------------------------------------------


def _sql_table_references(content: str, dialect: str, known: set[str]) -> list[dict[str, Any]]:
    dialect_name = DIALECT_ALIASES.get(dialect.strip().lower(), dialect.strip().lower())
    try:
        statements = sqlglot.parse(content, read=dialect_name)
    except Exception:  # noqa: BLE001 — syntax errors are already reported by lint_sql
        return []
    references: list[dict[str, Any]] = []
    seen: set[str] = set()
    for statement in statements:
        if statement is None:
            continue
        for table in statement.find_all(exp.Table):
            name = table.name
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            if name.lower() in known:
                continue
            references.append(
                _diag(
                    "SCRIPT_TABLE_UNKNOWN",
                    f'table "{name}" is not a resource in this project',
                    severity="warning",
                    source="references",
                )
            )
    return references


def _check_sql(content: str, dialect: str, known: set[str]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    result = lint_sql(content, dialect=dialect)
    diagnostics = [dict(item, source="syntax") for item in result["diagnostics"]]
    status = "ok" if result["valid"] else "error"
    references = _sql_table_references(content, dialect, known) if result["valid"] else []
    return status, diagnostics, references


# -- Python ------------------------------------------------------------------


def _python_import_references(tree: ast.AST, known: set[str]) -> list[dict[str, Any]]:
    stdlib = getattr(sys, "stdlib_module_names", frozenset())
    references: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(module: str | None, line: int) -> None:
        if not module:
            return
        top = module.split(".")[0]
        if not top or top in seen:
            return
        seen.add(top)
        if top in stdlib or top.lower() in known:
            return
        references.append(
            _diag(
                "PY_IMPORT_UNRESOLVED",
                f'import "{top}" is neither a stdlib module nor a project resource; '
                "verify the package is installed at runtime",
                severity="warning",
                line=line,
                source="references",
            )
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import resolves inside the script itself
                continue
            add(node.module, node.lineno)
    return references


def _check_python(content: str, known: set[str]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        return (
            "error",
            [
                _diag(
                    "PY_SYNTAX_ERROR",
                    exc.msg or "Python syntax error",
                    line=exc.lineno,
                    column=exc.offset,
                )
            ],
            [],
        )
    except ValueError as exc:
        return "error", [_diag("PY_SYNTAX_ERROR", str(exc) or "Python source is invalid")], []
    return "ok", [], _python_import_references(tree, known)


# -- Shell -------------------------------------------------------------------


def _shell_references(content: str, known: set[str]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for index, line in enumerate(content.splitlines(), start=1):
        match = SOURCE_LINE_RE.match(line)
        if not match:
            continue
        target = match.group(1).strip().strip("\"'")
        base = os.path.basename(target).lower()
        stem = base[: base.rfind(".")] if base.rfind(".") > 0 else base
        if base in known or stem in known:
            continue
        references.append(
            _diag(
                "SH_SOURCE_UNKNOWN",
                f'source target "{target}" is not a project resource',
                severity="warning",
                line=index,
                source="references",
            )
        )
    return references


def _check_shell(content: str, known: set[str]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    references = _shell_references(content, known)
    shell = resolve_shell_binary()
    if shell is None:
        return (
            "skipped",
            [
                _diag(
                    "SH_CHECKER_UNAVAILABLE",
                    "Neither bash nor sh is available to parse the script; shell syntax was not checked",
                    severity="warning",
                )
            ],
            references,
        )
    try:
        completed = subprocess.run(
            [shell, "-n"], input=content, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return (
            "skipped",
            [_diag("SH_CHECKER_UNAVAILABLE", f"shell syntax check could not run: {exc}", severity="warning")],
            references,
        )
    if completed.returncode == 0:
        return "ok", [], references
    stderr = (completed.stderr or "").strip()
    match = SH_LINE_RE.search(stderr)
    message = stderr.splitlines()[-1] if stderr else "Shell syntax error"
    return (
        "error",
        [_diag("SH_SYNTAX_ERROR", message, line=int(match.group(1)) if match else None)],
        references,
    )


# -- explicit cross-resource references --------------------------------------


def _explicit_resource_references(content: str, known: set[str]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for index, line in enumerate(content.splitlines(), start=1):
        for match in RESOURCE_REF_RE.finditer(line):
            name = match.group(1)
            if name.lower() in known:
                continue
            references.append(
                _diag(
                    "SCRIPT_RESOURCE_REF_UNKNOWN",
                    f"${{resource.{name}}} is not a resource in this project",
                    line=index,
                    column=match.start() + 1,
                    source="references",
                )
            )
    return references


# -- entry point -------------------------------------------------------------


def check_script(
    kind: str,
    content: str,
    *,
    known_resources: Sequence[str] = (),
    dialect: str = "mysql",
    execute: bool = False,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Check one draft without executing it in the API process."""
    if execute:
        raise ResourceDomainError("RES_EXECUTION_REQUIRES_TARGET", "choose an SSH trial node or dbx connection")
    if kind not in ("sql", "python", "shell"):
        raise ResourceDomainError("RES_KIND_UNKNOWN", f"kind must be one of ['sql', 'python', 'shell']")
    if not isinstance(content, str) or not content.strip():
        return {
            "kind": kind,
            "syntax": {"status": "error", "diagnostics": [_diag("SCRIPT_EMPTY", "script content is required")]},
            "references": [],
            "run": None,
        }

    known = _known_resource_keys(known_resources)
    if kind == "sql":
        status, diagnostics, native_references = _check_sql(content, dialect or "mysql", known)
    elif kind == "python":
        status, diagnostics, native_references = _check_python(content, known)
    else:
        status, diagnostics, native_references = _check_shell(content, known)

    return {
        "kind": kind,
        "syntax": {"status": status, "diagnostics": diagnostics},
        "references": _explicit_resource_references(content, known) + native_references,
        "run": None,
    }


# -- runtime environment -----------------------------------------------------

MAX_LISTED_PACKAGES = 200

_ENVIRONMENT_CACHE: dict[str, Any] | None = None


def _python_environment() -> dict[str, Any]:
    try:
        import importlib.metadata as metadata

        packages = sorted(
            {
                dist.metadata["Name"]
                for dist in metadata.distributions()
                if dist.metadata and dist.metadata["Name"]
            }
        )
    except Exception:  # noqa: BLE001 — package metadata is best-effort
        packages = []
    return {
        "available": True,
        "version": platform.python_version(),
        "executable": sys.executable,
        "package_count": len(packages),
        "packages": packages[:MAX_LISTED_PACKAGES],
    }


def _shell_environment() -> dict[str, Any]:
    shell = resolve_shell_binary()
    if shell is None:
        return {"available": False, "path": None, "kind": None, "version": None}
    version: str | None = None
    try:
        completed = subprocess.run(
            [shell, "--version"], capture_output=True, text=True, timeout=5, check=False
        )
        first = (completed.stdout or completed.stderr or "").strip().splitlines()
        if first:
            version = first[0]
    except (OSError, subprocess.SubprocessError):
        version = None
    return {
        "available": True,
        "path": shell,
        "kind": os.path.basename(shell).lower(),
        "version": version,
    }


def _container_marker() -> bool:
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()
    except OSError:
        return False
    return any(token in content for token in ("docker", "kubepods", "containerd"))


def describe_environment() -> dict[str, Any]:
    """Describe the local static checker; trial runtime comes from the selected SSH node."""
    global _ENVIRONMENT_CACHE
    if _ENVIRONMENT_CACHE is None:
        _ENVIRONMENT_CACHE = {
            "run_location": {
                "scope": "selected_ssh_node",
                "label": "试运行位置由所选 SSH 节点决定",
                "hostname": "",
                "platform": "",
                "containerized": False,
                "workdir": "所选主机的临时目录",
            },
            "python": _python_environment(),
            "shell": _shell_environment(),
            "database": None,
            "database_note": "SQL 试运行需选择 dbx 连接。",
            "output": {"channel": "run_log", "label": "弹窗下方「试运行日志」区域"},
        }
    return _ENVIRONMENT_CACHE
