# 在飞件原子提交单元表 + pathspec 固化建议（F8 形态第三例实证）

- **性质**：Claude 实施线对当前 worktree **未提交在飞件**做只读依赖扫描与提交原子性实证，落实冻结令 **裁定①**「pathspec 固化建议登记（后续 rebuild 后端提交显式 pathspec 防混载）」
- **日期**：2026-10-21
- **触发**：裁定① 要求登记 pathspec 固化建议；本线在全量复跑（1F 已知）之外，独立扫描在飞件的**跨文件提交耦合**，发现三处**顶层导入未跟踪模块**的 F8 形态风险（笔16/`640f2ab` app.py、`ddlparser.py` 之后第三例）
- **边界**：只读扫描 + HEAD 导出叠加实证；**零业务代码改动**；`.git` 只读未 push；未调用 `aoci_*`；未触碰他线在飞件

---

## 一、结论

| # | 形态 | 实证 | 严重度 |
|---|---|---|---|
| **H1** | M 态模块**顶层导入**未跟踪模块，单提交即 `ModuleNotFoundError` | **3 文件 / 实测**；其中 `app.py` 单件即阻断 **5** 个目标 | ★★★ 全量红 |
| **H2** | `app.py` 惰性导入 `execution.api`，而后者顶层导入 `run_stats`；`create_app()` 即失败 | 由 H1 链式（`app.py:1091`） | ★★★ 全 API 测试红 |
| **H3** | M 态模块**惰性**导入未跟踪模块，仅运行到该路径才失败 | **1 处，已实测**（`trial/runner.py:179`，导入 OK） | ★ 运行期 |
| **H4** | **HEAD-clean 测试**钉住 M 态模块的旧契约 → 即当前全量 **1F** | 已知（s316/s330/s331） | ★★ 全量 1F |
| **H5** | 未跟踪/M 态测试钉住 M 态模块新行为，单提交测试 → HEAD 中失败 | 9 条边（同票内） | ★★ 测试红 |

> **核心新增（H1/H2）**：当前 `api/app.py`（M 态，14 hunk / +261）**顶层导入 5 个未跟踪目标**——`rebuild.component_spec.migrations`、`rebuild.runtime_node`、`rebuild.runtime_node.models`、`rebuild.llm`、`rebuild.llm.migrations`（后四者指向**整个未跟踪包** `rebuild/llm/`、`rebuild/runtime_node/`）。因 `app.py` 是**全库装配件**，任一票单独提交 `app.py` 而不带这些未跟踪件，**HEAD 立即全量 ImportError**。这正是裁定① 要防的「混载」，且已可实测。
>
> **口径勘误（v1.1）**：v1 曾据「`.py` 后缀过滤的未跟踪清单」得出「10 个未跟踪文件、app.py 仅阻断 1 个目标」。**该过滤漏掉了 git 以目录形态上报的未跟踪包**（`?? datara-backend/rebuild/llm/`）。按 `--untracked-files=all` 展开，未跟踪文件实为 **30 个**，含 3 个整包。v1.1 已更正（见 §三.1、§四、§八）。

---

## 二、实证方法（HEAD 导出 + 单件叠加）

```
git archive HEAD datara-backend | tar -x -C /tmp/hc          # 只读导出 HEAD
cp <worktree 的某个 M 态文件> /tmp/hc/<同路径>                 # 仅叠加该单件
cd /tmp/hc/datara-backend && python -c "import <对应模块>"     # 观察是否可导入
```

原理：若某 M 态文件在**顶层**导入了一个**未跟踪**（HEAD 中不存在）的模块，则「HEAD + 仅该件」必然导入失败；反之（惰性导入 / 依赖在 HEAD 中）则导入成功。

---

## 三、实证结果

