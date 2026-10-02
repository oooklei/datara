/**
 * B3 F0：FieldRenderer 单字段渲染器的节点级上下文契约。
 * Inspector 组装（候选缓存/脚本库互通/目录懒加载等节点级共享状态与动作），
 * FieldRenderer 每字段一个实例，只读消费 ctx 并直接回写 data 引用。
 * Ref/ComputedRef 原样传递，跨组件保持响应式依赖追踪。
 */
import type { ComputedRef, Ref } from 'vue'
import type { GNode } from '../../model'
import type { NodeSchema } from '../../profiles/types'
import type { DataContext } from '../../profiles/formLinkage'
import type { DsRow, DsTree } from '../../../services/datasourceApi'
import type { Script } from '../../../services/types'

/** 目录浏览导航状态（dir-select：当前路径/子目录/错误/请求序号，Inspector seq 防乱序） */
export type DirNav = { path: string; dirs: { name: string }[]; err: string; seq: number }

/** 运行时节点下拉选项（C14 SSH：real 拉注册表，mock 用 dataStore.runtimeNodes） */
export type RuntimeNodeOpt = { id: number | string; name: string; host: string; port: number }

/** C37 探测联动派生态（endpoint_select 的 probeResult 字段可见 ⇔ 非 null） */
export type EpProbeState = {
  loading: boolean
  err: string
  noTgt: boolean
  hits: { schema: string; table: string }[]
  checked: string[]
}

/** FieldRenderer 节点级上下文（Inspector 组装一次，对象引用稳定） */
export interface FieldCtx {
  /* —— 只读状态 —— */
  /** 画布直接上游节点（upstreamNodes 选项 / column src='upstream' 列枚举） */
  upstream: ComputedRef<GNode[]>
  /** 上游节点 schema 解析（选项标签 / 输入区块图标共用） */
  upSchema: (n: GNode) => NodeSchema
  /** 上游节点输出枚举（upstreamOutputs 行编辑选项，端点合一具名化 `nodeId:port`） */
  upstreamOpts: ComputedRef<{ value: string; label: string }[]>
  /**
   * F60 ①输入 的「上游输出引用」候选：`节点名.键（参数｜结果表）`。
   * 与 ②输出登记表（node.data.outputs.params/tables）同源，Inspector/弹窗/值域校验三处共用一份
   * （§12.2 禁双实现漂移）——`domainViolations` 据此判定 ①输入 存量引用是否悬空。
   */
  upstreamOuts: ComputedRef<string[]>
  /** C37 探测联动状态（probeResult 特化渲染门） */
  epProbe: ComputedRef<EpProbeState | null>
  /** 数据源中心行（datasource 选项过滤 / resolveDsId 解析） */
  dsRows: Ref<DsRow[]>
  /** 脚本库列表（scriptId 选项 / 选择一致性提示） */
  scripts: Ref<Script[]>
  /** 运行时节点候选（runtimeNode 选项 / dir 节点 id 解析） */
  runtimeNodes: Ref<RuntimeNodeOpt[]>
  /** ssh-nodes 标签并集（selectFrom='exec-node-tags' 选项） */
  tagOptions: ComputedRef<string[]>
  /** 已注册变量名（expr readonly 变量引用下拉） */
  varOptions: Ref<string[]>
  /** F3 数据驱动值域上下文（dataScope 字段候选唯一来源；Inspector/弹窗共用同一 resolveDataContext 解析） */
  dataCtx: ComputedRef<DataContext>
  /** 库表树缓存三通道（table/column/insert/map/probe 派生共用） */
  pickTrees: Ref<Record<string, DsTree>>
  pickTreeErr: Ref<Record<string, string>>
  pickTreeBusy: Ref<Record<string, boolean>>
  /** topic 枚举缓存（ds 名 → topics；失败不缓存） */
  topicOpts: Ref<Record<string, string[]>>
  topicErr: Ref<Record<string, string>>
  topicBusy: Ref<Record<string, boolean>>
  /** 目录浏览导航状态（字段 key → DirNav；节点/依赖切换时 Inspector 整体重置） */
  dirNavs: Ref<Record<string, DirNav>>
  /* —— 动作 —— */
  /** 按需拉取库表树（按 ds 名缓存 + busy 去重；失败置行内错误不抛出） */
  ensureTree: (dsName: string) => Promise<DsTree | null>
  /** 按需枚举 topic（force=true 强制重拉刷新） */
  ensureTopics: (dsName: string, force?: boolean) => Promise<void>
  /** SFTP 目录懒加载（Inspector 持有全局请求序号，seq 防乱序/孤儿） */
  lsDir: (fKey: string, nodeId: number | string, path: string) => void
  /** 脚本库互通（作用于当前节点的 scriptId/code/lang 字段，Inspector 持有实现） */
  loadScriptCode: () => void
  saveToScript: () => void
  saveAsNewScript: () => void
  /** 文档脏标记（行编辑/勾选回写/级联写回等持久化入口） */
  markDirty: () => void
  /** 当前节点 schema（依赖字段展示名 depLabel 回退判定） */
  schema: ComputedRef<NodeSchema | null>
}
