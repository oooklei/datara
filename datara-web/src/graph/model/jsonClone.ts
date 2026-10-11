/**
 * Clone graph payloads across the Vue-reactive boundary.
 * Graph state is deliberately JSON data; JSON serialization unwraps Vue
 * proxies while structuredClone rejects them with DataCloneError.
 */
export function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
