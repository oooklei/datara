# 字条：门 1 根因修复已落地 D 盘主检出 → 请移植到 c63c 并续作（致 Codex）

| 项 | 值 |
|---|---|
| 时间 | 2026-10-26（用户侧写于 D 盘主检出） |
| 发件 | Trae（D 盘主检出 `D:\需求\数据治理工具\Datara`，`main` @ `217043c7` + 工作树未提交改动） |
| 收件 | Codex（worktree `C:\Users\Administrator\.codex\worktrees\c63c\Datara`，分支 `codex/datara-target-completion` @ `d880a5f5`） |
| 关联 | 本报告 `docs/qa/2026-10-26-M3-八门核验收口报告.md`（根因/证据全文）；既有交接单 `docs/handoff/2026-10-26-前端融合纳入-交接-codex.md` 继续有效 |
| 回执 | 完成后写八字段回执 JSON 至本目录 |

---

## 0. 本轮结果（D 盘主检出实跑，非采信日志）

| 门 | 判据 | 实跑 | 结论 |
|---|---|---|---|
| 门 1 后端全量 pytest | 0 fail | **2598 passed / 8 skipped / 0 failed**（884.90s） | PASS |
| 门 2 前端 vitest | ≥ 基线 | **102 files / 854 tests passed**（21.88s） | PASS |
| 门 3 vue-tsc | EXIT=0 | `VUE_TSC_EXIT=0` | PASS |
| 门 8 红线本地可判项 | R1~R7 | R1/R2/R3/R4/R5/R6/R7 全 PASS | PASS |

门 1 修复前后 `2593 → 2598`，**恰好 +5**（= 原 5 处失败数），零回归。
门 4~7 仍阻塞于 1.9 远程环境，需用户提供。

---

## 1. 【P0 首要票】把门 1 修复移植到 c63c

### 1a. 问题

c63c HEAD `d880a5f5` 的 `datara-backend/tests/test_component_catalog.py` **仍是污染版**（`sys.modules.pop` 后无恢复）。
该文件在**收集期** pop 掉 `sys.modules['common.*']` 并由 `api.main` 重新 import 出**新模块对象**，导致同进程后续用例的 `from common import queue` 与既有绑定分裂成两个对象，`monkeypatch` 只命中其一而**静默失效** —— 表现为 `test_r8a_failover*` 5 处失败、连真实 Redis（本机无 Redis 容器）。

顺序依赖实证（同两文件对调收集顺序即一过一败）：

```
test_component_catalog.py → test_r8a_failover_fence.py : 1 passed
test_r8a_failover_fence.py → test_component_catalog.py : 1 failed (redis ConnectionError)
```

### 1b. 移植内容（唯一改动，17+/6−）

D 盘源文件（**已改好，直接整文件抄入 c63c 或按其 diff 重放**）：
`D:\需求\数据治理工具\Datara\datara-backend\tests\test_component_catalog.py`

改动位于 L36-55，把原来的

```python
for _n in [n for n in sys.modules if n == "common" or n.startswith("common.")]:
    sys.modules.pop(_n, None)

from api.main import create_app  # noqa: E402
```

替换为

```python
_saved_common = {
    n: m for n, m in sys.modules.items() if n == "common" or n.startswith("common.")
}
for _n in list(_saved_common):
    sys.modules.pop(_n, None)
try:
    from api.main import create_app  # noqa: E402
finally:
    for _n in [n for n in sys.modules if n == "common" or n.startswith("common.")]:
        sys.modules.pop(_n, None)
    sys.modules.update(_saved_common)
```

同步更新其上方注释块（说明第 3 步「导入后恢复 sys.modules 原视图」的理由）。
**未触碰任何生产代码**，`master/failover.py` / `common/queue.py` 一字未改。

### 1c. 验证（两验，缺一不可）

```powershell
cd C:\Users\Administrator\.codex\worktrees\c63c\Datara\datara-backend
python -m pytest tests -q -k "r8a" -p no:cacheprovider 2>&1 | Select-Object -Last 5
# 期望：88 passed, 1 skipped（修复前为 5 failed / 83 passed / 1 skipped）

python -m pytest tests -q -p no:cacheprovider 2>&1 | Select-Object -Last 5
# 期望：2598 passed, 8 skipped, 0 failed（约 15 分钟）
```

注意：本机 pytest **无 pytest-cacheprovider**，`--lf` / `--ff` 不可用。

---

## 2. 续作票（按优先级）

### 2a. T-B `views/open/` 双副本归一 —— **已裁定：方案 B（根目录为正本），可动**

用户 2026-10-26 裁定「按推荐裁定」，权威出处已写入 `docs/increments/2026-10-26-前端融合纳入与优化方案.md` §3 第 3 项（v1.2）。

执行要点（方案 B）：
1. 融合版增量并入根目录两视图 —— 正本 `views/ApiManagementView.vue`（5525B）/ `views/ApiKeyManagementView.vue`（5182B），融合增量来源 `views/open/`（9870B / 11657B）；
2. 删 `views/open/` 两副本（连带其空目录）；
3. 改 `feMergeB3Assets.contract.test.ts` 与 `COPY_LEDGER.md` 行号；
4. 三重验证：`npx vitest run`（不回退既有基线）+ `npx vue-tsc -b`（EXIT=0）+ `vite build`。

**§8 七条红线无一禁止重复副本**，故本项不阻塞放行门；但既已裁定，按上序执行即可。

退役页（沿用 §3 第 1/2 项，**已批**）：`views/LlmModelManagementView.vue`（平铺件）退役，`/open/llm` 路由改指融合 `views/system/llm-models/`；`views/SecAuditView.vue`（平铺件）退役，`/sec/audit` 路由不变。

### 2b. T-A 令牌化扫尾

M2b 两视图（`ApiKeyManagementView` / `ApiManagementView`）+ 其余 LIVE 页（12 文件）。
四验：hex 复扫 + `npx vitest run` + `npx vue-tsc -b` + `vite build`。
**未回退既有基线**：vitest 816 绿（c63c 口径）/ vue-tsc EXIT=0。

### 2c. P1 metrics 域迁移接入启动装配

`datara-backend/api/app.py` L420-428 启动装配缺 metrics 迁移挂载，新环境会复现 `workflow-result-stats` 500（1.9 上次为手工幂等执行迁移绕过）。

---

## 3. 纪律（不变，重申）

1. `.git` 只读不 commit 不 push，禁全部 `aoci_*`；提交由用户侧把关。
2. 按文件名精确 `git add`，**严禁 `-A` / `add .`**。
3. 三层 stash（`stash@{0}`/`@{1}`/`@{2}`）在 IdeView/LoginView 并集验证通过前**一律不 pop / 不 drop**，只许 `git show 'stash@{n}:<path>'` 只读提取。
4. 不写 `STATE.md` 与 `mailbox.jsonl`。
5. 单会话轮次 > 30 或配额 ≥ 80% 即收尾写回执，不硬撑。
6. 测试纪律见 `2026-10-26-codex-runtime-prompt.txt`：迭代期只跑目标文件，全量每票只在票尾跑一次，输出一律管道截尾。
7. **本字条与 `2026-10-26-codex-runtime-prompt.txt` 冲突时以后者为准**，并当场向用户报告冲突点。
