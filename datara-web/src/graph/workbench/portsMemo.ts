/**
 * Task 12（方案§3.6）ports 结果 memo：按 schemaId + data JSON 摘要作键缓存工厂结果，
 * 杜绝拖拽/缩放每一帧对每个节点重算动态端口（如条件分支的每分支 Handle 列表）。
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
    const hit = cache.get(key)
    if (hit !== undefined) return hit
    const value = factory(schemaId, data)
    if (cache.size >= MEMO_CAP) cache.clear()
    cache.set(key, value)
    return value
  }
}
