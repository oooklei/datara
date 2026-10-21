# 「鉴权头词形分裂」核验 — FE 单一 `token` 头 vs rebuild 后端双轨（18 模块 dual-accept / 2 模块仅 Bearer）

- **性质**：Claude 实施线对 s339-cl-report 候裁②「前端 `http.ts` TOKEN_HEADER=token 与后端仅认 Authorization Bearer 失配，请裁归属票」做独立只读核验
- **日期**：2026-10-21
- **触发**：`s339-cl-report-l1202-full-e2e-f3-blocked-20261021`【候裁五组】②
- **边界**：只读静态实证；**零业务代码改动**；`.git` 只读未 push；未调用 `aoci_*`；未触碰他线在飞件

---

## 一、结论（四条）

1. **失配真实存在，但范围不是「前端 vs 后端」全域，而是「后端内部双轨」**：rebuild 后端 **18 个模块**采用 `token`-first + `Bearer` 回退（dual-accept），仅 **2 个模块**（`api/app.py`、`governance/api.py`）只认 `Authorization: Bearer`。
2. **前端只发 `token`，全域零 `Bearer`**（`datara-newweb/src/` 下 `Bearer` 出现 0 次），且部署链 nginx **不做任何头改写**。
3. **故 FE → 该 2 个模块的调用 401**；FE → 其余 18 模块正常。今日受影响面 = **项目 / 成员 / 数据源** 三类调用（`projectApi` / `memberApi` / `datasourceApi`）；governance 域 FE 未调用 ⇒ **潜伏无当日影响**。
4. **修复应选「对齐 2 个离群模块」而非改前端**：18:2 的压倒性多数即 rebuild 的既有约定（`token`-first），且 `app.py` 侧一处共享 helper 即可覆盖其 26 处端点。

---

## 二、前端侧实证

### 2.1 唯一 HTTP 底座，头名写死 `token`

`datara-newweb/src/services/http.ts`（全 FE **唯一** HTTP 模块）：

```
:38   export const TOKEN_HEADER = 'token' as const
:158  if (token) finalHeaders[TOKEN_HEADER] = token      // request()
:220  if (token) finalHeaders[TOKEN_HEADER] = token      // 单 BASE 请求底座
:290  if (token) finalHeaders[TOKEN_HEADER] = token      // 原始响应通道
```

注释自陈其来源：

```
:6    *   - token 自动携带（header `'token'`，与后端既有鉴权头同源）；
```

⇒ 「与后端既有鉴权头同源」指**旧侧**后端——`datara-backend/api/auth.py:85  token = request.headers.get("token")`（旧侧确以 `token` 为头名）。**前端是照旧侧契约写的**。

### 2.2 前端全域零 `Authorization` / 零 `Bearer`

```
$ grep -rn "Bearer" datara-newweb/src/
（无输出）
```

其它直连 `TOKEN_HEADER` 的服务件（同一约定）：`componentSpecApi.ts:49`、`resourceApi.ts:186`。

---

## 三、后端侧实证：双轨分裂矩阵

以 `grep -c "token: str = Header"` vs `grep -c "authorization: str = Header"` 逐模块计数：

