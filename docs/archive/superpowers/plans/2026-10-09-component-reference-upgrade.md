# Component Reference Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a component publisher to migrate selected workflow references through an explicit field-mapping review, with per-workflow optimistic locking and an auditable result.

**Architecture:** The browser derives the breaking field diff from the old and published specs, records a mapping or an explicit no-migration decision per workflow, and sends those decisions with each upgrade target. The backend validates only JSON-safe mapping keys, writes the decision into the graph's `componentRef`, and performs the existing version CAS update independently for each target. Existing targets without a mapping retain their current auto/pin semantics.

**Tech Stack:** Vue 3, TypeScript, Element Plus, FastAPI, Pydantic, SQLAlchemy, Vitest, pytest.

---

### Task 1: Extend the per-reference upgrade contract

**Files:**
- Modify: `datara-backend/api/component_design.py:1289-1376`
- Modify: `datara-backend/tests/test_upgrade_refs.py`
- Modify: `datara-web/src/services/componentApi.ts:433-465`
- Test: `datara-web/src/services/__tests__/componentApi.test.ts`

- [ ] **Step 1: Write backend contract tests for a field mapping and an explicit skip.**

```python
r = client.post(f"/api/v1/components/{COMP}/upgrade-refs", json={"targets": [{
    "wf_id": wf_a, "base_version": 1,
    "field_mapping": {"old_table": "source_table"},
}]})
assert r.status_code == 200
assert _ref_of(db_session, wf_a)["fieldMapping"] == {"old_table": "source_table"}

r = client.post(f"/api/v1/components/{COMP}/upgrade-refs", json={"targets": [{
    "wf_id": wf_b, "base_version": 1, "migration": "skip",
}]})
assert r.status_code == 200
assert _ref_of(db_session, wf_b)["migration"] == "skip"
```

- [ ] **Step 2: Run the new tests in the 1.9 backend container and confirm they fail because the request fields are rejected.**

Run: `python -m pytest tests/test_upgrade_refs.py -q` in `datara-backend:latest` mounted from `/lei/tmp/datara-codex-test/datara-backend`.

Expected: failure at `field_mapping` / `migration` validation or an absent graph decision.

- [ ] **Step 3: Add optional, validated target fields and persist them beside each matching `componentRef`.**

```python
class UpgradeRefTarget(BaseModel):
    wf_id: str
    strategy: Literal["auto", "pin"] = "auto"
    base_version: Optional[int] = None
    field_mapping: dict[str, str] = Field(default_factory=dict)
    migration: Literal["map", "skip"] = "map"

def _safe_field_mapping(value: dict[str, str]) -> dict[str, str]:
    return {key: target for key, target in value.items()
            if isinstance(key, str) and key and isinstance(target, str) and target}
```

For each matching reference, set `fieldMapping` to the sanitized map only when `migration == "map"`; otherwise set `migration` to `"skip"` and remove any stale `fieldMapping`. Include `migration` in the per-target result so the result screen can distinguish skip from failure.

- [ ] **Step 4: Serialize the new client fields without changing existing callers.**

```ts
export interface UpgradeRefTarget {
  wfId: string
  strategy?: 'auto' | 'pin'
  baseVersion?: number
  fieldMapping?: Record<string, string>
  migration?: 'map' | 'skip'
}
```

Map these optional keys to `field_mapping` and `migration` in `upgradeComponentRefs`; omit empty mappings.

- [ ] **Step 5: Run backend and client contract tests in the 1.9 containers.**

Run backend: `python -m pytest tests/test_upgrade_refs.py -q`.

Run frontend: `./node_modules/.bin/vitest run src/services/__tests__/componentApi.test.ts`.

Expected: all selected tests pass.

- [ ] **Step 6: Commit.**

```bash
git add datara-backend/api/component_design.py datara-backend/tests/test_upgrade_refs.py datara-web/src/services/componentApi.ts datara-web/src/services/__tests__/componentApi.test.ts
git commit -m "feat(components): persist upgrade field mappings"
```

### Task 2: Present a three-step review in the upgrade wizard

