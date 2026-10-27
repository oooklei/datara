# AUTH-UI-03 verification

- Verified at: 2026-10-26 00:35:46 +08:00
- Scope: `AppShell.vue`, `http.ts`, `authApi.ts`, `LoginView.vue`, and their contract tests only.
- AOCI: not loaded or invoked.

## Automated checks

- `npm test -- --reporter=dot`: PASS — 91 test files, 762 tests.
- `npx vue-tsc -b --pretty false`: PASS — exit 0, no diagnostics.
- `npm run build`: PASS — 1,763 modules transformed; production bundle emitted.
- Production artifact fixture scan: PASS — none of `runtime-token`, `tok-login-1`, `secret-1`, `validation-token`, `tok-out-1`, or `tok-out-2` found in `dist`.
- Auth source URL/storage write scan: PASS — no `URLSearchParams`, token/key query assignment, `localStorage.setItem`, or `sessionStorage.setItem` in the four production files.
- `git diff --check` for the eight scoped files: PASS.

## Contract evidence

- Login view contains no form or input surface for username, password, validation key, or token.
- Runtime token injection is consumed once into module memory and removed from the global injection slot.
- `setToken` and `clearToken` remove legacy local/session storage residue.
- Authenticated shell exposes a visible logout button; logout attempts server revocation, always clears local memory, and routes to `/login`.
- At narrow widths the shell becomes one column, clips topbar overflow, constrains horizontal scrolling to main/navigation regions, and hides the project-name label below 480px while preserving exit/logout actions.

## Non-blocking existing warnings

- Full Vitest emitted one unrelated `<tr>` nesting warning and three pre-existing unmatched-empty-route warnings; all tests passed.
- Vite emitted the existing chunk-size warning (>500 kB); build passed.
