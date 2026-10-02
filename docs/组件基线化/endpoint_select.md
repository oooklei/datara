# 端点选择（C37）· type=`endpoint_select`

> 基线化设计册 · 分组：M-B1 同步类 · 状态：⏳ 1.9 实测通过（待认可发 v1）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写。

## 1. 语义分析

**执行模型**：直通配置节点（`PASSTHROUGH_TYPES`，自身不执行，配置被 master 运行态物化消费）。
**配置流向**：画布存在 endpoint_select 时，`materialize_sync_exec`（master/engine.py:50）在 assert 入边处物化 `sys_exec_` 执行节点；按 `baseMode` 分拣执行类型（src_base/tgt_base → sync，file_sync → file_sync），并注入 `componentRef {type: endpoint_select, version: published}`（D2 §9.6）。直通链配置在派发时拍平进执行节点 param。
**worker 消费键**（executors/sync.py:326）：`srcDs→readerDs`、`srcTable→readerTable`、`tgtDs→writerDs`、`tgtTable→writerTable`、文件区 `filePath/fileType/...→readerFile|readerPath`。
**三分型**：src_base（源端选表+目标端选实例）/ tgt_base（目标端选表+源端探测）/ file_sync（文件源+目标端）。
**现状缺口**：21 个表单字段中 13 个带 `showIf` 函数；`tgtTable` 双 key 同名分型（required 互斥切换）；`summary` 为函数（依赖 baseMode 分型）。

## 2. 八项表单规格（草案）

### params（16 项，全部配置参数）

| key | label | uiType | required | default | options / cap | 说明 |
|---|---|---|---|---|---|---|
| baseMode | 基准类型 | select | ✓ | src_base | src_base=源表基准 / tgt_base=目标表基准 / file_sync=文件同步 | 决定源端形态与目标表是否必选 |
| srcDs | 源数据源 | resource | ✓ | — | cap: datasource mysql/greatdb | |
| srcTable | 源表 | resource | ✓ | — | cap: table dsKey=srcDs writeAs=schemaTable | |
| probe | 联动探测匹配表 | bool | | false | | 选定目标表后探测源实例各 schema 匹配表 |
| matchType | 匹配规则 | select | | exact | exact=完全同名 / prefix=前部分命名相同 | |
| matchPrefix | 匹配前缀 | text | | | | 留空=目标表名 |
| probeResult | 参与 schema/表 | text | | | | 逗号分隔，留空=探测全部匹配 |
| filePath | 文件路径 | text | ✓ | | | /datara/files 相对 |
| fileType | 文件类型 | select | | csv | csv/txt/excel | |
| fileDelimiter | 分隔符 | text | | , | | |
| fileEncoding | 编码 | select | | utf-8 | utf-8/gbk/gb18030 | |
| fileHeaderRows | 表头行数 | number | | 1 | | 0=无表头 |
| fileSheet | Sheet 名称 | text | | | | 留空=首个 |
| tgtDs | 目标数据源 | resource | ✓ | — | cap: datasource mysql/greatdb | |
| tgtTable | 目标表 | resource | 条件必选 | | cap: table dsKey=tgtDs writeAs=schemaTable | **单字段化**（见 §3 决策 1） |
| autoCreate | 目标表不存在则新建 | bool | | true | | 按源表/文件表头结构创建 |

### outputs（2 项，具名输出端口声明）

| key | label | 说明 |
|---|---|---|
| sourceRef | 源端表 | 下游 field_map/field_map_union 按端口语义引用 |
| targetRef | 目标端表 | 同上 |

### conditions（条件可见性，10 条，替代全部 showIf 函数）

| id | when | show |
|---|---|---|
| c-src-ds | baseMode ≠ file_sync | srcDs |
| c-src-table | baseMode = src_base | srcTable |
| c-probe | baseMode = tgt_base | probe |
| c-match | baseMode = tgt_base ∧ probe = true | matchType |
| c-prefix | baseMode = tgt_base ∧ probe ∧ matchType = prefix | matchPrefix |
| c-probe-res | baseMode = tgt_base ∧ probe = true | probeResult |
| c-file-path | baseMode = file_sync | filePath, fileType, fileHeaderRows |
| c-file-txt | baseMode = file_sync ∧ fileType ≠ excel | fileDelimiter, fileEncoding |
| c-file-xls | baseMode = file_sync ∧ fileType = excel | fileSheet |
| c-tgt | （恒显示，src/base 两分型见 constraints） | tgtDs, tgtTable, autoCreate |

### constraints（2 条）

| field | type | value | msg |
|---|---|---|---|
| tgtTable | requiredIf | baseMode = tgt_base | 目标表基准：目标表必选 |
| srcTable | requiredIf | baseMode = src_base | 源表基准：源表必选 |

### exclusions / refs / exports / inputs

均空。无变量引用域；无血缘（直通节点不执行，豁免注记）。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| 21 个 form 字段（13 个 showIf 函数） | params 16 项 + conditions 10 条 | showIf 全部消灭 → conditions 声明 |
| `tgtTable` 双 key 同名分型（required 两态互斥 showIf） | 单字段 + constraints.requiredIf | **决策 1**：八段同段 key 唯一，required 两态用 requiredIf 表达 |
| `outputs: [sourceRef, targetRef]` 静态端口 | outputs 段 2 项 | 平移 |
| `summary: (d) => 分型拼接` 函数 | render.summaryRules（草案） | **决策 2**：summary 声明为分型模板规则数组，M-B1 实现时随 baselineSpec 类型统一落地 |
| group/groupHint（同步基准/源端/文件源/目标端） | 字段 group 属性平移 | 平移 |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：
- 八段 DSL 声明（inputs=0 / outputs=2 / params=16 / conditions=9 / constraints=2）
- 消灭全部 13 个 `showIf` 函数 → conditions 声明（纯数据）
- tgtTable 单字段化（决策 1：双 key 同名分型 → 单字段 + constraints.requiredIf）
- summary 声明化为 render.summary 字符串（决策 2）

**后端**：零改动。passthrough 节点无 executor，materialize_sync_exec 消费键不变。

**体检**（10 项全过）：pure_data ✓ / form_whitelist ✓ / drop_policy ✓ / contract ✓（passthrough 豁免 executor）/ catalog_consistency ✓ / references ✓ / lineage_decl ✓（逻辑控制类豁免）/ exports_consistency ✓ / permission ✓ / draft_lock ✓

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

直通配置节点，不执行：血缘豁免（lineage_decl 体检项报「逻辑控制类豁免」）。运行态血缘由 sys_exec 节点（sync/file_sync）落库。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| wf=97 v5 | endpoint_select → sys_exec_c6bdbfe4（sync 物化） | ✅ state=success，config 输出 srcDs=9/tgtDs=4/baseMode=src_base | 直通节点配置拍平进执行节点；同步 250K 行实测通过 | 2026-09-28 |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