| 叠加件（M 态） | 导入目标 | 导入位置 | 结果 |
|---|---|---|---|
| `rebuild/api/app.py` | `rebuild.component_spec.migrations` | **顶层** `app.py:24` | ❌ `ModuleNotFoundError: No module named 'rebuild.component_spec.migrations'` |
| `rebuild/execution/api.py` | `rebuild.execution.run_stats` | **顶层** `execution/api.py:29` | ❌ `ModuleNotFoundError: No module named 'rebuild.execution.run_stats'` |
| `rebuild/execution/migrations.py` | `rebuild.execution.revisions.v0002_run_statistics` | **顶层** `migrations.py:9` | ❌ `ImportError: cannot import name 'v0002_run_statistics' from 'rebuild.execution.revisions'` |
| `rebuild/trial/runner.py` | `rebuild.execution.run_stats` | **惰性** `runner.py:179` | ✅ `IMPORT OK`（惰性，仅运行到该分支才失败） |

原始输出（节选）：

```
File ".../rebuild/api/app.py", line 24, in <module>
    from rebuild.component_spec.migrations import apply_component_spec_migrations
ModuleNotFoundError: No module named 'rebuild.component_spec.migrations'

File ".../rebuild/execution/api.py", line 29, in <module>
    from rebuild.execution.run_stats import RunStatisticsService
ModuleNotFoundError: No module named 'rebuild.execution.run_stats'

File ".../rebuild/execution/migrations.py", line 9, in <module>
    from rebuild.execution.revisions import v0001_execution_tables, v0002_run_statistics
ImportError: cannot import name 'v0002_run_statistics' from 'rebuild.execution.revisions'
```

**H2 链式**：`app.py:1091` 在 `create_app()` 内惰性 `from rebuild.execution.api import build_execution_router`；`execution/api.py:29` 顶层导入 `run_stats`。⇒ 即使 `import rebuild.api.app` 不触发，**`create_app()` 也会失败**（所有经 `create_app` 构造 app 的 API 测试全红）。

### 3.1 未跟踪件全量清单（v1.1 更正：按 `--untracked-files=all` 展开，共 30 件）

> **v1 口径缺陷**：v1 以 `git status --porcelain | 过滤 .py` 枚举未跟踪件，**漏掉 git 以目录形态上报的整包**（`?? datara-backend/rebuild/llm/`）。更正后未跟踪文件实为 **30 个**，含 **3 个整包**：

| 整包（未跟踪） | 文件数 | 内容 |
|---|---|---|
| `rebuild/llm/` | 9 | `__init__.py`/`api.py`/`crypto.py`/`migrations.py`/`models.py`/`provider.py`/`repository.py`/`resolver.py` + `revisions/{__init__,v0001_llm_model}.py` |
| `rebuild/runtime_node/` | 7 | `__init__.py`/`api.py`/`migrations.py`/`models.py`/`service.py`/`sftp.py` + `revisions/{__init__,v0001_runtime_node_registry}.py` |
| `rebuild/component_spec/revisions/` | 2 | `__init__.py`/`v0001_component_catalog.py` |

零散未跟踪件：`rebuild/component_spec/migrations.py`、`rebuild/execution/revisions/v0002_run_statistics.py`、`rebuild/execution/run_stats.py`，及 7 个测试件（`test_ai_tools_production_handlers`/`test_component_spec_migrations`/`test_execution_run_statistics`/`test_llm_api_and_resolver`/`test_llm_model_and_crypto`/`test_model_lineage_edge_shape_a`/`test_runtime_node_api`）。

### 3.2 闸门实测（`pathspec_gate.py`，见 §六）

```
$ python pathspec_gate.py datara-backend/rebuild/api/app.py
BLOCK: 顶层导入目标既不在提交集、也不在 HEAD：
  rebuild/api/app.py -> rebuild.component_spec.migrations  (期望文件 rebuild/component_spec/migrations.py)
  rebuild/api/app.py -> rebuild.runtime_node               (期望文件 rebuild/runtime_node.py)
  rebuild/api/app.py -> rebuild.runtime_node.models        (期望文件 rebuild/runtime_node/models.py)
  rebuild/api/app.py -> rebuild.llm                        (期望文件 rebuild/llm.py)
  rebuild/api/app.py -> rebuild.llm.migrations             (期望文件 rebuild/llm/migrations.py)
exit=1

$ python pathspec_gate.py datara-backend/rebuild/execution/api.py
BLOCK: ... rebuild/execution/api.py -> rebuild.execution.run_stats
exit=1

$ python pathspec_gate.py datara-backend/rebuild/execution/migrations.py
BLOCK: ... rebuild/execution/migrations.py -> rebuild.execution.revisions.v0002_run_statistics
exit=1

$ python pathspec_gate.py datara-backend/rebuild/trial/runner.py           # 惰性 → 放行
OK: ...                                                          exit=0
```

