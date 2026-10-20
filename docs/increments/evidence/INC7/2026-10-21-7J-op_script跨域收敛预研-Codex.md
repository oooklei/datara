# 7J 第二票：`op_script` 跨 ETL/stream 收敛预研

- 日期：2026-10-21（Asia/Shanghai）
- 派单：`s242-ruling5` / `s243-901-15-accept`
- 性质：只读预研；未改 catalog、spec、profile、执行器或历史工作流

## 1. 冲突事实

`common/dag_catalog.json` 有 76 行但只有 75 个唯一 type，唯一跨 profile 重复项为 `op_script`：

| 维度 | ETL 行 | stream 行 | 结论 |
|---|---|---|---|
| type/executor | `op_script` / `op_script` | 同左 | 全局键碰撞 |
| schema 来源 | `profiles/shared.ts::opScriptSchema` | 同左 | 当前内容完全一致 |
| props | `scriptId/lang/code` | 同左 | 无 profile 特有字段 |
| palette | 可见，“脚本”组 | 隐藏（由 ETL profile 继承） | 重复来自 profile 组合，不是两套业务语义 |
| worker | `@register("op_script")` 单执行器 | 同左 | 运行时无法区分来源 profile |

`tests/test_component_catalog.py:189-201` 已把重复事实锁为测试基线；`shared.ts:4-5` 说明此前已通过共享常量消除了“两份 schema 漂移”，但 catalog 仍按 profile 展开为两行。

## 2. 为什么不能用 profile 复合键长期保留

治理模型 `common/models.py:632` 明确 `t_component.type` 全局唯一，版本表也以 `(type, version)` 唯一。工作流引用只有 `componentRef.type/version`，没有 profile 维度。发布、升级、下线和影响面扫描都不能表达“ETL 的 op_script”和“stream 的 op_script”是两个独立组件。

因此目录允许跨 profile 重复与治理/发布模型不一致。把唯一键改为 `(profile,type)` 会扩散到版本引用和历史图格式，且没有产品需求依据，不建议采用。

## 3. 实现质量与权威边界

`worker/executors/op_script.py` 虽注册了真实 executor 名称，但核心仍是 TODO：只校验 `scriptId/code`，记录语言后固定返回 `SUCCESS` 和 `processed_rows=0`，不会执行 SQL/Python/Shell。这不能作为保留组件的成熟度证据。

当前权威设计已经：

- 删除 ETL 工作流和 ETL 算子组件，以正式 SQL/Python/Shell 节点承载脚本逻辑；
- 流处理使用 C18/C19/C20 与 `page_board` 正式组件体系；
- 要求无出处组件经裁定从后端 spec 移除。

两条 `op_script` 均缺少当前逐组件权威出处，也不存在两个不同的业务语义需要合并。

## 4. 收敛方案评估

| 方案 | 评价 | 结论 |
|---|---|---|
| A. 保留一个全局 `op_script`，两个 profile 共享 | 消除重复，但保留无权威出处且实际不执行的组件 | 不推荐 |
| B. 改名为 `etl_op_script` / `stream_op_script` | 消除键碰撞，却制造两个无权威出处的新类型，并扩大历史迁移 | 拒绝 |
| C. type 唯一键改为 `(profile,type)` | 破坏治理模型和 `componentRef` 契约，影响面最大 | 拒绝 |
| D. 两处停止新建，历史引用分流迁移后退场 | 符合 ETL 删除和正式流组件收敛方向 | **推荐** |

## 5. 推荐执行顺序

1. **只读盘点**：导出现网 `t_component/t_component_version` 中 `op_script` 的 published 状态，并扫描所有工作流版本的 `componentRef.type=op_script`；同时读取节点 `lang/scriptId/code` 和工作流标签/profile。
2. **停止新增**：从可创建 palette/spec 白名单移除 `op_script`，历史版本仍只读解析；不得改写已 published 版本。
3. **按节点迁移**：
   - 普通/存量 ETL 图：`lang=SQL/Python/Shell` 分别迁移到正式 `sql/python/shell` 节点；逐项校准属性，不能只改 type。
   - 流图：没有可证明等价的正式脚本算子。存在引用时标记“人工重构”，由 C18/C19/C20 流链重新表达；禁止静默改成批式脚本节点。
   - `scriptId` 引用必须先解析脚本库内容和权限，不能丢成空内联代码。
4. **兼容窗口**：worker 旧执行器仅服务未迁移历史版本，并显式标为 deprecated；鉴于当前执行器固定空成功，正式运行应 fail closed 或阻止新发布，不能继续伪成功。
5. **最终移除**：现网新建数为零、历史引用完成迁移/豁免后，删除两个 profile 展开项、`WORKER_TYPES` 与 executor 注册，再把原“重复存在”测试改为“跨 profile 无重复”。

## 6. 验收锚

- catalog 的 `crossProfileDuplicateTypes` 不再包含 `op_script`；
- `t_component.type` 全局唯一契约保持不变；
- 新工作流不能创建或发布 `op_script`；
- 历史 ETL 引用逐节点迁移到正式三脚本组件，属性和执行结果有回归；
- 历史 stream 引用全部人工处置，不发生静默语义降级；
- 不再出现固定 `SUCCESS/processed_rows=0` 的假执行路径。

## 7. 结论

该冲突是“同一共享 schema 被两个历史 profile 展开”的目录重复，并非两种同名业务能力。推荐方案为 **停止新增 + 按历史引用分流迁移 + 最终同时退场**，不改全局唯一键、不通过改名制造新组件。执行仍需现网只读引用快照作为硬前置，本预研不授权直接删除。
