/**
 * topo profile：部署运行拓扑视角（五层泳道，只读监控 + mock 健康刷新）
 * 接入层 → 运行时 → 中间件 → 计算引擎 → 存储
 */
import { findIsolated } from '../model'
import type { ViewProfile } from './types'
import type { GraphDocument } from '../model'

/** 周期刷新：确定性翻转个别组件健康状态（mock execService 异步推送语义） */
function tickHealth(doc: GraphDocument): void {
  const pool = doc.nodes.filter((n) => 'health' in n.data)
  if (!pool.length) return
  const n = pool[Math.floor(Math.random() * pool.length)]
  const cur = String(n.data.health ?? 'healthy')
  // 每次必产生状态变化：健康 → (告警|故障)，非健康 → 恢复
  const next = cur === 'healthy' ? (Math.random() < 0.4 ? 'fail' : 'warn') : 'healthy'
  n.data = { ...n.data, health: next }
}

export const topoProfile: ViewProfile = {
  id: 'topo',
  name: '集群拓扑',
  mode: 'view',
  defaultEdge: 'flow',
  layout: 'lane',
  lanes: [
    { key: 'access', name: '接入层' },
    { key: 'runtime', name: '运行时' },
    { key: 'middleware', name: '中间件' },
    { key: 'compute', name: '计算引擎' },
    { key: 'storage', name: '存储' },
  ],
  edgeKinds: {
    flow: { kind: 'flow', label: '数据流/调用', color: '#64748b' },
    dep: { kind: 'dep', label: '依赖/规划', color: '#94a3b8', dashed: true },
  },
  palette: [],
  nodeTypes: {
    lb: { type: 'lb', label: '负载均衡', icon: '⇄', color: '#0e7490', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    gateway: { type: 'gateway', label: 'API网关', icon: '◎', color: '#0369a1', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    app: { type: 'app', label: '应用实例', icon: '⬢', color: '#1668dc', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    ds_master: { type: 'ds_master', label: '调度 Master', icon: '⌘', color: '#7c3aed', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    ds_worker: { type: 'ds_worker', label: '执行 Worker', icon: '⌗', color: '#9333ea', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    zk: { type: 'zk', label: 'ZooKeeper', icon: '⌖', color: '#475569', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    kafka: { type: 'kafka', label: 'Kafka', icon: '≡', color: '#0d9488', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    redis: { type: 'redis', label: 'Redis', icon: '◈', color: '#dc2626', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    spark: { type: 'spark', label: 'Spark', icon: '⚡', color: '#ea580c', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    flink: { type: 'flink', label: 'Flink', icon: '≈', color: '#0d9488', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    mysql: { type: 'mysql', label: '业务库', icon: '⛁', color: '#c2410c', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    hdfs: { type: 'hdfs', label: 'HDFS', icon: '▤', color: '#b45309', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
    doris: { type: 'doris', label: 'Doris', icon: '◆', color: '#2563eb', shape: 'device', form: [],
      summary: (d) => `${d.comp} · ${d.addr}` },
  },
  validators: [
    (doc) => findIsolated(doc).map((id) => ({
      level: 'warn' as const,
      msg: `组件「${doc.nodes.find((n) => n.id === id)?.data.name}」未与任何组件连接`,
      nodeId: id,
    })),
  ],
  onTick: tickHealth,
}
