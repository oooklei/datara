# FE-20 门 8「试运行和正式运行行为验收通过」— 用例设计

> 任务：c28-fe-xcut ｜ FE-20（G 门禁验收）｜ 前置：门 1-7 全解阻 + 1.9 环境授权（未满足，用例设计先行）
> 依据：WBS `docs/increments/2026-10-19-WBS-前端融合任务分解.md` FE-20 行；设计 §4.1/§10 门 8
> 八能力源：设计 §4.1（L152-170）

---

## 一、八能力行为验收用例设计

### 1.1 八能力清单（设计 §4.1）

| # | 能力 | 行为描述 | 验收用例 | 正式页锚点 |
|---|---|---|---|---|
| 1 | 当前草稿运行 | 草稿 → 静态校验 → 草稿快照 → TRIAL 实例 → 执行 | `gate8-behavior.spec.ts` 能力1 | `/dag?tab=edit` → RunDialog |
| 2 | 单节点运行 | 选择单节点执行 TRIAL | 能力2 | RunDialog 单节点选项 |
| 3 | 从指定节点运行 | 选择起始节点执行 TRIAL | 能力3 | RunDialog 指定节点选项 |
| 4 | 测试变量覆盖 | 运行时可覆盖变量值 | 能力4 | RunDialog 变量覆盖输入 |
| 5 | 依赖模拟 | 模拟依赖节点执行结果 | 能力5 | RunDialog 依赖模拟选项 |
| 6 | Dry Run | 干跑模式（不实际执行） | 能力6 | RunDialog Dry Run 选项 |
| 7 | SQL 预检查 | 执行前 SQL 语法/语义预检 | 能力7 | RunDialog SQL 预检选项 |
| 8 | 结果转正式版本 | TRIAL 结果 promote 为正式版本 | 能力8 | `/dag/instances` 转正式按钮 |

### 1.2 正式运行行为

| 行为 | 描述 | 验收用例 |
|---|---|---|
| 已发布版本运行 | 已发布版本 → FORMAL 实例 → 调度/手工运行 | 门8 能力1（同一入口，instance_type 区分） |
| instance_type 三态 | TRIAL/FORMAL/STREAM 枚举 UI | `gate8-behavior.spec.ts` TRIAL/FORMAL 语义回归 |
| CANCELLED/CANCEL_FAILED 终态 | 1.9 实测 | 待 1.9 授权后补充 |

### 1.3 重试/恢复回归用例

| 用例 | 描述 | 测试文件 |
|---|---|---|
| RESUME_FROM 命令链路 | 失败实例恢复命令提交 | `retry-recovery.spec.ts` 恢复命令链路 |
| 恢复命令提交确认 | 恢复后提示 commandId | `retry-recovery.spec.ts` 恢复命令提交 |
| 重试预算展示 | retry_budget/retry_deadline 持久化 | `retry-recovery.spec.ts` 重试预算展示 |
| vitest 回归 | resume-from API 调用链路 | `src/__tests__/gate8-behavior.test.ts` |

## 二、用例文件清单

| 文件 | 类型 | 状态 | 说明 |
|---|---|---|---|
| `e2e/gate8-behavior.spec.ts` | Playwright | 就绪 | 八能力行为验收（8 用例 + 1 语义回归） |
| `e2e/retry-recovery.spec.ts` | Playwright | 就绪 | 重试/恢复回归（3 用例） |
| `playwright.config.ts` | 配置 | 就绪 | Playwright 配置（baseURL/headless/trace） |
| `src/__tests__/gate8-behavior.test.ts` | vitest | 可跑 | 回归测试（resume-from API 链路） |

## 三、验收标准对照（WBS FE-20）

| WBS 验收标准 | 本设计覆盖 |
|---|---|
| 八能力行为 Playwright 逐项通过 | §1.1 八能力用例（8 项） |
| 重试/恢复回归全绿 | §1.3 重试/恢复用例（Playwright 3 + vitest 1） |
| 全链执行证据归档 | 待 1.9 实测后归档 `docs/increments/evidence/` |

## 四、执行边界

- 本设计仅用例设计，**实测待门 1-7 全解阻 + 1.9 环境授权**；
- Playwright 用例当前 `test.skip(!process.env.DATARA_API_BASE_URL)`——无 1.9 环境时自动跳过，不产生假失败；
- vitest 回归测试（`src/__tests__/gate8-behavior.test.ts`）当前可跑，覆盖 resume-from API 调用链路；
- 文件域：`datara-web/e2e/`（Playwright 用例）、`datara-web/src/__tests__/`（vitest 回归）、`datara-web/playwright.config.ts`（配置）。

---

*产出：Claude 实施线 c28-fe-xcut；日期：2026-10-19；状态=用例设计冻结，待门 1-7 解阻 + 1.9 授权后实测。*