⇒ **`app.py` 单件提交即阻断 5 个目标，其中 4 个指向两个整包**；`execution/api.py` 阻断 1；`execution/migrations.py` 阻断 1（**名称级**：`revisions` 包在 HEAD，但 `v0002_run_statistics` 子模块不在）；`trial/runner.py` 因惰性导入**放行**（但运行到该分支仍会失败，须与同票新件同批，见 §四 Unit ②）。

> **闸门实现要点（v1.1）**：名称级检查不可省——`execution/migrations.py:9` 的 `from rebuild.execution.revisions import … v0002_run_statistics`，其**包路径在 HEAD 中**，仅路径级检查会漏判（实测：v1 首版闸门在此**误放行**，与 §三 的 HEAD 叠加实证矛盾；已修正）。另：行首缩进须用 `[ \t]*` 而非 `\s*`——`\s*` 会吞掉前置空行的换行符，使顶层导入被误判为惰性（实测：同样导致误放行）。

---

## 四、原子提交单元表（据依赖边推导）

> 每行 = **必须同批提交**的最小集合；`NEW`=未跟踪新文件，`M`=已改，`HEAD-clean`=HEAD 干净但**必须随票改**。

### Unit ① component_spec migrations（CD-C17-03，s333 已 PASS）
- `NEW` `rebuild/component_spec/migrations.py`
- `NEW` `rebuild/component_spec/revisions/__init__.py`、`v0001_component_catalog.py`
- `NEW` `tests/rebuild/test_component_spec_migrations.py`
- `M` `tests/rebuild/test_component_spec_api.py`
- `M` **`rebuild/api/app.py`**（`:24` 顶层 import、`:363` 调用、`:1057` router mount）★共享窗

### Unit ② execution 运行统计（inc8.2，即 s330/s331 所称「r9 扩表」）
- `M` `rebuild/execution/models.py`（`EXECUTION_TABLES` 6→8：`workflow_run_stat`/`workflow_run_reconcile_detail`）
- `M` `rebuild/execution/migrations.py`（`:9` 顶层 import `v0002_run_statistics`；`:22-24` 用 `EXECUTION_TABLES[-2],[-1]` **位置索引**，与 models.py 顺序强耦合）
- `NEW` `rebuild/execution/revisions/v0002_run_statistics.py`
- `NEW` `rebuild/execution/run_stats.py`
- `M` `rebuild/execution/api.py`（`:29` 顶层 import `run_stats`）
- `M` `rebuild/trial/runner.py`（`:179` 惰性 import `run_stats`）
- `NEW` `tests/rebuild/test_execution_run_statistics.py`
- `M` `tests/rebuild/test_execution_api.py`
- `M` `tests/rebuild/test_execution_migrations.py`
- **`HEAD-clean` `tests/rebuild/test_execution_models.py`**（`:18-25` 钉死 6 表 ⇒ **须改为 8 表**，否则 HEAD 全量 1F）★r9 责任线
- `M` **`rebuild/api/app.py`**（execution router mount）★共享窗

### Unit ③ ai_tools
- `M` `rebuild/ai_bridge.py`、`M` `rebuild/ai_tools.py`
- `NEW` `tests/rebuild/test_ai_tools_production_handlers.py`

### Unit ④ governance（含 i22 importer）
- `M` `rebuild/governance/api.py`、`M` `tests/rebuild/test_governance_api.py`
- `M` `rebuild/governance/legacy_i22_importer.py`、`M` `tests/rebuild/test_governance_legacy_i22_preview_api.py`

### Unit ⑤ identity
- `M` `rebuild/identity/repository.py`、`M` `tests/rebuild/test_identity_api.py`

### Unit ⑥ resources
- `M` `rebuild/resources/api.py`、`M` `rebuild/resources/repository.py`、`M` `tests/rebuild/test_r4_resources_api.py`

