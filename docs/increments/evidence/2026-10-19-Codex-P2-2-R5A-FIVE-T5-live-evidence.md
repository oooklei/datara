# P2-2-R5A-FIVE T5 live evidence

## Live provider run

Command (run from `datara-backend/`): `rtk python -c "from ai_copilot.adapter import AdapterContext,CopilotAdapter,DATA_ROOT; events=[]; c1=AdapterContext(user_id=7,project_id=11); c2=AdapterContext(user_id=8,project_id=11); adapter=CopilotAdapter(audit_hook=events.append); sql=adapter.generate_sql('Return exactly one read-only SQL statement that selects the constant 1, with no table dependency.',c1); v1=adapter._clients[c1]; v2=adapter._client(c2); p1=CopilotAdapter._scoped_chroma_path(c1); p2=CopilotAdapter._scoped_chroma_path(c2); assert sql.strip().rstrip(';').upper()=='SELECT 1'; assert not hasattr(v1.client,'api_key'); assert v1 is not v2; assert p1 != p2 and p1.is_relative_to(DATA_ROOT.resolve()) and p2.is_relative_to(DATA_ROOT.resolve()); assert [(e.action,e.outcome) for e in events]==[('generate_sql','started'),('generate_sql','succeeded')]; print('LIVE_GENERATE_SQL=',sql); print('ASSERTIONS=generated_sql_only:PASS; vanna_has_no_api_key_attribute:PASS; user_project_partition:PASS; chroma_path_under_datara_data:PASS; audit_started_succeeded:PASS'); print('CHROMA_PATH_EXISTS=',p1.exists())"`

Output:

```text
Using model deepseek-ai/DeepSeek-V4.1-Flash for 258.5 tokens (approx)
LIVE_GENERATE_SQL= SELECT 1;
ASSERTIONS=generated_sql_only:PASS; vanna_has_no_api_key_attribute:PASS; user_project_partition:PASS; chroma_path_under_datara_data:PASS; audit_started_succeeded:PASS
CHROMA_PATH_EXISTS= True
```

The `.env` key was loaded only through `AIConfig`; no key value was printed, returned, or written. TDD regression evidence for the pre-fix key ownership defect is in `2026-10-19-P2-2-R5A-FIVE-T5-red.txt`; post-fix module tests are in `2026-10-19-P2-2-R5A-FIVE-T5-green.txt`.

## Sovereignty assertions

1. **Vanna key ownership: PASS (instance boundary).** Before the fix, `vanna.client.api_key` directly exposed the configured key; after the fix, Vanna retains a credential-free proxy and the adapter supplies its OpenAI client only through a per-call `ContextVar`.
2. **Authorized read-only execution: NOT VERIFIED.** Vanna's own `run_sql` remains disabled and tested; this run did not execute the generated SQL against a real Datara-authorized datasource, so the full generation-to-authorized-execution-to-explanation chain is incomplete.
3. **User/project isolation: PASS (partition boundary).** Separate user contexts produced distinct Vanna clients and distinct scoped Chroma paths; the existing sovereignty tests also verify path separation across users and projects.
4. **Datara Chroma location and audit: PASS.** The scoped path is under `datara-backend/data/ai_copilot/chromadb`, exists after the real call, and the real call emitted `generate_sql` started/succeeded audit events.

This is partial R8-V evidence, not a full-chain acceptance or GREEN declaration. No credential was included in this file.
