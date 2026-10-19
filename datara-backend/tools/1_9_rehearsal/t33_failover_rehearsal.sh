#!/usr/bin/env bash
# Offline T33/FV-15 rehearsal checklist. This script never runs the checks.
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PLANNER="$SCRIPT_DIR/rehearsal.py"

printf '%s\n' 'MODE=PLAN_ONLY; no 1.9, database, Redis, worker, or network action will run.'
printf '%s\n' 'STEP 1/3: independent master processes and stale fence_token rejection'
python "$PLANNER" t33-two-process
printf '%s\n' 'STEP 2/3: duplicate dispatch to independent workers; verify one durable effect'
python "$PLANNER" t33-worker-idempotency
printf '%s\n' 'STEP 3/3: DB intent / Redis enqueue / acknowledgement crash windows, lease expiry, restart and replay'
python "$PLANNER" t33-db-redis-windows
printf '%s\n' 'SAFE_STOP: planner output is not rehearsal evidence; separately authorized operator execution is required.'