| 类别 | 模块数 | 模块（token/authz 计数） |
|---|---|---|
| **dual-accept**（token 优先 + Bearer 回退） | **18** | workflow(12/12)、model(22/22)、execution(13/13)、stream(11/11)、scheduling(7/7)、trial(7/7)、llm(6/6)、metrics(6/6)、resources(6/6)、variables(6/6)、dependency(5/5)、sshnode(5/5)、sync(5/5)、rb(4/4)、ai_bridge(2/2)、runtime_node(2/2)、component_spec(1/1)、monitor(1/1) |
| **authorization-only** | **2** | `api/app.py`(0/**26**)、`governance/api.py`(0/**28**) |

### 3.1 dual-accept 的语义（注释自陈）

`datara-backend/rebuild/workflow/api.py:39-41`：

```python
def principal(token: str, authorization: str) -> dict[str, object]:
    """Authenticate via the FE ``token`` header first, then Bearer fallback."""
    raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
```

⇒ 18 个模块是**明确为迁就 FE `token` 头而写**的，Bearer 仅作回退。**这是 rebuild 的既有约定。**

### 3.2 离群模块：`api/app.py` 仅 Bearer

```python
# datara-backend/rebuild/api/app.py
:525  def current_user(authorization: str) -> dict[str, object]:
:526      if not authorization.startswith("Bearer "):
:527          raise ValueError("missing bearer token")
:528      token = authorization[7:]
...
:627  @app.get("/api/v1/rebuild/projects")
:628  def list_projects(authorization: str = Header(default="")):
:629      try:
:630          user = current_user(authorization)
:631      except ValueError:
:632          return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
```

`api/app.py` **全域无 `token` 形参**（`token=0`）；`governance/api.py` 同（`token=0`，全 `authorization: str = Header(default="")`）。

---

## 四、部署链核验：无任何头改写

`datara-newweb/deploy/nginx.conf`（1.9 栈 FE 容器，监听 80 → 18091）：

```
location /api/v1/ { proxy_pass $rebuild_api_upstream$request_uri;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; }
```

`datara-web/nginx.conf` 亦仅 `Host` / `X-Real-IP` / `X-Forwarded-For`。

⇒ **nginx 不注入 `Authorization`、不改写 `token`**；FE 的 `token` 头**原样**抵达后端。Vite dev proxy（`vite.config.ts:6`）亦仅 `changeOrigin`，无改写。**不存在任何能把 `token` 桥成 `Bearer` 的中介。**

---

## 五、影响面（FE 调用 Authorization-only 端点的清单）

| FE 服务件 | 端点 | 落点模块 | 判定 |
|---|---|---|---|
| `projectApi.ts:27` | `GET /rebuild/projects` | `api/app.py:627` | **401** |
| `memberApi.ts:54/61/68/77` | `/rebuild/projects/{id}/members`（GET/POST/DELETE/PATCH） | `api/app.py` | **401** |
| `datasourceApi.ts:118` | `/rebuild/projects/{id}/datasources` | `api/app.py` | **401** |
| `datasourceApi.ts:148/150` | `/rebuild/datasources/validate`、`/datasources/profiles/{id}/probe` | `api/app.py` | **401** |
| （governance 域） | — | `governance/api.py` | FE 零调用 ⇒ **潜伏，无当日影响** |

**旁证（独立）**：并行 Claude 会话在 `s339-cl-report` 二 记载同一现象——「鉴权头词形失配已由 E2E route 层适配并复跑实证生效」，且明言「auth 域属他票本线未动生产码，仅 E2E route 层适配」⇒ 该会话在 E2E 层**绕过**了此缺陷，生产码未修。

> **限定**：本节为**代码 + 配置静态推演**，本线未起 1.9 栈实测。旁证为并行会话 E2E 观测，方向一致。

---

## 六、为何既有测试未捕获

| 侧 | 事实 | 后果 |
|---|---|---|
| 后端测试 | 一律发 `Authorization: Bearer`（`test_identity_api.py:71/74/86/91/115/134`；`test_governance_api.py` 全线同） | 只走 Bearer 主路径，**永不触碰 FE 的 `token` 头** |
| 前端测试 | 仅单测 `TOKEN_HEADER` 常量与 mock 底座 | 无跨栈契约断言 |
| 跨栈 | **无** FE `token` 头 ↔ BE 接受度的契约测试 | 失配**结构性不可见** |

⇒ 两侧各自绿，接缝红。**这正是需要一张跨栈契约测试锚的原因**（见 §七.3）。

---

## 七、修复选项与归属建议

### 7.1 选项（三）

| 选项 | 动作 | 波及 | 评价 |
|---|---|---|---|
| **A（推荐）** | 对齐 2 个离群模块：`api/app.py` 的 `current_user` + `governance/api.py` 的等价 helper 增 `token` 形参并前置（`raw = token or Bearer回退`） | BE 2 文件；`app.py` 侧一处 helper 覆盖 26 端点 | **符合 18:2 既有约定**；前端零改；最小语义漂移 |
| B | 前端改发 `Authorization: Bearer`（`http.ts` 一处） | FE 1 文件 | 亦可通（18 模块 Bearer 回退生效），但**逆既有约定**，且日后任一模块收紧回退即复发 |
| C | nginx 改写 `token` → `Authorization` | 部署配置 | 治标；dev/Vite 与直连场景不复现，**掩盖契约分歧** |

### 7.2 归属建议（供监督线裁定）

跨三域，单一票无法闭合：**BE-核心域**（`api/app.py`，且该件为 s339①「app.py 单写者锁」热点）+ **BE-治理域**（`governance/api.py`）+ **FE 契约域**（`http.ts` 是否随之固化）。

建议：**立一张「鉴权头词形统一」跨域票**，DoD = ① 选项 A 落地（或监督线择定项）；② §七.3 跨栈契约测试转绿；③ `http.ts` 头名注释更正为「与 **rebuild** 后端约定同源（token-first，18 模块 dual-accept）」——现行注释指向旧侧，是**误解之源**。

### 7.3 建议回归锚

新增跨栈契约测试一例：**FE 底座实发头名**（`token`）→ 打 `GET /api/v1/rebuild/projects` **须 200**。该用例在选项 A/B 任一落地前为**红**，可作为本缺陷的 TDD 锚。

---

## 八、红线自查

| 红线 | 状态 |
|---|---|
| `.git` 只读 | ✅ 仅 `grep`/`cat`/`sed`；未 `add`/`commit`/`push` |
| 禁 `aoci_*` | ✅ 零调用 |
| 禁 push | ✅ |
| 零业务代码改动 | ✅ 纯只读实证 + 文档 |
| 未触碰他线在飞件 | ✅ `app.py`/`governance/api.py`/`http.ts` 等**仅读** |
| 证据成对 | ✅ 本件 + 信件 `outbox/claude/cl-done-auth-header-split-verify.json` |
| 不静默覆盖失败证据 | ✅ 本件为新增 |
| 不摘他线票 | ✅ 仅核验候裁②，未认领归属票；E 系/L5-03/15.2-D/15.3 归并行会话 |

---

| 版本 | 日期 | 作者 |
|---|---|---|
| v1 | 2026-10-21 | Claude 实施线（s339 候裁② 鉴权头词形分裂独立核验） |
