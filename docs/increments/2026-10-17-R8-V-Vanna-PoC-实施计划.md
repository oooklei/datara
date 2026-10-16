# R8-V Vanna PoC 实施计划（P1-0）

- **日期**：2026-10-17
- **性质**：实施计划（监督线起草，执行=Trae 线；依据监督线评审后可开工）。
- **依据**：[分阶段混合集成方案设计 §2/§3](2026-10-17-分阶段混合集成方案-设计.md)（D5 OpenAI 兼容/D7 锁版禁自动更新/D6 主权边界）+ 标准 v3（v4 转正后按 v4）+ R8-A 八工具契约 v1 + P1-1~P1-4 任务池定义。
- **门禁**：每步 TDD 红绿先行；验收=A1-A7 + 主权四条断言 + 成功判据全链路演示（§5）。

## 步骤 0 前置确认（开工闸）

1. K1（用户）LLM key 注入验证环境（环境变量，禁入库）——P1-3 联调前置，不阻塞步骤 1/2。
2. 文件域声明：`datara-backend/ai_copilot/`（全新目录）+ `pyproject.toml`（追加依赖）+ R8-B 测试页（前端验证域）。与 Phase 0 文件域零重叠。

## 步骤 1（P1-1）模块骨架+锁版+存储目录

- **TDD 红灯**：`tests/ai_copilot/test_skeleton.py` —— 断言模块可导入、适配层接口存在、chromadb 目录落点正确。
- 新增 `datara-backend/ai_copilot/__init__.py`、`adapter.py`（空壳签名）、`config.py`（读环境变量：`DATARA_AI_LLM_BASE_URL/API_KEY/MODEL`）。
- `pyproject.toml`：`vanna==<精确版本>`（vendor wheel 缓存+锁文件提交；禁止 `>=`/`~=`）；chromadb 固定版本同理。
- chromadb 数据目录：`datara-backend/data/ai_copilot/chromadb/`（纳入 Datara 数据区持久化约定，gitignore 数据文件只留 `.gitkeep`）。
- **验收**：红灯转绿；`pip install` 走锁文件可复现；依赖树无自动升级通道。

## 步骤 2（P1-2）vanna_adapter 适配层（主权四条）

- **TDD 红灯**：`tests/ai_copilot/test_adapter_sovereignty.py` —— 四条各一组用例：
  1. key 只从 `config.py` 环境注入路径流入，adapter 内无硬编码/默认 key；
  2. `generate_sql` 返回 SQL 文本，**不执行**；执行入口只接受经 R8-A 授权通道的 handler 注入；
  3. 上下文对象（user_id/project_id）必须显式传入，缺失即抛 `SovereigntyContextMissing`；
  4. 记忆读写（DDL/文档/SQL 样本）全部经 audit hook 落审计记录，存储仅指向步骤 1 目录。
- 实现 `adapter.py`：vanna 实例包装+四条实现；**vanna 类型不得泄漏出适配层签名**（对外仅 Datara 契约类型）。
- **验收**：四条用例全绿；`grep` 断言模块边界无 vanna import 泄漏（除 adapter.py）。

## 步骤 3（P1-3）R8-A 八工具对接

- **TDD 红灯**：`tests/ai_copilot/test_r8a_bridge.py` —— `generate_sql` 产出 SQL→经 Datara 只读授权校验→`run_sql` 走既有执行链路（复用 R8-A 契约 v1 签名，不另建执行引擎）。
- PoC 最小工具集：`generate_sql`/`run_sql`/`search_schema` 三工具打通即判 PoC 达标（其余五工具契约挂接、实现沿用既有 service）。
- **验收**：三工具契约测试绿；审计记录含 user/project/run_id 贯穿字段。

## 步骤 4（P1-4）R8-B 悬浮助手测试页+假 Agent 扩展

- 测试页扩展：自然语言输入→`generate_sql`→（授权确认）→`run_sql`→结果展示+解释。
- 假 Agent 测试：无 LLM 模式（mock 适配层）先行全绿，真实 LLM 模式作 P1-5 注入后联调。
- **验收**：无 LLM 模式全链路绿（隔离于 K1）；测试页挂 rebuild 验证路由并登记。

## 步骤 5 验收材料（交 P1-6 监督线评审）

1. A1-A7 门禁证据包（含 TDD 红绿时间线）。
2. 主权四条断言测试报告 + 跨项目隔离演示（两条 project 上下文互不可见）。
3. 成功判据演示：自然语言→SQL→经授权执行→结果解释 录屏/API 证据。
4. 锁版证明：`pip freeze` 快照+锁文件 diff 入 evidence。

## 纪律

- 心跳：每步完成 pathspec 提交+心跳通报；O7 诚实自评（未跑的不声称 GREEN）。
- 与 AOCI 守护写窗口互斥：守护开窗期间让行。
- 依赖 K1 的步骤 3/4 真实联调段若 key 未到位，转步骤 5 材料整理，不停整体推进。
