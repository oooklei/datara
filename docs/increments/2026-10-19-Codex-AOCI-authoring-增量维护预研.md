# AOCI authoring 增量维护策略预研（只读）

日期：2026-10-19
编制线：Codex
派单锚：监督员消息 #a9c8ab9d；STATE S31/S32
状态：只读预研；未调用任何 aoci_* 工具，未修改 .aoci/config.json，未执行 preview、apply、maintain 或 authoring。

## 1. 已核对事实

- 当前配置中启用规则共 11 条：既有 .agents、.claude 两项，加本轮新增的 9 项排除：docs/increments、datara-backend/tests、datara-web/tests、datara-web/src/__tests__、docs/组件基线化、docs/archive、prototype、datara-web/deploy、release。
- 当前 whole_index 预算为 target=150000、warning=220000、max=300000 tokens；配置还含 R/S 分层预算，本预研不调整它们。
- STATE S31 记录过先前一次 scope apply 已成功且 stage 到 authoring_required。监督员本轮派单说明，以上新增瘦身配置尚未 apply，旧 preview 已过期；因此不能把 S31 的 stage 或旧 preview 当成本轮新配置的预演结果。
- 当前 authoring_targets 数量和删减比例尚无新机读 preview 证据。预期会下降只是待验证假设，不作为批次规划基数。
- 只读核对命令：`rtk python -c "import json; from pathlib import Path; d=json.loads(Path('.aoci/config.json').read_text(encoding='utf-8')); rules=d['managed_scope']['rules']; new=[r['pattern'] for r in rules if r.get('enabled') and r['rule_id'] not in ('exclude-agents-dir','exclude-claude-dir')]; b=d['cognition_budget']['whole_index']; print('enabled_rules_total',sum(1 for r in rules if r.get('enabled'))); print('new_excludes',len(new),','.join(new)); print('whole_index',b)"`
- 输出定位：本轮终端。输出为 11 条启用规则、9 条新增排除，以及 whole_index 150000/220000/300000；未保存整段终端日志。配置位置：`.aoci/config.json:43-235`；历史阶段依据：`docs/handoff/STATE.md` S31。

## 2. 建议的增量维护路径

1. **先冻结变更输入并重开预演。** AOCI 守护线在全仓静默窗口内，以当前已审阅配置生成新的 preview；过期 preview 不复用。确认预演绑定的配置/范围摘要与当前 9 条新增排除及预算一致，再读取机器给出的移除数、比例、authoring_targets 和审批状态。若范围偏离、影响未批准对象，或触发 review/approval 闸，停在闸前报监督线，不推测目标数，也不先 apply。
2. **只由监督线执行 scope apply。** apply 成功后保存事务回执及机器状态，明确区分本轮 scope 变更和 S31 旧事务。仅在当前机器状态明确要求 authoring 时进入下一步；preview 生成、审批及 apply 均不由 Codex 实施线代办。
3. **让当前 Plan/Guide 产生维护候选。** 监督线按当时的实时 Guide 和工具返回推进；本预研不固定或重建其状态机。每个候选的语义由 Host 模型结合绑定的源码和必要证据独立撰写，不从路径、文件名、AST 或固定模板推断。
4. **按机器批次完整提交并续办。** 对每个机器签发批次，保留 candidate_id、source_sha256、domain/batch identity；完整提交当批候选，遵守工具的原子事务上限，不自行截断或拆分机器批次。若返回 remaining，成功 Apply 后重新 Maintain，从新的前像继续，直到机器不再返回剩余项。
5. **证据不足时转 follow-up。** 不猜标签或 F/R/A/S；使用当前布局支持的 report/follow-up 路径，让监督线补证或裁定。repair_required 只修复机器明确指出的候选，然后仍提交该批完整集合；third-party bytes、CAS 或 Recovery 冲突时停止并留证。
6. **按独立状态收口。** 监督线记录维护批次完成、范围/治理对齐和 strict Attestation 的机器事实。不得把候选批次完成误报成治理对齐，也不得把 strict Attestation 失败直接写成模型完全不理解。对齐后不重复维护；是否需要普通 Overview 由下一阶段任务决定。

## 3. 角色边界与静默闸

- 监督线守护会话拥有 AOCI 全流程，负责实时 Guide、preview/apply、维护、语义更新、Recovery 和最终对齐。Codex 只提供本预研、核对监督线引用的证据及复评文档；不得调用 aoci_*，不得修改 `.aoci`、索引或元数据，也不承担 AOCI 启动认知检查/维护义务。
- 静默窗口仅用于监督线执行获批的范围事务；窗口前停止所有相关循环并确认没有在飞写入，apply 完成后由监督线确认新状态、重启循环并派发任务。旧 preview 过期时必须重新预演，不能通过重启循环绕过闸门。
- 若监督线需要实施线帮助，派发具体、只读、证据边界清晰的检查或复评单；本预研不创建子任务、不触发后台 AOCI 操作。

## 4. 风险与决策点

- **排除 docs/increments 的可追溯性：** 配置将历史增量日志排除在 active cognition volume 外。handoff 指示当前事实转由 docs/handoff 承载；需要进入下一轮工作的关键事实应先摘要到 handoff，不能假设 excluded increments 仍会进入 AOCI cognition。
- **预期缩减量未验证：** 9 个排除与预算收紧会改变候选集合及成本，但当前没有新的 preview 输出，故暂不报告预计条目数、百分比或批次数。
- **范围审批阈值：** preview 应对照配置中的 review_required 和 entry removal 数量/比例门槛；达到审批状态时等待监督线裁定，不用预算阈值替代审批闸。
- **依赖机器结果：** 维护批次数量、每批上限、candidate schema 和下一步状态以本轮实时 Plan/Guide/工具输出为准。此文是执行前策略预研，不能代替这些输出或作为执行授权。

## 5. 交付与验证

- 交付范围仅本文；未修改 `.aoci/config.json`、aoci.code.txt、索引、业务代码或远端。
- 只读核对命令及输出定位见 §1；本轮为策略文档，不运行测试。
- 下一单：监督线复评本预研；AOCI 具体操作仍待监督线另行开启静默窗口并按届时机器输出推进。P2-3 设计复评待 Claude 提交文档后由 Codex 接单。
