# 文件入仓执行（C24）· type=`file_sync`

> 基线化设计册 · 分组：M-B1 同步类 · 状态：⏳ 1.9 实测通过（待认可发 v1）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写。

## 1. 语义分析

**执行模型**：runtimeOnly 执行组件（`RUNTIME_ONLY_TYPES` + `WORKER_TYPES`）。设计态画布排除；运行图由 master 按 endpoint_select.baseMode=file_sync 物化插入（sys_exec_ 前缀）。
**worker 执行器**（executors/file_sync.py，I12 §3.1）：
- 取文件：/datara/files 共享卷直读（file.py 同口径）；不在共享卷且配置 runtimeNode → SFTP 拉取暂存（`{instance_id}_filesync_` 前缀，D4 清扫口径），结束即清理
- 解析/类型推断：复用 dsconn.iter_rows + infer_schema（不复制逻辑）
- 建表：autoCreate 按推断类型映射 BIGINT/DOUBLE/TINYINT(1)/DATETIME/TEXT；src_flag 追加标识列
- 写入：append=INSERT / overwrite=先 TRUNCATE / src_flag=常量标识列（值=来源文件名）；批插复用 sync._insert_batch（脏行回退计忽略行，不断流）
**输出统计**：rows_read / rows_written / rows_skipped / batch_id(=instance_id)
**表单角色**：仅写入模式等兜底参数（文件路径/类型/目标端由 master 合并自 endpoint_select）。
**现状缺口**：flagColumn 带 showIf；summary 为函数；fieldMap 在 defaults 中（运行兜底映射）。

## 2. 八项表单规格（草案）

### params（5 项）

| key | label | uiType | required | default | options | 说明 |
|---|---|---|---|---|---|---|
| chainHint | （说明条） | hint | | | | 固定文案（决策 5） |
| writeMode | 写入模式 | select | | append | append=追加 / overwrite=覆盖先 TRUNCATE / src_flag=标识列每行落来源文件标识 | |
| flagColumn | 标识列名 | text | | src_schema | | writeMode=src_flag 时生效 |
| autoCreate | 目标表不存在时自动建表 | bool | | true | | 按文件表头推断类型 |
| fieldMap | 字段映射（兜底） | mapEditor | | [] | mode=columnMap | 运行兜底映射（合并配置优先） |

### inputs / outputs / conditions / constraints / exclusions

均空（runtimeOnly）。

### refs（0 条，注记）

同 sync：合并链变量引用已在直通节点声明。

### exports（4 项）

| key | from | type | desc |
|---|---|---|---|
| rows_read | output | number | 读取行数 |
| rows_written | output | number | 写入行数 |
| rows_skipped | output | number | 忽略行数 |
| batch_id | output | string | 批次号（=instance_id） |

### lineage（血缘声明，执行类必填）

| role | pick | assetType |
|---|---|---|
| source | filePath | file |
| target | tgtDs（经 endpoint_select 合并） | table |

注：source 锚点为文件路径字段（file 型资产），target 为合并链目标端数据源引用字段——动态合并锚点口径同 sync（草案，待用户确认）。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| chainHint（hint，text 常量函数） | params 段 hint 字段 | 决策 5 |
| writeMode / flagColumn / autoCreate | params 段 | 平移；flagColumn showIf → conditions |
| defaults.fieldMap | params 段 fieldMap | **决策 6**：defaults 值并入 params.default 显式声明 |
| `summary: (d) => ...` 函数 | render.summaryRules（分型模板） | 决策 2 |
| fileType/delimiter/encoding/headerRows（defaults 遗留） | 不入 params（合并配置优先，endpoint_select 文件区为准）——注记保留避免双真源 | 决策 7 |

### conditions（1 条）

| id | when | show |
|---|---|---|
| c-flag-col | writeMode = src_flag | flagColumn |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（params=5 / conditions=1 / exports=4 / lineage=2）；runtimeOnly 节点；flagColumn showIf → conditions（writeMode=src_flag 时显示）；defaults.fieldMap 值并入 params.default 显式声明（决策 6）；fileType/delimiter/encoding/headerRows 不入 params（合并配置优先，endpoint_select 文件区为准，决策 7）；summary 函数迁移至 render.summaryRules 分型模板。

**后端**：零改动，executor=file_sync 消费键不变（executors/file_sync.py，/datara/files 共享卷直读 + SFTP 拉取暂存）；master 物化链（baseMode=file_sync 插入 sys_exec_ 前缀节点）零改动。

**体检**（10 项全过）：contract=dag-engine+binding executor=file_sync；runtimeOnly 合规；lineage 文件源锚点（filePath/file）+ 目标表锚点（tgtDs/table）完整；conditions 替代 showIf；exports 4 项完整。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

见 §2 lineage：文件源锚点 + 目标表锚点；运行态字段级血缘由 worker/lineage 落库。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| wf=98 v2 | mb1_test.csv (5 rows) → datara_dw.dwd_file_sync_test | ✅ rows_read=5 rows_written=5 rows_skipped=0 | Docker 内网数据源（ds#4）；物化节点 file_sync；目标表数据验证一致 | 2026-09-28 |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
