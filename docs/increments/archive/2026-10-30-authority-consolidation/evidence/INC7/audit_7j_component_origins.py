"""7J component-origin audit (read-only evidence generator).

This script reads the exported catalog only.  It never connects to a database and
never mutates component state.  Live ``published`` state therefore remains an
explicitly unknown field when no production database export is supplied.
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
CATALOG = ROOT / "datara-backend/common/dag_catalog.json"
OUTPUT = Path(__file__).with_name("2026-10-21-7J-组件出处与引用量调查.csv")

FORMAL_ORIGINS = {
    **{name: "DolphinScheduler/DAG control semantics; authority design §5A.3" for name in (
        "start", "end", "conditions", "switch", "fork", "join", "merge", "delay", "dependent", "loop"
    )},
    "sql": "DBX SQL IDE + authority design §5A.3 (C11)",
    "shell": "DolphinScheduler Shell task + authority design §5A.3 (C12)",
    "python": "DolphinScheduler Python task + authority design §5A.3 (C13)",
    "ssh": "DolphinScheduler SSH task + authority design (C14)",
    "procedure": "DolphinScheduler procedure task + authority design (C15)",
    "http": "DolphinScheduler HTTP task + authority design (C16)",
    "sync": "DataX synchronization execution + authority design (C17)",
    "stream_input": "Flink stream model + authority design (C18)",
    "stream_fuse": "Flink stream model + Datara extension (C19)",
    "stream_output": "Flink stream model + authority design (C20)",
    "variable": "Datara authority design extension (C21)",
    "file": "Datara authority design meeting item ⑫ (C22)",
    "file_sync": "DataX file synchronization execution (C24)",
    "assert": "Datara authority design data validation (C25)",
    "notify": "Datara authority design notification (C26)",
    "src_base_orch": "Datara synchronization template design (C29)",
    "tgt_base_orch": "Datara synchronization template design (C30)",
    "file_sync_orch": "Datara synchronization template design (C31)",
    "field_map": "Datara synchronization template design (C34)",
    "condition_set": "Datara synchronization template design (C35)",
    "field_map_union": "Datara synchronization template design (C36)",
    "endpoint_select": "Datara synchronization template design (C37)",
    "smoke": "Implementation/test helper (C38); no product-origin evidence found",
    "page_board": "Datara authority design page component extension",
}


def production_reference_index(component_types: set[str]) -> dict[str, list[str]]:
    """Return production-code files containing each exact type token.

    Definitions, tests, generated catalog, docs and build output are excluded so
    the count is a conservative static usage signal, not a live workflow count.
    """
    roots = (ROOT / "datara-backend", ROOT / "datara-web", ROOT / "datara-newweb")
    excluded_parts = {"tests", "__tests__", "node_modules", "dist", "__pycache__"}
    excluded_names = {"dag_catalog.json", "dag.ts"}
    patterns = {
        name: re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")
        for name in component_types
    }
    hits: dict[str, list[str]] = {name: [] for name in component_types}
    for base in roots:
        if not base.exists():
            continue
        for directory, dirs, files in os.walk(base):
            dirs[:] = [name for name in dirs if name not in excluded_parts]
            for filename in files:
                path = Path(directory) / filename
                if filename in excluded_names or path.suffix.lower() not in {".py", ".ts", ".vue", ".js", ".json"}:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                rel = path.relative_to(ROOT).as_posix()
                for name, pattern in patterns.items():
                    if pattern.search(text):
                        hits[name].append(rel)
    return {name: sorted(set(paths)) for name, paths in hits.items()}


def origin_for(item: dict) -> str:
    component_type = item["type"]
    if component_type in FORMAL_ORIGINS:
        return FORMAL_ORIGINS[component_type]
    profile = item.get("profile")
    if profile == "etl":
        return "Legacy ETL palette; archive says ETL operators were cancelled; no current authority-design source found"
    if profile == "stream":
        return "Legacy stream palette/Flink-inspired; no per-component current authority-design source found"
    if profile == "topo":
        return "Legacy topology canvas device; non-DAG and no component-spec product source found"
    if component_type == "reroute":
        return "Legacy DAG convenience node; no I0-I11/component code source found"
    if component_type == "demo_pipeline":
        return "Demo template; no production component source"
    return "Unknown; requires supervisor/product evidence"


def recommendation(item: dict, origin: str) -> str:
    if origin.startswith(("DolphinScheduler", "DBX", "DataX", "Flink", "Datara authority", "Datara synchronization")):
        return "retain candidate; verify published spec and workflow-type filtering"
    if item.get("runtimeOnly"):
        return "retain runtime-only; exclude from palette"
    if item.get("type") == "smoke":
        return "supervisor decision: likely test-only; verify zero live references before any offline action"
    if item.get("type") == "demo_pipeline":
        return "supervisor decision: demo/template isolation; verify zero live references"
    if item.get("profile") == "topo":
        return "separate from component-spec governance; do not publish as DAG component"
    return "supervisor decision required; no removal until live DB references and product origin are resolved"


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    reference_index = production_reference_index({item["type"] for item in catalog["components"]})
    rows = []
    for ordinal, item in enumerate(catalog["components"], 1):
        refs = reference_index[item["type"]]
        origin = origin_for(item)
        rows.append({
            "ordinal": ordinal,
            "type": item["type"],
            "code": item.get("code") or "",
            "label": item.get("label") or "",
            "profile": item.get("profile") or "",
            "catalog_palette_visible": item.get("paletteVisible"),
            "catalog_runtime_only": item.get("runtimeOnly"),
            "live_published_state": "UNKNOWN (no reachable production DB/export)",
            "origin_evidence": origin,
            "static_production_reference_file_count": len(refs),
            "static_production_reference_files": "; ".join(refs),
            "recommended_disposition": recommendation(item, origin),
            "supervisor_decision": "PENDING",
        })
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"catalog_rows={len(rows)} output={OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
