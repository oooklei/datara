import type { CompletionContext, CompletionResult } from "@codemirror/autocomplete";
import { externalVariableSnapshot, type ExternalVariableEntry } from "./externalVariables";

// Datara variables are delivered by the host page over the `datara:variables`
// postMessage bridge (see composables/useExternalVariableBridge.ts) and are
// referenced in SQL with the shell placeholder syntax `${scope.name}`. This
// completion source is deliberately independent from the SQL metadata
// completion: it only reacts to a `$` (optionally followed by `{` and a partial
// `scope.name`) immediately before the cursor.

const VARIABLE_PREFIX_RE = /\$(\{?)([\p{L}_][\p{L}\p{N}_]*(?:\.[\p{L}_][\p{L}\p{N}_]*)*\.?)?$/u;
const LOOKBEHIND_CHARS = 200;
const MAX_DETAIL_CHARS = 40;

function variableKey(entry: ExternalVariableEntry): string {
  return `${entry.scope}.${entry.name}`;
}

function detailFor(entry: ExternalVariableEntry): string {
  const valueType = entry.valueType?.trim();
  const prefix = valueType ? `${valueType}: ` : "";
  if (entry.sensitive || entry.value === null) return `${prefix}***`;
  return entry.value.length > MAX_DETAIL_CHARS ? `${prefix}${entry.value.slice(0, MAX_DETAIL_CHARS)}…` : `${prefix}${entry.value}`;
}

/**
 * CodeMirror completion source that offers the datara variables currently
 * registered in the editor. Returns `null` unless the cursor sits right after
 * `$` / `${` / `${partial.name`, so it never competes with normal SQL
 * completion.
 *
 * The option label carries the full `${scope.name}` reference on purpose: the
 * autocomplete framework matches the typed text between the result's `from` and
 * the cursor against each option label, and `from` sits on the `$`. A bare
 * `scope.name` label contains no `$`, so every candidate would be filtered out
 * and the popup would never appear.
 */
export function provideExternalVariableCompletions(context: CompletionContext): CompletionResult | null {
  const entries = externalVariableSnapshot();
  if (entries.length === 0) return null;

  const position = context.pos;
  const windowFrom = Math.max(0, position - LOOKBEHIND_CHARS);
  const before = context.state.doc.sliceString(windowFrom, position);
  const matched = VARIABLE_PREFIX_RE.exec(before);
  if (!matched) return null;

  const from = position - matched[0].length;
  const prefix = matched[2] ?? "";
  const lowered = prefix.toLowerCase();
  const candidates = prefix ? entries.filter((entry) => variableKey(entry).toLowerCase().startsWith(lowered)) : entries;
  if (candidates.length === 0) return null;

  // When the placeholder is already closed (`${|}`), replace the brace too so
  // accepting a completion does not leave a doubled `}`.
  const nextChar = context.state.doc.sliceString(position, position + 1);
  const to = nextChar === "}" ? position + 1 : position;

  return {
    from,
    to,
    options: candidates.map((entry) => {
      const key = variableKey(entry);
      return {
        label: `\${${key}}`,
        detail: detailFor(entry),
        type: "variable",
        apply: `\${${key}}`,
      };
    }),
    validFor: /^\$?\{?[\p{L}\p{N}_.]*\}?$/u,
  };
}