### Unit ⑦ trial
- `M` `rebuild/trial/runner.py`、`M` `rebuild/trial/validator.py`、`M` `tests/rebuild/test_trial_validator.py`

### Unit ⑧ llm（整包，未跟踪）
- `NEW` **整包** `rebuild/llm/`：`__init__.py`、`api.py`、`crypto.py`、`migrations.py`、`models.py`、`provider.py`、`repository.py`、`resolver.py`、`revisions/{__init__,v0001_llm_model}.py`（9 件）
- `NEW` `tests/rebuild/test_llm_api_and_resolver.py`、`test_llm_model_and_crypto.py`
- `M` **`rebuild/api/app.py`**（`llm` 顶层 import、`apply_llm_migrations`、`build_llm_router` mount）★共享窗

### Unit ⑨ runtime_node（整包，未跟踪）
- `NEW` **整包** `rebuild/runtime_node/`：`__init__.py`、`api.py`、`migrations.py`、`models.py`、`service.py`、`sftp.py`、`revisions/{__init__,v0001_runtime_node_registry}.py`（7 件）
- `NEW` `tests/rebuild/test_runtime_node_api.py`
- `M` **`rebuild/api/app.py`**（`runtime_node`/`runtime_node.models` 顶层 import、router mount）★共享窗

### Unit ⑩ model-lineage（新测试）
- `NEW` `tests/rebuild/test_model_lineage_edge_shape_a.py`（模块侧无未跟踪依赖，独立提交安全）

---

## 五、`rebuild/api/app.py` 共享窗的跨票风险（核心）

`app.py` 的 M 态 **14 hunk / +261 行**，经扫描确认**至少跨 4 票**：component_spec migrations（`:24`/`:363`/`:1057`）、execution（`:1091`）、llm（`build_llm_router`/`apply_llm_migrations`）、runtime_node（`build_runtime_node_router`）。其中**顶层导入 5 个未跟踪目标，4 个指向两个整包**（`rebuild/llm/`、`rebuild/runtime_node/`）。

⇒ **同一文件承载多票改动，且其中含对未跟踪模块的顶层导入**。风险场景：

1. **r9 票先提交**：若 r9 的 pathspec 只含 execution 相关件 + `app.py`，而**不含** `component_spec/migrations.py`（属 CD-C17-03 票）→ HEAD 全量 `ModuleNotFoundError`。
2. **CD-C17-03 先提交**：若只含 component_spec 件 + `app.py`，而 execution mount（`:1091`）已在 app.py 中引用 → `create_app()` 因 `run_stats` 缺失失败（H2）。
3. **任何票单独提交 `app.py` 的某几个 hunk**：`git add -p` 拆 hunk 可行但易错，且 app.py 的 import 区（`:21-30`）与 mount 区（`:1057`/`:1091`/`:1117+`）跨票交错，拆错即半红。

⇒ **建议 `app.py` 单列「共享窗装配件」类别，整文件与当窗全部依赖的未跟踪/新模块同批提交**，不做跨票 hunk 拆分。

---

## 六、对裁定① pathspec 固化的具体建议

