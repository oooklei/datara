/**
 * 批量对齐/分布纯函数（工作台优化 Task 11，方案 §3.5）。
 * 语义对齐标准编辑器（Figma 式）：以选集包围盒为基准，不改传入数组——
 * 返回同序新数组，节点浅拷贝 + 新 position，由宿主自行写回 doc/渲染层。
 * 尺寸（宽/高）由调用方注入回调（画布实测），缺省按 0（点节点）处理。
 */

/** 对齐/分布节点最小结构（泛型透传保留 id/position 之外的额外字段） */
export interface AlignNode {
  id: string
  position: { x: number; y: number }
}

/** 对齐方向：左 / 右 / 上 / 下 / 水平居中 / 垂直居中 */
export type AlignDir = 'left' | 'right' | 'top' | 'bottom' | 'hcenter' | 'vcenter'

/** 分布轴：h = 水平（按 x 排序）/ v = 垂直（按 y 排序） */
export type DistributeAxis = 'h' | 'v'

/**
 * 对齐选中节点到选集包围盒：
 * - left: x = min(x_i)；right: x = max(x_i + w_i) - w_i；hcenter: x = (min(x_i) + max(x_i + w_i)) / 2 - w_i / 2
 * - top/bottom/vcenter 同理（y 与 heightOf）
 * 纯函数：返回同序新数组（节点浅拷贝 + 新 position），不改传入数组。
 */
export function alignNodes<N extends AlignNode>(
  nodes: N[],
  dir: AlignDir,
  widthOf?: (n: N) => number,
  heightOf?: (n: N) => number,
): N[] {
  if (!nodes.length) return []
  const horizontal = dir === 'left' || dir === 'right' || dir === 'hcenter'
  const coord = horizontal ? 'x' : 'y'
  const sizeOf = horizontal ? widthOf : heightOf
  const min = Math.min(...nodes.map((n) => n.position[coord]))
  const max = Math.max(...nodes.map((n) => n.position[coord] + (sizeOf?.(n) ?? 0)))
  return nodes.map((n) => {
    const size = sizeOf?.(n) ?? 0
    const pos = { ...n.position }
    if (dir === 'left' || dir === 'top') pos[coord] = min
    else if (dir === 'right' || dir === 'bottom') pos[coord] = max - size
    else pos[coord] = (min + max) / 2 - size / 2
    return { ...n, position: pos }
  })
}

/**
 * 分布选中节点（axis 轴按坐标排序后，相邻节点之间隙相等）：
 * gap = (lastLeft - firstLeft - Σsize) / (n-1)，x_i = 前一节点坐标 + 前一节点尺寸 + gap。
 * 首节点坐标固定；尺寸回调缺省按 0 处理（等距分布）。少于 3 个节点时原样返回传入数组引用。
 * 取舍说明：等间隙分布仅首节点坐标固定，末节点左坐标将移至 lastLeft − 末尺寸（计划测试值 [0,25,50] 口径）；
 * 与 Figma「首末均固定」语义有别，取计划口径。
 * 纯函数：≥3 时返回与入参同序的新数组（节点浅拷贝 + 新 position），不改传入数组。
 */
export function distributeNodes<N extends AlignNode>(
  nodes: N[],
  axis: DistributeAxis,
  widthOf?: (n: N) => number,
  heightOf?: (n: N) => number,
): N[] {
  if (nodes.length < 3) return nodes
  const coord = axis === 'h' ? 'x' : 'y'
  const sizeOf = axis === 'h' ? widthOf : heightOf
  /* 稳定排序取秩；result 按原数组下标回填，保证返回数组与入参同序 */
  const order = nodes
    .map((n, i) => ({ n, i }))
    .sort((a, b) => a.n.position[coord] - b.n.position[coord])
  const first = order[0]!.n.position[coord]
  const last = order[order.length - 1]!.n.position[coord]
  const sizes = order.map((o) => sizeOf?.(o.n) ?? 0)
  const gap = (last - first - sizes.reduce((s, v) => s + v, 0)) / (order.length - 1)
  const result = new Array<N>(nodes.length)
  let cursor = first
  order.forEach((o, rank) => {
    const pos = { ...o.n.position }
    pos[coord] = cursor
    result[o.i] = { ...o.n, position: pos }
    cursor += sizes[rank]! + gap
  })
  return result
}
