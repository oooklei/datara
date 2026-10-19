#!/usr/bin/env bash
# Offline FV real-test checklist. This script never runs the checks.
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PLANNER="$SCRIPT_DIR/rehearsal.py"

printf '%s\n' 'MODE=PLAN_ONLY; no 1.9, datasource, database, Redis, write, or network action will run.'
printf '%s\n' 'STEP 1/5: FV-02 online chain readiness (requires live LLM and datasource authorization)'
python "$PLANNER" fv02-online-chain
printf '%s\n' 'STEP 2/5: FV-04 live sovereignty assertions'
python "$PLANNER" fv04-live-sovereignty
printf '%s\n' 'STEP 3/5: FV-15 cross-process fencing and DB/Redis windows'
"$SCRIPT_DIR/t33_failover_rehearsal.sh"
printf '%s\n' 'STEP 4/5: FV-06 read-only target checks and separately gated FV-12 controlled write path'
python "$PLANNER" fv06-12-target-db
printf '%s\n' 'STEP 5/5: FV-09 capacity and FV-13 rollback in an authorized disposable schema'
python "$PLANNER" fv09-13-capacity-rollback
printf '%s\n' 'SAFE_STOP: planner output is not FV evidence; owner decisions and operator authorization remain required.'
