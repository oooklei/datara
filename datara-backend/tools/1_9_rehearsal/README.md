# 1.9 rehearsal preparation (offline planner only)

This directory is a preparation aid for T44. Its scripts **never connect to or
modify 1.9**. They do not open sockets, load `.env`, run SQL, publish Redis
messages, contact an LLM, or perform remote actions. The shell wrappers invoke
only the local Python planner. Environment variables only affect whether a
checklist item says `SKIP` or is ready for a separately authorized operator;
they never enable execution in these scripts.

## Safe execution order

1. Obtain explicit supervisor authorization for the 1.9 rehearsal host and, for
   FV-12/FV-13, a disposable schema with a tested backup/restore path. Never use
   `dev_ro` for writes.
2. Resolve the FV-05 formal security-owner signature and FV-10 D8 profile
   threshold decision. Keep either item pending until its owner supplies it.
3. Run the local baseline and archive its raw output before remote work:

   ```powershell
   cd datara-backend
   rtk pytest tests/rebuild/test_r8a_failover_fence.py tests/rebuild/test_r8a_failover.py -q
   rtk pytest tests/ai_copilot/test_adapter_sovereignty.py tests/ai_copilot/test_adapter_default_factory.py -q
   ```

   The current failover tests use in-process fakes; they are preparation
   evidence only and do not satisfy T33's real cross-process acceptance.
4. Use `tools/1_9_rehearsal/t33_failover_rehearsal.sh` to print the
   `t33-two-process`, `t33-worker-idempotency`, and `t33-db-redis-windows`
   run cards in order. The planner does not execute them. Capture separate
   process identities/logs, durable worker side-effect counts, DB intent state,
   Redis stream IDs, and restart/replay outcomes.
5. Use `tools/1_9_rehearsal/fv_field_rehearsal.sh` to print the five real-test
   group run cards (FV-02, FV-04, FV-15, FV-06/FV-12, FV-09/FV-13). Keep the
   `dev_ro` path read-only; FV-12's controlled write path is a separate
   authorization boundary.
6. Run FV-09/FV-13 capacity and rollback checks only in the approved disposable
   schema and only after FV-10 thresholds are adjudicated.
7. Run FV-02 online chain and the `tools/1_9_rehearsal/t21_e2e_smoke.sh`
   full-chain checklist last, after the LLM key and
   `api.siliconflow.cn` network access are explicitly available. If either is
   unavailable, record `SKIP` and retain the existing blocker; do not infer a
   pass from unit tests or datasource connectivity.
8. Have the independent reviewer inspect raw evidence and exact command/output
   locations. FV-15/T33 remains RED until real process, worker, and DB↔Redis
   failure-window evidence is complete.

## Planner

From `datara-backend` (bash is required for the shell wrappers):

```powershell
python tools/1_9_rehearsal/rehearsal.py all
python tools/1_9_rehearsal/rehearsal.py t33-two-process
bash tools/1_9_rehearsal/t33_failover_rehearsal.sh
bash tools/1_9_rehearsal/fv_field_rehearsal.sh
bash tools/1_9_rehearsal/t21_e2e_smoke.sh
```

The planner prints a status, the required evidence action, a command/run
description, and an evidence destination. The shell wrappers invoke only the
planner; it does not execute those descriptions.
Items that need LLM access print an explicit `SKIP` when any canonical
`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, or `LLM_API_KEY` value is absent.
Secrets are never printed.

Each item defines its eventual evidence directory under
`docs/increments/evidence/1_9_rehearsal/`. For each execution, save the exact
command or operator action, raw output file path and line/record locator,
timestamp, environment identity (without secrets), and verdict. Keep the raw
output outside this planner until the separately authorized execution occurs.

## Evidence scope anchors

- T33/FV-15: `docs/increments/2026-10-19-监督线裁定-FV-01~17权威清单重建.md` §3 FV-15,
  §4 (required 1.9 tests); S94/S98 in `docs/handoff/STATE.md` (in-process
  acceptance is closed; real cross-process and DB↔Redis windows remain remote).
- Five FV real-test groups: FV-02, FV-04, FV-15, FV-06/FV-12, and FV-09/FV-13
  per the same document §4. FV-05 sign-off and FV-10 thresholds are owner
  decisions/prerequisites, not silently inferred test results.
- T21: `docs/increments/evidence/2026-10-19-T5-final-green.md`; the datasource
  path and 10 sovereignty unit tests passed, while live SQL generation failed
  with a sanitized `VannaAdapterError` after provider connection failure. No
  business query or result explanation was reached.
- Local T33 test anchors:
  `datara-backend/tests/rebuild/test_r8a_failover_fence.py` and
  `datara-backend/tests/rebuild/test_r8a_failover.py`; they use a fake Redis and
  in-process threads, so they are not remote acceptance evidence.

No script in this directory uses `aoci_*`, accesses the mailbox, or pushes
changes.
