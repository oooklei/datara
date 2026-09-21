/**
 * 运行时节点服务（/dep/runtime 配套）：按全局分发策略挑选执行节点。
 * 分发策略（runtimePolicy 集合，单例 id=RP01）：
 * - 轮询：在线节点按心跳序轮换（mock 以时间片轮转模拟）
 * - 负载均衡：取正在执行任务数最少的在线节点
 * - 指定节点：固定下发到指定节点（该节点离线时回落负载均衡）
 * 无任何可用节点时回落「本地节点」（本地随系统自动注册，恒可用）。
 */
import { dataStore } from './dataStore'
import type { RuntimeNode, RuntimePolicy } from '../types'

export async function pickExecNode(): Promise<string> {
  const nodes = (await dataStore.list<RuntimeNode>('runtimeNodes')) ?? []
  const online = nodes.filter((n) => n.status === 'online')
  if (online.length === 0) return '本地节点'
  const policy = await dataStore.get<RuntimePolicy>('runtimePolicy')
  const mode = policy?.mode ?? '轮询'
  if (mode === '指定节点' && policy?.specificNode) {
    const fixed = online.find((n) => n.name === policy.specificNode)
    if (fixed) return fixed.name
  }
  if (mode === '负载均衡') {
    return [...online].sort((a, b) => a.tasks - b.tasks)[0].name
  }
  // 轮询：在线节点按当前时间片轮转（mock 演示）
  return online[Math.floor(Date.now() / 1000) % online.length].name
}
