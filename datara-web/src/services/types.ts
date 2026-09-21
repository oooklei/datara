/**
 * 服务契约层：前端唯一依赖的接口定义（即未来真实后端 API 契约）。
 * 全部 async；execService 提交即返回，状态经 EventBus 异步推送。
 */
import type { GraphDocument } from '../graph/model'

export type NodeRunStatus = 'queued' | 'running' | 'success' | 'fail'

export interface RunHandle { runId: string }
export interface RunOptions { fromNode?: string }

export interface NodeStatusEvent {
  runId: string
  nodeId: string
  status: NodeRunStatus
  ts: number
  log?: string
}

export interface VersionMeta {
  version: number
  updatedAt: string
  operator: string
  remark?: string
}

export interface IGraphService {
  get(id: string): Promise<GraphDocument | null>
  save(doc: GraphDocument, remark?: string): Promise<{ version: number }>
  listVersions(id: string): Promise<VersionMeta[]>
  rollback(id: string, version: number): Promise<GraphDocument>
}

export interface IExecService {
  run(doc: GraphDocument, opts?: RunOptions): Promise<RunHandle>
  stop(runId: string): Promise<void>
}

/* ============================================================
 * 全模块集合契约（Wave 0 todo 2）
 * 字段名与 prototype/assets/data.js 逐字一致（只读形状，不做业务改写）
 * ============================================================ */

/* ---------- 通用：状态字典 / 菜单 ---------- */
export interface StEntry {
  label: string
  cls: string
}
export type StDict = Record<string, StEntry>

export interface MenuItem {
  id?: string
  icon?: string
  label: string
  path: string
  children?: MenuItem[]
}
export interface MenuGroup {
  group: string
  items: MenuItem[]
}

/* ---------- M03 数据源 ---------- */
export interface DsType {
  name: string
  code: string
  group: string
  xc: boolean
  port: number
  color: string
}
export interface DataSourcePool {
  max: number
  minIdle: number
  idle: number
  timeout: number
}
export interface DataSource {
  id: string
  name: string
  type: string
  host: string
  port: number
  db: string
  user: string
  pwd: string
  env: string
  group: string
  tags: string[]
  pool: DataSourcePool
  status: string
  owner: string
  createdAt: string
  latency: number
  health: string
  /** 最近探活时间戳（todo 8 探活成功后写入，格式 yyyy-MM-dd HH:mm:ss） */
  lastProbe?: string
}

/* ---------- M04 数仓模型 ---------- */
export interface DwLayer {
  code: string
  name: string
  desc: string
  color: string
  rule: string
}
export interface ModelField {
  n: string
  t: string
  len: string | number
  pk: boolean
  pkPart: boolean
  cmt: string
  def: string
}
export interface ModelVersion {
  v: number
  date: string
  author: string
  note: string
  status: string
}
export interface Model {
  id: string
  name: string
  code: string
  layer: string
  engine: string
  type: string
  status: string
  fields: ModelField[]
  version: number
  owner: string
  bizDomain: string
  updatedAt: string
  versions: ModelVersion[]
}
export interface EngineType {
  name: string
  ddl: string
  xc: boolean
}

/* ---------- M05 批处理/同步 ---------- */
export interface SyncLog {
  st: string
  tt: string
  sc: number
  tc: number
  dc: number
  status: string
  dur: string
  /** 同步分区（如 dt=2026-09-11 对应日期） */
  partition?: string
}
export interface SyncBatch {
  id: string
  srcDs: string
  srcName: string
  target: string
  mode: string
  strategy: string
  total: number
  ok: number
  diff: number
  fail: number
  srcRows: number
  tgtRows: number
  status: string
  startAt: string
  endAt: string
  cron: string
  concurrency: number
  retry: number
  logs: SyncLog[]
}
/** 工作流局部变量（M13）：支持默认值/加密值/下拉选择 */
export interface WfVariable {
  id: string
  wf: string
  name: string
  value: string
  type: '日期' | '文本' | '数值' | '加密' | '下拉'
  encrypted: boolean
  options: string[]
  desc: string
}
export interface EtlOp {
  id: string
  type: string
  name: string
  cfg: string
}
export interface EtlTask {
  id: string
  name: string
  code: string
  type: string
  status: string
  owner: string
  ops?: EtlOp[]
  sql?: string
  scriptLang?: string
  script?: string
  cron: string
  lastRun: string
  updatedAt: string
}