1. **提交前机械闸门（已实现并实测，可直接取用）**：对待提交 `.py` 集合 S，静态提取每件的**顶层** `from A import B` / `import A`，做**两级**核查：(a) **模块级**——A 的任一候选路径须在 S 或 HEAD 中；(b) **名称级**——`from A import B` 时 B 须满足 `A.B` 候选路径存在，或 B 在 A 源码中以 `class`/`def`/赋值/`__all__` 形式定义为顶层名字。任一违反即**阻断**并列出缺失件。§三.2 即该闸门验收样本（app.py 阻断 5、execution/api.py 阻断 1、execution/migrations.py 阻断 1、trial/runner.py 放行）。

   ```python
   #!/usr/bin/env python3
   """pathspec 固化闸门（只读）— 裁定① 建议(1) 的可执行实现。

   用法:
     python pathspec_gate.py <待提交文件1> [<待提交文件2> ...]

   对提交集 S 中每个 .py，静态提取其 **顶层** `from A import B, C` / `import A`：
     1) 模块级：A 的任一候选路径须在 S 或 HEAD 中可解析；
     2) 名称级：`from A import B` 时，B 须满足其一 —— (a) A.B 候选路径在 S 或 HEAD 中；
        (b) B 在 A 的源码中以 class/def/赋值/__all__ 形式定义为顶层名字。
     违反者报告为阻断（提交后 HEAD 将 ImportError）。

   退出码: 0=全通过；1=存在阻断。
   """
   import subprocess
   import sys
   import os
   import re

   BACKSLASH = chr(92)


   def head_files():
       out = subprocess.run(['git', 'ls-tree', '-r', 'HEAD', '--name-only'],
                            capture_output=True, text=True).stdout
       return set(out.split())


   def module_candidates(name):
       if not name.startswith('rebuild.'):
           return []
       rel = name.replace('.', '/')
       return ['datara-backend/' + rel + '.py',
               'datara-backend/' + rel + '/__init__.py']


   def _read(p):
       try:
           return open(p, encoding='utf-8', errors='replace').read()
       except OSError:
           return None


   def defines_top_level_name(src, name):
       """粗略判断 name 是否为 src 中定义的顶层名字（class/def/赋值/__all__）。"""
       if src is None:
           return False
       pats = [
           r'(?m)^class\s+' + re.escape(name) + r'\b',
           r'(?m)^def\s+' + re.escape(name) + r'\b',
           r'(?m)^' + re.escape(name) + r'\s*(?::[^=\n]+)?=',
           r'(?m)^' + re.escape(name) + r'\s*:',
           r'(?m)^__all__\s*=\s*[\(\[](?:[^\)\]]*)["\']' + re.escape(name) + r'["\']',
       ]
       return any(re.search(p, src) for p in pats)


   def resolve_source(cands, S, head):
       """返回 S∪HEAD 中第一个存在的候选路径，否则 None。"""
       for c in cands:
           if c in S or c in head:
               return c
       return None


   IMP = re.compile(r'^([ \t]*)from\s+([\w\.]+)\s+import\s+([^\n#]+)|^([ \t]*)import\s+([\w\.]+)',
                    re.M)


   def main(argv):
       if not argv:
           print(__doc__)
           return 2
       S = set(p.replace(BACKSLASH, '/') for p in argv)
       head = head_files()
       blockers = []

       for f in sorted(S):
           if not f.endswith('.py') or not os.path.exists(f):
               continue
           src = _read(f) or ''
           for m in IMP.finditer(src):
               if m.group(2):                      # from A import B, C
                   indent, base, names = m.group(1), m.group(2), m.group(3)
                   if indent:
                       continue
                   if not module_candidates(base):
                       continue
                   if resolve_source(module_candidates(base), S, head) is None:
                       blockers.append((f, base, module_candidates(base)[0]))
                       continue
                   # 名称级：逐名核查
                   for raw in names.replace('(', ' ').replace(')', ' ').split(','):
                       nm = raw.strip().split(' as ')[0].strip()
                       if not nm or nm == '*':
                           continue
                       sub = base + '.' + nm
                       if module_candidates(sub) and \
                          resolve_source(module_candidates(sub), S, head) is not None:
                           continue
                       # 名字可能是 base 模块内的符号：读 base 源码
                       base_path = resolve_source(module_candidates(base), S, head)
                       bsrc = _read(base_path) if base_path else None
                       if defines_top_level_name(bsrc, nm):
                           continue
                       blockers.append((f, sub, (module_candidates(sub) or [sub + '.py'])[0]))
               else:                                # import A
                   indent, base = m.group(4), m.group(5)
                   if indent:
                       continue
                   if not module_candidates(base):
                       continue
                   if resolve_source(module_candidates(base), S, head) is None:
                       blockers.append((f, base, module_candidates(base)[0]))

       if blockers:
           print('BLOCK: 顶层导入目标既不在提交集、也不在 HEAD：')
           seen = set()
           for f, name, cand in blockers:
               key = (f, name)
               if key in seen:
                   continue
               seen.add(key)
               print('  %s -> %s  (期望文件 %s)' % (f, name, cand))
           print('')
           print('修复：把上列“期望文件”加入同批提交，或从提交集移除引用它的文件。')
           return 1
       print('OK: 提交集内所有顶层 rebuild 导入均可在同批或 HEAD 中解析。')
       return 0


   if __name__ == '__main__':
       sys.exit(main(sys.argv[1:]))

   ```

   > 注：闸门只覆盖**静态导入**；`getattr`/动态加载/字符串导入不在覆盖内，需人工核对。名称级检查依赖「B 是否为 A 中顶层名字」的启发式，`__all__` 与条件导入可能产生假阳性/假阴性，**最终以 §二 的 HEAD 叠加导入实证为准**。
