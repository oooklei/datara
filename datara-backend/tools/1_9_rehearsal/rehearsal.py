#!/usr/bin/env python3
"""Offline rehearsal planner for the authorized 1.9 evidence run.

This module is deliberately non-operational: it never opens sockets, invokes
subprocesses, loads credentials from files, or runs a database/Redis/LLM check.
It prints a gated checklist for a separately authorized operator to execute.
"""

from __future__ import annotations

import argparse
import os
import sys


ITEMS: dict[str, dict[str, object]] = {
    "t33-two-process": {
        "title": "T33 / FV-15: two-process fencing",
        "requires": ("DATARA_REHEARSAL_19_AUTHORIZED", "DATARA_REHEARSAL_DB_URL", "DATARA_REHEARSAL_REDIS_URL"),
        "check": "Start two isolated master processes; claim a newer fence in process B; prove process A's stale token cannot dispatch; retain both process logs and the single accepted dispatch id.",
        "command": "operator-run: two isolated master processes against the approved rehearsal DB/Redis; no command is executed by this planner",
        "evidence": "docs/increments/evidence/1_9_rehearsal/T33-two-process-fencing/",
    },
    "t33-worker-idempotency": {
        "title": "T33 / FV-15: worker execution idempotency",
        "requires": ("DATARA_REHEARSAL_19_AUTHORIZED", "DATARA_REHEARSAL_DB_URL", "DATARA_REHEARSAL_REDIS_URL"),
        "check": "Deliver the same run/task/attempt twice to separate worker processes; prove one business side effect and a durable duplicate acknowledgement; also prove changed payload under the same key is rejected.",
        "command": "operator-run: duplicate the same attempt message across isolated workers and inspect durable side-effect/idempotency records",
        "evidence": "docs/increments/evidence/1_9_rehearsal/T33-worker-idempotency/",
    },
    "t33-db-redis-windows": {
        "title": "T33 / FV-15: DB↔Redis failure windows",
        "requires": ("DATARA_REHEARSAL_19_AUTHORIZED", "DATARA_REHEARSAL_DB_URL", "DATARA_REHEARSAL_REDIS_URL"),
        "check": "Exercise lease expiry and process restart; inject termination at DB intent commit, Redis enqueue, and enqueue acknowledgement boundaries; restart/replay and prove no lost intent, duplicate side effect, or stale-leader dispatch.",
        "command": "operator-run: expire the lease, restart isolated processes, inject controlled termination at each named DB↔Redis boundary, then reconcile DB intent, stream entry, and worker effect",
        "evidence": "docs/increments/evidence/1_9_rehearsal/T33-db-redis-failure-windows/",
    },
    "fv02-online-chain": {
        "title": "FV-02: online T5 chain",
        "requires": ("DATARA_REHEARSAL_19_AUTHORIZED", "DATARA_T5_DS_HOST", "DATARA_T5_DS_PORT", "DATARA_T5_DS_USER", "DATARA_T5_DS_PWD", "DATARA_T5_DS_DB", "LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"),
        "check": "Natural language → live generate_sql → read-only ec_retail execution → result explanation, with per-stage audit evidence and no credential/SQL leakage.",
        "command": "operator-run: approved T5 online smoke with one scoped aggregate question; use dev_ro and the read-only session contract",
        "evidence": "docs/increments/evidence/1_9_rehearsal/FV-02-online-chain/",
        "llm": True,
    },
    "fv04-live-sovereignty": {
        "title": "FV-04: live sovereignty assertions",
        "requires": ("DATARA_REHEARSAL_19_AUTHORIZED", "DATARA_T5_DS_HOST", "DATARA_T5_DS_PORT", "DATARA_T5_DS_USER", "DATARA_T5_DS_PWD", "DATARA_T5_DS_DB"),
        "check": "Reconfirm configured LLM key is not retained by Vanna; SQL execution uses only the read-only channel; user/project context is isolated; Chroma storage is contained and audited. Pair live evidence with the existing 10-test unit record.",
        "command": "operator-run: T5 live assertion checklist; local anchor: rtk pytest tests/ai_copilot/test_adapter_sovereignty.py tests/ai_copilot/test_adapter_default_factory.py -q",
        "evidence": "docs/increments/evidence/1_9_rehearsal/FV-04-live-sovereignty/",
    },
    "fv06-12-target-db": {
        "title": "FV-06/FV-12: target DB gates and controlled write path",
        "requires": ("DATARA_REHEARSAL_19_AUTHORIZED", "DATARA_T5_DS_HOST", "DATARA_T5_DS_PORT", "DATARA_T5_DS_USER", "DATARA_T5_DS_PWD", "DATARA_T5_DS_DB"),
        "check": "Verify dev_ro's scoped SELECT/SHOW VIEW grants and one harmless denied-write proof; separately exercise FV-12 only in an explicitly approved disposable governance schema with backup, confirm phrase, audit row, and compensation evidence. Never issue a write as dev_ro.",
        "command": "operator-run: read-only permission check; FV-12 write-path requires separate disposable-schema authorization and must not use dev_ro",
        "evidence": "docs/increments/evidence/1_9_rehearsal/FV-06-FV-12-target-db/",
    },
    "fv09-13-capacity-rollback": {
        "title": "FV-09/FV-13: snapshot/export capacity and DDL rollback",
        "requires": ("DATARA_REHEARSAL_19_AUTHORIZED", "DATARA_REHEARSAL_DB_URL"),
        "check": "Measure bounded large-snapshot/export behavior against FV-10 approved thresholds; prove fail-closed row/byte caps, TTL/cleanup, cancellation and partial-file cleanup; inject a controlled disposable-schema DDL failure and verify backup/compensation/rolled-back state.",
        "command": "operator-run: capacity profile and isolated DDL rollback rehearsal; do not use a production schema",
        "evidence": "docs/increments/evidence/1_9_rehearsal/FV-09-FV-13-capacity-rollback/",
    },
    "t21-full-chain": {
        "title": "T21: T5 full-chain smoke",
        "requires": ("DATARA_REHEARSAL_T21_AUTHORIZED", "DATARA_T5_DS_HOST", "DATARA_T5_DS_PORT", "DATARA_T5_DS_USER", "DATARA_T5_DS_PWD", "DATARA_T5_DS_DB", "LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"),
        "check": "Run the already-scoped T21 question through live SQL generation, dev_ro execution, and result explanation; retain sanitized stage events. No query is issued if generation fails.",
        "command": "operator-run: T21 scoped T5 full-chain smoke; local anchor: rtk pytest tests/ai_copilot/test_adapter_sovereignty.py tests/ai_copilot/test_adapter_default_factory.py -q",
        "evidence": "docs/increments/evidence/1_9_rehearsal/T21-full-chain/",
        "llm": True,
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("item", choices=(*ITEMS, "all"), nargs="?", default="all")
    args = parser.parse_args()
    selected = ITEMS.items() if args.item == "all" else ((args.item, ITEMS[args.item]),)

    print("MODE=PLAN_ONLY; remote/network/database/Redis/LLM actions are hard-disabled")
    print("This tool does not read .env, reveal values, or execute the displayed checks.")
    for key, item in selected:
        missing = [name for name in item["requires"] if not os.environ.get(name)]
        if missing:
            status = "SKIP: missing explicit environment/authorization: " + ", ".join(missing)
        else:
            status = "READY_FOR_SEPARATELY_AUTHORIZED_OPERATOR; execution remains disabled here"
        if item.get("llm") and any(not os.environ.get(name) for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")):
            status = "SKIP: canonical LLM config is incomplete; no LLM request will be attempted"
        print(f"\n[{key}] {item['title']}\nSTATUS: {status}")
        print(f"CHECK: {item['check']}")
        print(f"COMMAND: {item['command']}")
        print(f"EVIDENCE: {item['evidence']}")

    print("\nSAFE_STOP: no remote side effects were attempted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
