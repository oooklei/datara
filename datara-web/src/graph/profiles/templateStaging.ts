/**
 * 模板展开的暂存/编排纯逻辑（configure-first，§12.1）。
 *
 * 背景：模板此前「单 mode → 直接物化」，8 个节点一次性写进画布，用户无法在落地前配置任何一步；
 * 而其中 C1 开始 / C2 结束的 `form` 为空，弹窗只能呈现 6 个空区块，逐一索要配置是纯摩擦。
 *
 * 改造后的语义（用户已确认）：
 *  1. **暂存**：模板 `build()` 产出的节点/边先留在暂存区，不写 doc、不画到画布；
 *  2. **逐节点配置**：只有「有可配置内容」的节点进向导，复用同一个配置弹窗实例；
 *  3. **原子提交**：末步确认才一次性写 doc；任一步取消则整链丢弃（暂存本就没写过 doc → 画布无痕）。
 *
 * 本模块只放纯函数（暂存区无 IO、无 Vue 依赖），编排状态机留在 `GraphWorkbench.vue`。
 */
import type { GEdge, GNode } from '../model'
import type { NodeSchema } from './types'
import { hasConfigurableContent } from './formSections'

/** 模板暂存区（尚未落画布） */
export interface TemplateStage {
  /** 模板模式名（向导标题/成功提示用） */
  chainLabel: string
  /** 全链节点（含被跳过的纯装饰节点，提交时一并写入） */
  nodes: GNode[]
  /** 全链边 */
  edges: GEdge[]
  /** 需用户配置的节点（按链序 = `nodes` 声明序） */
  steps: GNode[]
  /** 当前步（0 基，指向 `steps`） */
  step: number
}

/**
 * 挑出需要用户配置的节点（= 向导步序）。
 *
 * 判定复用 `hasConfigurableContent`：有业务表单字段，或六区块任一有值/引用。
 * 纯装饰节点（C1 开始 / C2 结束：form 空且六区块无值）不入向导，提交时自动带上。
 *
 * @param nodes  模板 build 产出的节点（**保持链序**）
 * @param lookup 节点类型 → schema（取不到 schema 的节点按「需配置」保守处理并由调用方报错）
 */
export function selectTemplateSteps(
  nodes: GNode[],
  lookup: (type: string) => NodeSchema | undefined,
): GNode[] {
  return nodes.filter((n) => {
    const s = lookup(n.type)
    if (!s) return true
    return hasConfigurableContent(s.form ?? [], (n.data ?? {}) as Record<string, unknown>)
  })
}

/**
 * 暂存链内某节点的**全部可达上游**（反向 BFS，只在暂存子图内遍历）。
 *
 * 用途：弹窗的 ①输入候选与 `dataScope` 上游列/表域都以它为「上游」，
 * 使**暂存期**的校验口径与节点落画布后等价——不依赖尚未写入 doc 的节点。
 *
 * 健壮性：
 *  - `seen` 预置 `targetId` → 脏模板若含回边，节点不会把自己算成自己的上游
 *    （否则 `upstream-columns` 会把本表列混进值域，掩盖真实校验）；
 *  - 入边自环跳过、不存在的节点 id 静默忽略 → 不抛错阻断向导。
 */
export function stagedUpstreamOf(
  stage: Pick<TemplateStage, 'nodes' | 'edges'>,
  targetId: string,
): GNode[] {
  const incoming = new Map<string, string[]>()
  for (const e of stage.edges) {
    if (e.source === e.target) continue
    const arr = incoming.get(e.target)
    if (arr) arr.push(e.source)
    else incoming.set(e.target, [e.source])
  }
  const seen = new Set<string>([targetId])
  const out: GNode[] = []
  const queue = [...(incoming.get(targetId) ?? [])]
  while (queue.length) {
    const id = queue.shift()!
    if (seen.has(id)) continue
    seen.add(id)
    const n = stage.nodes.find((x) => x.id === id)
    if (!n) continue
    out.push(n)
    queue.push(...(incoming.get(id) ?? []))
  }
  return out
}

/** 构造暂存区（`steps` 由 `selectTemplateSteps` 填充） */
export function createTemplateStage(chainLabel: string, nodes: GNode[], edges: GEdge[]): TemplateStage {
  return { chainLabel, nodes, edges, steps: [], step: 0 }
}
