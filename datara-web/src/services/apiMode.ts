/**
 * API 模式开关（叶子模块：**刻意不 import 任何东西**）。
 *
 * 背景：此前 `isMock` 定义在 `services/index.ts`，而 `index.ts` 又从 `graphApi.ts` /
 * `datasourceApi.ts` 再导出各自实现 → 各 api 模块若要判断 mock 只能 `import { isMock } from './index'`，
 * 与 `index.ts → graphApi.ts` 形成**循环依赖**。`datasourceApi.ts:11` 已经在承受这个环。
 *
 * 拆成叶子模块后依赖方向单向：`apiMode.ts ← graphApi/datasourceApi/syncApi ← index.ts`，
 * 既消除环，也让各 api 模块能在函数内部自行 mock 化（不必改调用方的 import）。
 */
export type ApiMode = 'real' | 'mock'

/** 'real'（默认）| 'mock' */
export const apiMode: ApiMode = (import.meta.env.VITE_API_MODE as ApiMode | undefined) ?? 'real'

export const isMock = apiMode === 'mock'