2. **共享窗件登记**：`rebuild/api/app.py`（及同类多票共改装配件）登记为「共享窗」，其提交**必须整文件同批**，禁跨票拆 hunk。
3. **r9 票前置项**：提交 Unit ② 时**必须同步**将 `tests/rebuild/test_execution_models.py:18-25` 的 6 表断言改为 8 表（含 docstring `:1`「six §9 execution tables」措辞）。此为 s330/s331「候 r9 责任线报验一并收口」的**具体落点**，非新票。
4. **位置索引告警**：`execution/migrations.py:22-24` 以 `EXECUTION_TABLES[-2],[-1]` 取表，与 `models.py` 的元组**顺序**强耦合；建议改具名引用（`WorkflowRunStatRecord.__table__`），消除顺序漂移隐患。

---

## 七、红线自查

| 红线 | 状态 |
|---|---|
| `.git` 只读 | ✅ 仅 `git archive`/`status`/`diff`/`ls-files` 只读；未 `add`/`commit`/`push` |
| 禁 `aoci_*` | ✅ 零调用 |
| 禁 push | ✅ |
| 零业务代码改动 | ✅ 纯扫描 + HEAD 导出叠加实证 + 文档 |
| 未触碰他线在飞件 | ✅ 全部 M/未跟踪件仅只读；未改 |
| 证据成对 | ✅ 本件 + 信件 `cl-done-pathspec-atomic-units.json` |
| 不静默覆盖失败证据 | ✅ 本件为新增；1F 与三处 H1 如实记录 |

---

## 八、修订记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1 | 2026-10-21 | 初稿：三处 F8 形态实证（H1 三例）+ 原子提交单元表（9 单元）+ app.py 共享窗风险 + pathspec 固化建议 |
| v1.1 | 2026-10-21 | **两处自纠（均因 v1 自身口径缺陷，非新增事实）**：<br>① **未跟踪件清单口径**——v1 以 `.py` 后缀过滤 `git status --porcelain`，**漏掉 git 以目录形态上报的整包**（`?? datara-backend/rebuild/llm/`、`rebuild/runtime_node/`、`rebuild/component_spec/revisions/`）。按 `--untracked-files=all` 展开，未跟踪文件由 10 → **30**；`app.py` 单件阻断由 1 → **5** 个目标（4 个指向两个整包）。§一/§三.1/§三.2/§四/§五 已更正，原子单元由 9 → **10**（拆分 llm / runtime_node 整包）。<br>② **闸门首版误放行**——首版闸门仅做**路径级**检查，对 `from rebuild.execution.revisions import v0002_run_statistics`（包在 HEAD、子模块不在）**误判通过**，与 §三 HEAD 叠加实证（实测 ImportError）矛盾；且行首缩进用 `\s*` 会吞掉前置空行换行符、把顶层导入误判为惰性。已改为**两级核查（模块级 + 名称级）**并将缩进收紧为 `[ \t]*`，复测四例结果与 HEAD 叠加实证一致。§三.2/§六 已更正。<br>两处更正均在文内显式标注（非静默覆盖）。 |

---

| 版本 | 日期 | 作者 |
|---|---|---|
| v1 | 2026-10-21 | Claude 实施线（在飞件原子提交单元扫描 + F8 第三例实证 + pathspec 固化建议） |
| v1.1 | 2026-10-21 | 同上（自纠未跟踪件口径 + 闸门两级核查；见 §八） |