/* ---------- M06 流处理 ---------- */
export interface StreamCheckpoint {
  interval: string
  mode: string
  backend: string
  lastOk: string
  successRate: string
}
export interface StreamMetrics {
  tps: number
  latency: string
  inTotal: number
  outTotal: number
  watermark: string
}
export interface StreamJob {
  id: string
  name: string
  type: string
  source: string
  sink: string
  status: string
  checkpoint: StreamCheckpoint
  metrics: StreamMetrics
  sql: string
  owner: string
  parallelism: number
  uptime: string
  createdAt: string
}
export interface StreamWindow {
  name: string
  desc: string
  eg: string
}
export interface TimeSemantics {
  name: string
  desc: string
  use: string
}

/* ---------- M07 质量管理 ---------- */
export interface QcDim {
  code: string
  name: string
  icon: string
  color: string
  desc: string
}
export interface QcRule {
  id: string
  name: string
  table: string
  field: string
  dim: string
  type: string
  threshold: string
  level: string
  status: string
  owner: string
  lastResult: string
  linkTask: string
  /** 预制规则（系统内置，可停用不可删除） */
  builtin?: boolean
  /** 校验正则（预制格式规则使用） */
  pattern?: string
}
export interface QcTask {
  id: string
  name: string
  tables: number
  rules: number
  cron: string
  linkEtl: string
  status: string
  lastRun: string
  lastResult: string
}
export interface QcException {
  id: string
  qcId: string
  ruleId: string
  ruleName: string
  table: string
  field: string
  dim: string
  cnt: number
  dt: string
  status: string
  sample: Record<string, unknown>[]
}
export interface QcReport {
  id: string
  name: string
  type: string
  period: string
  score: number
  problems: number
  fixed: number
  status: string
}
export interface QcAlarm {
  id: string
  name: string
  channel: string
  scope: string
  threshold: string
  receivers: string
  status: string
}

/* ---------- 开放接口（流数据/数据质量/元数据 三类产出型 API） ---------- */
export interface OpenApi {
  id: string
  name: string
  path: string
  method: 'GET' | 'POST'
  category: '流数据' | '数据质量' | '元数据'
  desc: string
  status: 'enabled' | 'disabled'
  /** 请求参数说明（模拟网关文档用） */
  params: { name: string; required: boolean; desc: string }[]
  /** 响应示例（JSON 字符串） */
  respExample: string
  calls: number
}
export interface OpenApiKey {
  id: string
  name: string
  key: string
  /** 绑定的 API id 列表（空 = 未绑定，无法调用） */
  apis: string[]
  status: 'enabled' | 'disabled'
  owner: string
  createdAt: string
  lastCalled: string
  calls: number
}
export interface OpenLog {
  id: string
  ts: string
  keyId: string
  keyName: string
  apiId: string
  apiPath: string
  params: string
  httpStatus: number
  costMs: number
  result: 'success' | 'denied' | 'error'
  msg: string
}
export interface QcScoreTrend {
  labels: string[]
  ods: number[]
  dwd: number[]
  dws: number[]
  ads: number[]
}
export interface QcDimScore {
  name: string
  score: number
}

/* ---------- M09 元数据 ---------- */
export interface BizDomain {
  name: string
  color: string
  tables: number
  models: number
  indicators: number
  desc: string
}
export interface MetaTable {
  id: string
  name: string
  layer: string
  domain: string
  rows: number
  size: string
  owner: string
  tags: string[]
  yesterdayOk: boolean
  desc: string
  sample: Record<string, unknown>[]
  /** 最近采集时间戳（采集成功后写入） */
  collectedAt?: string
  /** 数据密级（M15 数据安全·分级分类）：公开/内部/机密/绝密；缺省=内部 */
  security?: string
}
export interface TableLineage {
  from: string
  to: string
  task: string
  wf: string
}
export interface FieldLineageItem {
  from: string
  transform: string
}
export type FieldLineage = Record<string, FieldLineageItem[]>
export interface ImpactExample {
  table: string
  downTables: { name: string; task: string }[]
  downTasks: { name: string; wf: string; type: string }[]
  downIndicators: { name: string; code: string }[]
  reports: string[]
}
export interface MetaTag {
  id: string
  name: string
  cat: string
  color: string
  cnt: number
  desc: string
  tables: string[]
}

/* ---------- M10 数据标准 ---------- */
export interface StdElement {
  id: string
  cn: string
  en: string
  type: string
  len: string | number
  format: string
  domain: string
  desc: string
  status: string
  v: number
  owner: string
  updatedAt: string
}
export interface StdCodeValue {
  c: string
  n: string
}
export interface StdCode {
  id: string
  name: string
  values: StdCodeValue[]
  status: string
  used: number
}
export interface NamingRule {
  id: string
  scope: string
  pattern: string
  eg: string
  desc: string
  status: string
}
export interface StdMapping {
  id: string
  table: string
  field: string
  stdId: string
  stdName: string
  result: string
  diff: string
  checkedAt: string
}
export interface StdApproval {
  id: string
  type: string
  target: string
  proposer: string
  submitAt: string
  flow: string[]
  current: number
  status: string
  opinion: string
}

