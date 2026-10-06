/**
 * canvas-bench 工具：构建 200 节点/400 边标准图文档（方案 §3.6 基准用，§11.3 基线对比）。
 * 纯工具模块（无 .test 后缀），vitest 不会收集。
 *
 * 节点 type 对齐 src/graph/profiles/dag.ts 的真实类型：
 * - 'sql'：数据计算类 SQL 节点（palette「数据计算」真实存在）；
 * - 计划原文的 'sink' 并非模型真实 type，改用逻辑控制类的 'end'（结束节点，
 *   dag 中 maxOut=0、天然充当流程汇聚终点）。基准图不跑 validator，链式边穿越
 *   end 节点仅作量测负载，不影响计时语义。
 * 边 kind 取 dag profile 的默认边语义 'flow'（src/graph/model/index.ts EDGE_KIND.flow）。
 */
import type { GEdge, GNode, GraphDocument } from '../../src/graph/model'

/** 构建标准基准图：默认 200 节点（前 160 个为 sql 型、其余 end 型）/400 条 flow 边 */
export function buildBenchDoc(nodeCount = 200, edgeCount = 400): GraphDocument {
  const sqlCount = Math.floor(nodeCount * 0.8)
  const sinkCount = nodeCount - sqlCount
  const nodes: GNode[] = []
  const edges: GEdge[] = []

  // 网格排布（每行 20 列）：x = 列 * 240，y = 行 * 140，模拟真实画布散布
  for (let i = 0; i < nodeCount; i++) {
    const isSql = i < sqlCount
    nodes.push({
      id: `bench_n${i}`,
      type: isSql ? 'sql' : 'end',
      position: { x: (i % 20) * 240, y: Math.floor(i / 20) * 140 },
      data: { name: isSql ? `SQL 加工 ${i}` : `结束 ${i}` },
    })
  }

  // 链式主干：bench_n0 → bench_n1 → … → bench_n{n-1}，共 nodeCount-1 条
  for (let i = 0; i < nodeCount - 1; i++) {
    edges.push({ id: `bench_e${edges.length}`, source: `bench_n${i}`, target: `bench_n${i + 1}`, kind: 'flow' })
  }

  // 汇聚补足至 edgeCount：源节点每第 5 个取一个（sql 区内循环取 0,5,…,155）；
  // 目标自首个 sink（bench_n160）起在 sink 池内轮转——严格只连首个 sink 最多产生
  // sqlCount/5 条不重复边，凑不满 400 条，故目标轮转 sink 池。j 与 j+32 同源时目标
  // 错位 33 格（33 与 40 互素），need=201 < 1280，数学上保证 (source,target) 不重复。
  const need = edgeCount - (nodeCount - 1)
  for (let j = 0; j < need; j++) {
    const src = `bench_n${(5 * j) % sqlCount}`
    const tgt = `bench_n${sqlCount + ((j + Math.floor(j / (sqlCount / 5))) % sinkCount)}`
    edges.push({ id: `bench_e${edges.length}`, source: src, target: tgt, kind: 'flow' })
  }

  return {
    id: 'bench_doc',
    name: 'canvas-bench 标准基准图',
    version: 1,
    meta: { profile: 'dag' },
    nodes,
    edges,
  }
}
