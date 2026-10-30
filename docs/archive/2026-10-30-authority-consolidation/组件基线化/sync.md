# 同步执行（C17）· type=`sync`

> 基线化设计册 · 分组：M-B1 同步类 · 状态：⏳ 1.9 实测通过（待认可发 v1）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写。

## 1. 语义分析

**执行模型**：runtimeOnly 执行组件（`RUNTIME_ONLY_TYPES` + `WORKER_TYPES`）。设计态画布/palette/校验均排除（schema 保留供运行实例详情渲染）；运行图由 master 引擎按 endpoint_select.baseMode∈{src_base,tgt_base} 物化插入（id 前缀 `sys_exec_`，materialize_sync_exec 注入 componentRef）。
**worker 执行器**（executors/sync.py，DataX/SeaTunnel 式读写器分离）：
- 读端：MySQL/GreatDB（单 schema / 多 schema UNION ALL / 分区隔离 / 前缀多表探测）+ CSV/TXT/Excel 文件源
- readerWhere 连接型拼 SQL WHERE；readerMatchType exact/prefix；autoSchema 运行时差集探测新增 schema
- 写端 MySQL/GreatDB；autoCreate 按源列建表；合并策略 union/src_flag/partition（裁定①②）
- 脏数据容忍（F33）：批插异常回退逐行定位，bad_rows 超 errorThreshold → failure
- **血缘（裁定④）**：成功后表级边（每参与源表→目标表）+ 字段映射落库（worker/lineage 公共入口）
**输出统计**：read_rows / write_rows / bad_rows / skipped_rows / rows_per_sec / batch_id(=instance_id) / schemas_included
**表单角色**：本节点仅保留运行兜底参数（合并配置优先，业务配置在 endpoint_select 等直通节点完成）。
**现状缺口**：chainHint 的 text 为常量函数；summary 为函数。

## 2. 八项表单规格（草案）

### params（4 项）

| key | label | uiType | required | default | options | 说明 |
|---|---|---|---|---|---|---|
| chainHint | （说明条） | hint | | | | 固定文案（text 函数 → 字符串字面量，决策 5） |
| batchSize | 批大小 | number | | 1000 | | 写端批大小上限 |
| errorThreshold | 错误阈值（坏行容忍条数） | number | | 0 | | 超阈值 failure（F33） |
| truncate | 写入前清空目标（TRUNCATE） | bool | | false | | |

### inputs / outputs / conditions / constraints / exclusions

均空（runtimeOnly：无设计态数据面声明；配置经 master 合并）。

### refs（0 条，注记）

合并链中的变量引用（filterExpr/incrementalExpr）已在 condition_set 声明，本节点不重复声明。

### exports（7 项，执行器产出统计键声明）

| key | from | type | desc |
|---|---|---|---|
| read_rows | output | number | 读取行数 |
| write_rows | output | number | 写入行数 |
| bad_rows | output | number | 坏行数 |
| skipped_rows | output | number | 跳过行数 |
| rows_per_sec | output | number | 速率（行/秒） |
| batch_id | output | string | 批次号（=instance_id） |
| schemas_included | output | array | 参与 schema 清单 |

### lineage（血缘声明，执行类必填）

| role | pick | assetType | 说明 |
|---|---|---|---|
| source | tgtDs | table | 读端数据源（连接型）|
| target | tgtDs | table | 写端数据源 |

**注**：sync 的读写端由合并配置动态决定（多 schema/文件源），声明级血缘以「数据源引用字段」为 pick 锚点（srcDs/tgtDs 均存在性由合并链保证）；字段级血缘运行时由 worker/lineage 落库（裁定④），声明级仅登记读写资产锚点。这是**执行类动态资产**的声明口径特例，体检 lineage_decl 按锚点字段存在性校验（草案，待用户确认）。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| chainHint（hint，text 常量函数） | params 段 hint 字段 | **决策 5**：常量 text 函数 → 字符串字面量 |
| batchSize / errorThreshold / truncate | params 段 | 平移 + default 显式化 |
| `summary: () => '同步执行（运行态，配置经 master 合并）'` 常量函数 | render.summaryRules 单条无 when 兜底模板 | 决策 2 |
| page（同步运行详情 F61） | render.page 声明位（组件引用不在 spec 冻结范围，注记） | 页面组件映射保留在前端 profile，spec 冻结页面元数据（title/尺寸） |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（params=4 / exports=7 / lineage=2）；runtimeOnly 节点（designing 画布不显示，RUNTIME_ONLY_TYPES 排除）；chainHint text 常量函数字符串字面量化（决策 5）；summary 常量函数迁移至 render.summaryRules 兜底模板；page 声明位保留在前端 profile（spec 冻结页面元数据）。

**后端**：零改动，executor=sync 消费键不变（executors/sync.py DataX/SeaTunnel 式读写器分离）；runtimeOnly 物化链（materialize_sync_exec，sys_exec_ 前缀）零改动。

**体检**（10 项全过）：contract=dag-engine+binding executor=sync；runtimeOnly 无设计态数据面声明合规；lineage_decl 通过（runtimeOnly pick 允许引用非本表单字段——srcDs/tgtDs 由合并链保证存在性）；exports 7 项完整。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

见 §2 lineage：声明级读写锚点 + 运行态字段级血缘（worker/lineage 裁定④）双层结构。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| wf=97 v5 | ec_retail.ods_order (250K) → datara_dw.dwd_order_sync_test | ✅ read=250000 write=250000 bad=0 rows_per_sec=5423.1 | Docker 内网数据源（ds#9→ds#4）；物化节点 sys_exec_c6bdbfe4；目标表数据验证一致 | 2026-09-28 |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
