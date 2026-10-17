# R4-DEPENDENCY / R4-RESOURCE — P0-4 执行证据（2026-10-17）

> 任务：P0-4 DEP/RES 双域 BE 冻结契约实现 + FE 接线 + 门禁 + 联调 + E2E（dependency 五端点 + resources 五端点）。
> 契约真源：A2 v2.1 冻结契约（`docs/increments/2026-10-17-R4-DEP-RES-API-contract-pending.md` §2/§4，双线会签）+ GREEN 接线计划 Task 4 契约面表。
> 编排依据：心跳 #74（#75）授权 DEP/RES 归 Trae；#77 追认 R2 越权/秘密暴露两缺口并入 P0-7（本批不涉及）。

## 1. 交付物（提交链，pathspec 单文件逐笔）

| # | 文件 | 内容 |
|---|---|---|
| 1-4 | `datara-backend/rebuild/dependency/`（`__init__.py`/`models.py`/`repository.py`/`api.py`） | dependency_config 表 + 五端点（GET /workflows、GET /workflows/{id}/tasks、POST /preview、POST /saves、POST /evaluate）、DEP_* 域错误、窗口解析（as_of/period/offsets→半开区间）、R7 表历史 verdict（satisfied/failed/pending/timeout）、两层条件组合判定、同槽替换保存 |
| 5-8 | `datara-backend/rebuild/resources/`（`__init__.py`/`models.py`/`repository.py`/`api.py`） | resources/resource_version/resource_binding 三表 + 五端点（POST /uploads multipart、GET ''、GET /{id}/versions、GET /{id}/versions/{version}、POST /bindings）、sha256 落盘存储（resource_storage/）、不可变版本单调、显式版本绑定幂等+409 冲突 |
| 9 | `datara-backend/rebuild/api/app.py` | 四新表 create_all + 两 router 挂载（/api/v1/rebuild/dependency、/api/v1/rebuild/resources） |
| 10 | `datara-backend/.gitignore` | +resource_storage/（上传二进制不入库） |
| 11 | `datara-backend/tests/rebuild/test_r4_dependency_api.py` | 8 测试：honest 空列表/401/4001、窗口精确值（as_of=2026-10-17T12:00:00Z→[10-16,10-17)）、关窗无 timeout→pending、task selector 哨兵 '5'（string 透传）、失败历史→failed、R7 表历史 verdict 五态、两层组合四态、校验族（DEP_INVALID_WINDOW/DEP_INVALID_TIMEOUT_POLICY/4001 帧畸形）、saves 同槽替换、evaluate evaluated_at 回显 |
| 12 | `datara-backend/tests/rebuild/test_r4_resources_api.py` | 6 测试：multipart sha256+落盘一致、v2 单调+v1 不可变、校验族（RES_TYPE_NOT_ALLOWED/RES_KIND_UNKNOWN/RES_SIZE_EXCEEDED/4001）、kind 过滤、404 族、绑定幂等+409、401/403 |
| 13 | `datara-web/src/services/rebuild/dependencyApi.ts` | GREEN 接线：五方法真实 fetch、upstreamTaskCode string→int 哨兵（非十进制 fail-fast ID_NORMALIZATION_FAILED）、包络解包+非 2xx 保码透出（DEP_*/4001）、15s 超时、token header |
| 14 | `datara-web/src/services/rebuild/resourceApi.ts` | GREEN 接线：uploadResource 真实 multipart（contentBase64→Blob、不手工设 Content-Type）、版本链三 GET、bindResourceVersion POST、RES_* 保码透出 |
| 15 | `datara-web/src/views/rebuild/validation/dependency-form/dependencyApi.contract.test.ts` | RED describe（方法冻结+composeExpressionDraft）+ GREEN describe 8 断言（wire body 全 snake、哨兵转换、保码透出） |
| 16 | `datara-web/src/views/rebuild/validation/resource-upload/resourceApi.contract.test.ts` | RED describe（方法冻结+validateUploadDraft）+ GREEN describe 7 断言（multipart FormData、CONTRACT_VIOLATION fail-fast、snake→camel 映射、RES_* 保码） |
| 17 | `datara-web/src/views/rebuild/validation/resource-upload/ResourceUploadValidationView.vue` | 最小接线修补：picked 携带 contentBase64（FileReader 读取）、onUpload 传入并回填版本结果展示（上传按钮否则必报 CONTRACT_VIOLATION） |

DependencyFormValidationView.vue 本批零改动（RED 期已通过契约工厂调用五方法，接线后自动 GREEN）。

## 2. 门禁

| 门禁 | 命令 | 结果 |
|---|---|---|
| BE 全量回归 | `python -m pytest tests/rebuild -q`（datara-backend） | **332 passed, 1 xfailed**（318 基线 + 14 新增，零回归） |
| FE 全量 | `npx vitest run`（datara-web） | **872 passed (93 files)**（859 基线 + dependency 12 + resource 11，零回归） |
| FE 类型 | `npx vue-tsc --noEmit` | **0 错误** |

## 3. 联调与 E2E（双向锚点互证）

环境：BE `uvicorn rebuild.api.app:create_app --factory --port 8000`（REBUILD_DB_URL=sqlite+pysqlite:///./rebuild_e2e_r2.db，REBUILD_TOKEN_SECRET=r4-e2e-secret）；FE vite dev 5173（HMR 加载 GREEN 契约层）；E2E runner=Playwright headless Chromium（沿 R7 模式，独立 profile）。

