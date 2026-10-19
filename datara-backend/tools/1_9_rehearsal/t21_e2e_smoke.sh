#!/usr/bin/env bash
# Offline T21 full-chain checklist. This script never contacts an LLM or datasource.
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PLANNER="$SCRIPT_DIR/rehearsal.py"

printf '%s\n' 'MODE=PLAN_ONLY; no LLM, datasource, SQL, database, or network action will run.'
printf '%s\n' 'CHAIN: natural language → SQL generation → authorized read-only execution → result explanation'
python "$PLANNER" t21-full-chain
printf '%s\n' 'SKIP RULE: if any canonical LLM_PROVIDER/LLM_BASE_URL/LLM_MODEL/LLM_API_KEY is missing, planner reports SKIP; no request is attempted.'
printf '%s\n' 'SAFE_STOP: do not infer a pass from datasource connectivity or unit tests.'
