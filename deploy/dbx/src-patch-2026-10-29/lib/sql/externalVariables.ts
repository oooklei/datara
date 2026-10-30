export interface ExternalVariableEntry {
  scope: string;
  name: string;
  valueType?: string;
  value: string | null;
  sensitive?: boolean;
  unavailableReason?: string;
  description?: string;
}

let externalVariables: ExternalVariableEntry[] = [];

export function setExternalVariables(entries: ExternalVariableEntry[]): void {
  externalVariables = Array.isArray(entries) ? entries.slice() : [];
}

export function clearExternalVariables(): void {
  externalVariables = [];
}

export function lookupExternalVariable(key: string): string | null {
  const match = externalVariables.find((entry) => `${entry.scope}.${entry.name}` === key);
  if (!match || match.value === null) return null;
  return match.value;
}

export function externalVariableSnapshot(): ExternalVariableEntry[] {
  return externalVariables.slice();
}