/* ---------- M10 指标 ---------- */
export interface IndicatorVersion {
  v: number
  date: string
  note: string
  author: string
}
export interface Indicator {
  id: string
  name: string
  en: string
  type: string
  bizDef: string
  techDef: string
  srcTable: string
  srcField: string
  outTable: string
  outTask: string
  period: string
  dims: string
  owner: string
  domain: string
  status: string
  v: number
  trend: number[]
  unit: string
  baseMetric?: string
  formula?: string
  changeNote?: string
  versions: IndicatorVersion[]
}
export interface IndConsistency {
  metric: string
  places: string[]
  result: string
  detail: string
}

/* ---------- M12 参数 ---------- */
export interface GlobalParam {
  id: string
  name: string
  value: string
  type: string
  encrypt: boolean
  desc: string
  env: string
  updatedAt: string
}
export interface BuiltinParam {
  name: string
  desc: string
  eg: string
}
export interface EnvGroup {
  name: string
  desc: string
  cnt: number
  ds: string
  params: string
}
export interface RefCheckResult {
  file: string
  refs: string[]
  result: string
  detail: string
}
export interface ParamPreview {
  name: string
  scope: string
  value: string
}

/* ---------- M13 DAG ---------- */
export interface WorkflowNodeDetail {
  id: string
  name: string
  type: string
  dep: string[]
  outTable: string
  retry: number
  dur: string
}
export interface WorkflowMeta {
  id: string
  name: string
  cron: string
  owner: string
  status: string
  nodes: number
  lastRun: string
  lastResult: string
  desc: string
  nodesDetail: WorkflowNodeDetail[]
}
export interface WfInstanceNode {
  id: string
  name: string
  status: string
  start: string
  end: string
  dur: string
  retry: number
  err?: string
}
export interface WfInstance {
  id: string
  wf: string
  wfName: string
  bizDate: string
  status: string
  startAt: string
  endAt: string
  dur: string
  /** 执行节点（运行时节点页注册的节点名；缺省 = 历史实例未记录） */
  execNode?: string
  nodes: WfInstanceNode[]
}
export interface TableDep {
  down: { wf: string; task: string }
  up: { wf: string; task: string }
  table: string
  period: string
  strategy: string
  check: string
}
export interface DagAlarm {
  id: string
  name: string
  scope: string
  event: string
  channel: string
  receivers: string
  status: string
}
export interface SlaRule {
  id: string
  wf: string
  deadLine: string
  today: string
  status: string
  history: string
}

/* ---------- M14 脚本 ---------- */
export interface Script {
  id: string
  name: string
  lang: string
  status: string
  owner: string
  updated: string
  code: string
}
export interface PyEnvPkg {
  n: string
  v: string
}
export interface PyEnv {
  id: string
  name: string
  python: string
  pkgs: PyEnvPkg[]
  status: string
  used: number
}
export interface ExecLog {
  id: string
  script: string
  mode: string
  status: string
  start: string
  dur: string
  content: string
}
export interface RemoteNode {
  id: string
  name: string
  ip: string
  os: string
  mode: string
  auth: string
  status: string
  lastPing: string
  scripts: number
}

/* ---------- 运行时节点（/dep/runtime：任务执行节点注册表，SSH 主机信息唯一权威源） ---------- */
export interface RuntimeNode {
  id: string
  name: string
  /** 本地=系统自动注册（无需 SSH）；远程=必须完整配置 SSH 信息 */
  kind: '本地' | '远程'
  host: string
  port: number
  user: string
  /** 密钥名 / 密码(加密存储) / 本地进程（无需SSH） */
  auth: string
  /** 远程必填：脚本/任务分发运行时目录 */
  runtimeDir: string
  /** 远程必填：临时数据目录 */
  tmpDir: string
  os: string
  status: 'online' | 'offline'
  /** 资源状态（最近心跳采样）：CPU/内存/磁盘 使用率 % */
  cpu: number
  mem: number
  disk: number
  /** 正在执行的任务数（负载均衡分发依据） */
  tasks: number
  lastHeartbeat: string
  desc?: string
}
/** 全局分发策略（启动/重跑任务时按策略挑选执行节点） */
export interface RuntimePolicy {
  id: string
  mode: '轮询' | '负载均衡' | '指定节点'
  /** mode=指定节点 时的默认节点名 */
  specificNode: string
  updatedAt: string
}

