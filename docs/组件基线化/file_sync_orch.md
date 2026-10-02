# 文件同步编排（C31）· type=`file_sync_orch`

> 基线化设计册 · 分组：M-B1 同步类 · 状态：⏳ 1.9 实测通过（待认可发 v1）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写。

## 1. 语义分析

**执行模型**：模板组件（`TEMPLATE_TYPES`）——落图即展开，无独立运行时路由。
**展开语义**：参考源表基准：开始 → 前置清理 → 端点选择(文件源) → 字段映射-复制 → 条件设定 → 对账校验 → 结束（对账不通过 → 消息通知）。展开链构建函数 `buildFileSyncChain`。
**与 src_base 的差异**：endpoint_select 初始 baseMode=file_sync（文件源配置区）；运行态执行节点为 file_sync（C24）而非 sync。
**基线化核心工作**：同决策 8——`build` 函数声明化为 template.chain 纯数据模板 DSL。

## 2. 八项表单规格（草案）

### params / inputs / outputs / conditions / constraints / exclusions / refs / exports

全部为空（模板组件无配置表单）。

### template（声明式展开链）

```json
{
  "modes": [{
    "key": "file_sync",
    "label": "文件同步",
    "desc": "CSV/TXT/Excel 文件 → 库表入仓，字段复制映射 + 筛选条件",
    "chain": {
      "nodes": [
        {"id": "n_start", "type": "start"},
        {"id": "n_cleanup", "type": "shell", "data": {"name": "前置清理"}},
        {"id": "n_endpoint", "type": "endpoint_select", "data": {"baseMode": "file_sync"}},
        {"id": "n_fmap", "type": "field_map"},
        {"id": "n_cond", "type": "condition_set"},
        {"id": "n_assert", "type": "assert"},
        {"id": "n_end", "type": "end"}
      ],
      "edges": [
        {"source": "n_start", "target": "n_cleanup"},
        {"source": "n_cleanup", "target": "n_endpoint"},
        {"source": "n_endpoint", "target": "n_fmap"},
        {"source": "n_fmap", "target": "n_cond"},
        {"source": "n_cond", "target": "n_assert"},
        {"source": "n_assert", "sourceHandle": "success", "target": "n_end"}
      ]
    },
    "hooks": {"assertFailNotify": "消息通知节点接入位（对账不通过）"}
  }]
}
```

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form: [] | 八段全空 | 平移 |
| `template.modes[].build` 函数 | template.chain 声明式链 | 决策 8 |
| `summary` 常量函数 | render.summaryRules 兜底模板 | 决策 2 |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：template.chain 声明式展开链（决策 8），nodes=7 edges=6；链结构：start → shell（前置清理）→ endpoint_select(baseMode=file_sync) → field_map → condition_set → assert → end；与 src_base 差异：endpoint_select 初始 baseMode=file_sync（文件源配置区），运行态执行节点为 file_sync（C24）而非 sync；build 函数退役；summary 迁移至 render.summaryRules。

**后端**：零改动，template 节点落图即展开。

**体检**（10 项全过）：contract=template 豁免 executor；八段全空合规；chain 可序列化；血缘豁免。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

模板组件不执行：血缘豁免。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| 代码审查 | buildFileSyncChain 展开逻辑 | ✅ 展开链=start→sql(前置清理)→endpoint_select(file_sync,filePath=samples/orders_part.csv)→field_map→condition_set→assert→end+notify，与 template.chain 声明一致 | 前端展开函数实现正确；展开后节点链运行时行为同普通节点链（已验证 file_sync 5 行 CSV 入仓） | 2026-09-28 |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