种子：project 1（owner=dev）+ 项目成员（dev）+ workflow_result_stat wf1 行（2026-10-16，success=2/failure=0 → preview/evaluate 判 satisfied）。

BE 十端点冒烟（python urllib，先于页面走查）：**10/10 全 200**（preview/evaluate satisfied、saves version=3、upload digest=sha256、bind binding_id=1）。

E2E 走查（runner：`%TEMP%\r4-e2e-runner\r4_e2e.js`，不入库）：

**页面 A `#/rebuild/validation/dependency-form`（8 步全完成）**：加条件组 → 填任务编码 clean → 候选工作流加载（200，诚实空列表 0 行）→ 任务加载（200，0 行）→ 本地草稿 `wf(1) day[-1..-1]` → 预览最终表达式 完成 → 保存依赖 完成 → 预演判定 完成。

**页面 B `#/rebuild/validation/resource-upload`（7 步全完成）**：选文件（预校验通过）→ 上传（multipart 200，版本结果回显 v1+digest）→ 资源列表 完成 → 版本列表 完成 → 读取指定版本 完成（digest 与上传回显一致）→ 填任务编码 → 绑定确定版本 完成。

网络捕获（`r4-dep-res-e2e-20261017.json`）：**10/10 全 200，零失败**：

| 方法 | 端点 | 状态 |
|---|---|---|
| GET | /api/v1/rebuild/dependency/workflows?project_id=1 | 200 |
| GET | /api/v1/rebuild/dependency/workflows/1/tasks?project_id=1&workflow_version=1 | 200 |
| POST | /api/v1/rebuild/dependency/preview | 200 |
| POST | /api/v1/rebuild/dependency/saves | 200 |
| POST | /api/v1/rebuild/dependency/evaluate | 200 |
| POST | /api/v1/rebuild/resources/uploads（multipart） | 200 |
| GET | /api/v1/rebuild/resources?project_id=1&kind=sql | 200 |
| GET | /api/v1/rebuild/resources/1/versions?project_id=1 | 200 |
| GET | /api/v1/rebuild/resources/1/versions/1?project_id=1 | 200 |
| POST | /api/v1/rebuild/resources/bindings | 200 |

首轮走查曾暴露 dependency preview/save/evaluate 400（页面 taskId 默认空）——BE 帧校验正确拒绝（`task_id must be a non-empty string`），runner 补填后全绿；该轮失败过程保留于本节诚实留痕，证据 json 为重跑后的干净版本（E2E 脏数据已清库重跑：resource_binding/resource_version/resources/dependency_config 四表清零）。

证据文件：r4-dep-res-e2e-20261017.json（完整网络+步骤报告）、r4-dep-res-e2e-dep-20261017.png、r4-dep-res-e2e-res-20261017.png（双页整页截图）。

## 4. 窄口径披露（诚实自评）

1. **listCandidateWorkflows / listWorkflowTasks 诚实空列表**：main 无 workflow 注册表（DolphinScheduler 元数据迁移未落地），两 GET 恒返回 []——BE/FE 双侧已披露，非缺陷。
2. **页面横幅维持 RED 文案**：「后端契约未接入」横幅按 R7 惯例原样保留，待监督线/Codex 独立评审 PASS 前不宣称终态 GREEN（R4_DEPENDENCY_NOT_WIRED/R4_RESOURCE_NOT_WIRED 常量保留仅作 View 兼容）。
3. **dependency workflow 粒度窗口 hour 落 pending**：repository.py metrics_history_lookup 以 run_date（day 粒度）作 proxy，hour 窗口当前无法精确判定，已注释披露——属 P0-4 冻结基「差异对齐清单」已声明项。
4. **非 2xx 保码透出强化**：包络含 code（DEP_*/RES_*/4001/1001/1003/4041）时 ContractApiError 同时携带 httpStatus 与后端码；非 JSON/无 code 才退回 HTTP 状态码错误。
5. **首轮 E2E 失败已修复留痕**：dependency 页面 taskId 未填导致 BE 帧校验 400，属 runner 输入缺失而非产品缺陷；修复后重跑全绿。

## 5. 红线自检（runbook §7）

- 显式人工确认闸：未涉及（P0-4 无人工闸项）。
- 失败证据保留：首轮 E2E 400 过程与本节披露保留；未删除失败痕迹。
- 诚实状态标注：本批交付 BE+FE 全链 GREEN 证据，终态 GREEN 待独立评审。
- TDD 红绿顺序：BE 测试先行全绿→联调；FE contract test RED describe 先行、GREEN describe 随接线提交。
- token/key 边界：E2E token 仅运行时注入 localStorage；REBUILD_TOKEN_SECRET 仅进程环境变量；无任何秘密入库。
- 验收前不提交实现：门禁+E2E 全部完成后方开始本提交链。
- 不 push：全部提交仅落 main 本地。

## 6. 遗留与后续

- **P0-7（#77 令 P0-4 收口后优先）**：R2 `GET /run-snapshot` 越权（无 project 权限校验）+ env completion 秘密暴露（整个 os.environ 返回且 sensitive=false）——Trae 名下下一任务。
- P1-1/P1-2 已移交 Codex（#77）；P1-3 ai_copilot 挂载时 Trae 配合 app.py。
- T-1 P1-7 修订（Codex 五缺口）保留待办。