/* ---------- M16 部署 ---------- */
export interface Server {
  id: string
  name: string
  ip: string
  cpu: string
  mem: string
  disk: string
  os: string
  role: string
  status: string
}
export interface Component {
  id: string
  name: string
  version: string
  role: string
  nodes: string[]
  status: string
  health: string
  cpu: number
  mem: number
  qps: number
  upDays: number
}
export interface Suite {
  id: string
  name: string
  comps: string
  desc: string
  status: string
}
export interface PrecheckItem {
  item: string
  result: string
  detail: string
}
export interface DeployLog {
  id: string
  comp: string
  node: string
  time: string
  level: string
  content: string
}
export interface DeployAlarm {
  id: string
  level: string
  comp: string
  title: string
  time: string
  channel: string
  status: string
  desc: string
}
export interface Backup {
  id: string
  target: string
  time: string
  size: string
  type: string
  status: string
}

/* ---------- IDE ---------- */
export interface IdeHistory {
  id: string
  ds: string
  sql: string
  rows: number
  dur: string
  time: string
  star: boolean
}
export interface SqlFunc {
  cat: string
  items: string[]
}

/* ---------- 血缘图（DAG 用） ---------- */
export interface LineageGraph {
  nodes: { id: string; layer: string }[]
  edges: [string, string][]
}

/* ---------- 外壳 ---------- */
export interface Notification {
  id: number
  icon: string
  cls: string
  title: string
  desc: string
  time: string
}
export interface DbUser {
  name: string
  role: string
  /** 数据许可上限（M15）：公开/内部/机密/绝密；缺省=绝密（管理员） */
  clearance?: string
}

/* ---------- M15 数据安全（RBAC + 脱敏 + 审计） ---------- */
/** 平台用户：用户→角色→权限（角色编码 admin/dev/analyst/viewer） */
export interface User {
  id: string
  name: string
  role: string
  roleName: string
  /** 数据许可上限 */
  clearance: string
  /** 授权业务域（空=全部） */
  domains: string[]
  status: 'enabled' | 'disabled'
  lastLogin: string
}
/** 脱敏规则：敏感字段类型 → 策略 */
export interface MaskRule {
  id: string
  field: string
  type: string
  strategy: string
  scope: string
  enabled: boolean
}
/** 访问审计：谁、什么时间、查了什么、查了多少 */
export interface AccessLog {
  id: string
  user: string
  action: string
  target: string
  rows: number
  ts: string
  result: '允许' | '拒绝'
  reason?: string
}

/* ---------- 集合标识 union（覆盖 data.js DB 全部顶层键） ---------- */
export type CollectionKey =
  | 'dsTypes' | 'datasources'
  | 'dwLayers' | 'models' | 'engineTypes'
  | 'syncBatches' | 'etlTasks' | 'syncHistory'
  | 'streamJobs' | 'windows' | 'timeSemantics'
  | 'qcDims' | 'qcRules' | 'qcTasks' | 'qcExceptions' | 'qcScoreTrend' | 'qcDimScore' | 'qcReports' | 'qcAlarms' | 'qcKeepDays' | 'qcRetention'
  | 'bizDomains' | 'metaTables' | 'tableLineage' | 'fieldLineage' | 'impactExample' | 'metaTags'
  | 'stdElements' | 'stdCodes' | 'namingRules' | 'stdMappings' | 'stdApprovals'
  | 'indicators' | 'indConsistency'
  | 'globalParams' | 'builtinParams' | 'envGroups' | 'refCheckResult' | 'paramPreview'
  | 'workflows' | 'wfVariables' | 'wfInstances' | 'tableDeps' | 'dagAlarms' | 'slaRules'
  | 'scripts' | 'pyEnvs' | 'execLogs' | 'remoteNodes'
  | 'servers' | 'components' | 'suites' | 'precheckItems' | 'deployLogs' | 'deployAlarms' | 'backups' | 'deployWizardSteps'
  | 'runtimeNodes' | 'runtimePolicy' | 'sshNodes'
  | 'ideHistory' | 'sqlFuncs' | 'lineageGraph'
  | 'notifications' | 'channelCfg' | 'env' | 'user'
  | 'openApis' | 'apiKeys' | 'openLogs'
  | 'users' | 'maskRules' | 'accessLogs'

/* ---------- 数据存储接口（全部 async；内存实现 + localStorage 兜底） ---------- */
export interface IDataStore {
  get<T>(col: CollectionKey): Promise<T | null>
  list<T>(col: CollectionKey): Promise<T[]>
  save<T>(col: CollectionKey, row: T): Promise<void>
  remove(col: CollectionKey, id: string): Promise<void>
}