**Files:**
- Modify: `datara-web/src/components/designer/UpgradeWizard.vue`
- Modify: `datara-web/src/services/componentApi.ts`
- Create: `datara-web/src/components/designer/__tests__/UpgradeWizard.test.ts`

- [ ] **Step 1: Write a wizard test covering selection, mapping, explicit skip, and result grouping.**

```ts
await wrapper.get('[data-testid="upgrade-next"]').trigger('click')
expect(wrapper.text()).toContain('字段变更')
await wrapper.get('[data-testid="migration-skip-wf_a"]').setValue(true)
await wrapper.get('[data-testid="upgrade-submit"]').trigger('click')
expect(upgradeComponentRefs).toHaveBeenCalledWith('comp_demo', [
  expect.objectContaining({ wfId: 'wf_a', migration: 'skip' }),
])
```

- [ ] **Step 2: Run the focused test in the 1.9 frontend container and confirm it fails because no review step exists.**

Run: `./node_modules/.bin/vitest run src/components/designer/__tests__/UpgradeWizard.test.ts`.

Expected: failure locating `upgrade-next`.

- [ ] **Step 3: Replace the one-screen wizard with a compact state machine.**

Use `step: 'select' | 'review' | 'result'`. The select step keeps the existing impacted-workflow table. The review step shows each selected workflow with removed fields, tightened fields, changed control types, and removed outputs from `classifySpecChange`; every removed input has a target field selector plus an explicit “do not migrate” choice. Submit only after each removed input has either a target mapping or a skip decision. The result step separates successful upgrades, intentionally skipped migrations, and failed CAS/API targets.

- [ ] **Step 4: Preserve accessibility and safe defaults.**

Use labelled radio controls, keyboard-reachable buttons, visible disabled explanations, and default a breaking field to `skip` rather than guessing a target. Never submit a mapping for a workflow that is no longer selected.

- [ ] **Step 5: Run focused Vitest plus production build on 1.9.**

Run: `./node_modules/.bin/vitest run src/components/designer/__tests__/UpgradeWizard.test.ts src/services/__tests__/componentApi.test.ts && ./node_modules/.bin/vite build`.

Expected: all tests pass and Vite emits a production bundle.

- [ ] **Step 6: Commit.**

```bash
git add datara-web/src/components/designer/UpgradeWizard.vue datara-web/src/components/designer/__tests__/UpgradeWizard.test.ts datara-web/src/services/componentApi.ts
git commit -m "feat(components): review mappings before reference upgrade"
```

### Task 3: Verify the design-to-runtime upgrade path

**Files:**
- Modify: `datara-backend/tests/test_upgrade_refs.py`
- Modify: `datara-web/src/views/meta/pageDesigner/PageDesignerView.vue` only if result handling requires a user-visible summary
- Test: `datara-web/src/components/designer/__tests__/UpgradeWizard.test.ts`

- [ ] **Step 1: Add an end-to-end backend assertion that upgraded graph references keep both version and migration metadata.**

```python
ref = _ref_of(db_session, wf_a)
assert ref["version"] == 2
assert ref["fieldMapping"] == {"old_table": "source_table"}
```

- [ ] **Step 2: Ensure wizard completion refreshes the component designer state without closing a failed-result report.**

Call the existing `done` event only after the user acknowledges the result. Keep failures visible until close; then reload impacted/reference indicators through the existing catalog refresh path.

- [ ] **Step 3: Run the combined regression suite on 1.9.**

Run backend: `python -m pytest tests/test_upgrade_refs.py tests/test_publish_breaking_change.py -q`.

Run frontend: `./node_modules/.bin/vitest run src/components/designer/__tests__/UpgradeWizard.test.ts src/services/__tests__/componentApi.test.ts && ./node_modules/.bin/vite build`.

Expected: all selected tests pass; only the known chunk-size warning may remain.

- [ ] **Step 4: Commit.**

```bash
git add datara-backend/tests/test_upgrade_refs.py datara-web/src/components/designer/UpgradeWizard.vue datara-web/src/components/designer/__tests__/UpgradeWizard.test.ts datara-web/src/views/meta/pageDesigner/PageDesignerView.vue
git commit -m "test(components): verify mapped reference upgrades"
```
