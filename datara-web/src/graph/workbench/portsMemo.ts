/**
 * Task 12（方案§3.6）ports 结果 memo：按 schemaId + data JSON 摘要作键缓存工厂结果，
 * 避免 Inspector 编辑等 data 引用换新但深相等场景重复构建端口数组（如条件分支的每分支
 * Handle 列表）；拖拽帧不经过此路径（position 变更不触发该 computed）。
 *
 * 生命周期：memo 实例由 DataNode 按当前 schema 引用创建（组件实例级缓存），
 * schema 引用切换或组件卸载时整体回收，无全局泄漏。
 * 键含 schemaId：不同 schema 同 data 不串桶；键为 JSON 摘要：深相等 data 命中。
 */
/** 缓存容量上限：Inspector 每次编辑都产生新 data 键，无界增长会慢性泄漏；
 * 达到上限整体清空（简单有界，端口数组偶发重建一次开销可忽略） */
const MEMO_CAP = 64

export function memoPorts<T>(factory: (schemaId: string, data: Record<string, unknown>) => T) {
  const cache = new Map<string, T>()
  return (schemaId: string, data: Record<string, unknown>): T => {
    const key = `${schemaId}:${JSON.stringify(data)}`
    /* 命中判据用 has 而非 get !== undefined：工厂理论上可返回 undefined，
     * 以 get 结果判命中会把「缓存值为 undefined」误判为未命中而反复重算 */
    if (cache.has(key)) return cache.get(key) as T
    const value = factory(schemaId, data)
    if (cache.size >= MEMO_CAP) cache.clear()
    cache.set(key, value)
    return value
  }
}
