/**
 * Task 23（§2.4/§8.2）保存 409 三方逐项 diff（纯函数）：
 * 「我的 / 远端 / 基准」三档展开为可逐项采纳的条目，按采纳结果合并出待保存 spec。
 * 展开粒度：spec 顶层键；两侧同为数组 → 逐下标（path `k.i`）；两侧同为普通对象 → 逐子键（`k.sub`）；
 * 其余为单项（path `k`）。仅展开一层，保证条目数可控（页面 DSL 逐 widget 一行）。
 */

export type DiffSide = 'mine' | 'remote'

export interface ThreeWayItem {
  path: string
  mine: unknown
  remote: unknown
  base: unknown
  /** 本项是否被本地修改（mine ≠ base） */
  mineChanged: boolean
  /** 本项是否被远端修改（remote ≠ base） */
  remoteChanged: boolean
  /** 默认采纳方：本地未改 → 远端（他端修改）；远端未改 → 本地；双方均改 → 远端（服务器最新，可改选） */
  adopt: DiffSide
}

const eq = (a: unknown, b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b)

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v)

/** 读取 `k` / `k.i` / `k.sub` 三种形态的取值（越界/缺失返回 undefined） */
export function getDiffValue(spec: Record<string, unknown> | null, path: string): unknown {
  const dot = path.indexOf('.')
  if (dot < 0) return spec?.[path]
  const key = path.slice(0, dot)
  const sub = path.slice(dot + 1)
  const parent = spec?.[key]
  if (Array.isArray(parent)) return parent[Number(sub)]
  if (isPlainObject(parent)) return parent[sub]
  return undefined
}

/** 写入 `k` / `k.i` / `k.sub`（目标容器缺失时按远端值形态补建数组/对象） */
function setDiffValue(target: Record<string, unknown>, path: string, value: unknown): void {
  const dot = path.indexOf('.')
  if (dot < 0) { target[path] = value; return }
  const key = path.slice(0, dot)
  const sub = path.slice(dot + 1)
  const parent = target[key]
  if (Array.isArray(parent)) parent[Number(sub)] = value
  else if (isPlainObject(parent)) parent[sub] = value
  else target[key] = /^\d+$/.test(sub) ? Object.assign([], { [Number(sub)]: value }) : { [sub]: value }
}

function makeItem(path: string, mine: Record<string, unknown> | null, remote: Record<string, unknown> | null, base: Record<string, unknown> | null): ThreeWayItem {
  const m = getDiffValue(mine, path)
  const r = getDiffValue(remote, path)
  const b = getDiffValue(base, path)
  const mineChanged = !eq(m, b)
  const remoteChanged = !eq(r, b)
  return {
    path, mine: m, remote: r, base: b, mineChanged, remoteChanged,
    adopt: mineChanged ? (remoteChanged ? 'remote' : 'mine') : 'remote',
  }
}

/** 展开三方差异条目：mine 与 remote 相同的项不出现（无需选择）；base 缺档（无基线）时按 undefined 参与 */
export function threeWayDiffItems(
  mine: Record<string, unknown> | null,
  remote: Record<string, unknown> | null,
  base: Record<string, unknown> | null,
): ThreeWayItem[] {
  const items: ThreeWayItem[] = []
  const keys = [...new Set([...Object.keys(mine ?? {}), ...Object.keys(remote ?? {})])]
  for (const key of keys) {
    const m = mine?.[key]
    const r = remote?.[key]
    if (eq(m, r)) continue
    if (Array.isArray(m) || Array.isArray(r)) {
      // 逐下标（以较长侧为准；越界侧以 undefined 呈现「新增/删除」）
      const len = Math.max(Array.isArray(m) ? m.length : 0, Array.isArray(r) ? r.length : 0)
      for (let i = 0; i < len; i++) {
        const path = `${key}.${i}`
        if (!eq(getDiffValue(mine, path), getDiffValue(remote, path))) items.push(makeItem(path, mine, remote, base))
      }
    } else if (isPlainObject(m) && isPlainObject(r)) {
      // 逐子键
      for (const sub of [...new Set([...Object.keys(m), ...Object.keys(r)])]) {
        const path = `${key}.${sub}`
        if (!eq(getDiffValue(mine, path), getDiffValue(remote, path))) items.push(makeItem(path, mine, remote, base))
      }
    } else {
      items.push(makeItem(key, mine, remote, base))
    }
  }
  return items
}

/** 按逐项采纳合并：以 mine 为骨架，采纳 remote 的项写入远端值（深拷贝，防与快照共享引用） */
export function mergeThreeWay(
  mine: Record<string, unknown> | null,
  items: readonly ThreeWayItem[],
  decisions: Readonly<Record<string, DiffSide>>,
): Record<string, unknown> {
  const merged = JSON.parse(JSON.stringify(mine ?? {})) as Record<string, unknown>
  for (const item of items) {
    if ((decisions[item.path] ?? item.adopt) !== 'remote') continue
    setDiffValue(merged, item.path, item.remote === undefined ? undefined : JSON.parse(JSON.stringify(item.remote)))
  }
  return merged
}
