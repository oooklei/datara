# datara-newweb 1.9 部署联调前置物料（1.5 前置准备交付物）

> **票源**：S240 ④ 用户令即派「Trae 即接 1.5 部署联调前置准备（1.9 隔离工作目录 + 18091 入口 + 构建产物冒烟，回执 tr-ack-15）」
> **日期**：2026-10-21
> **编制**：Trae 线
> **权威约束**：纠偏重构前端权威设计 v3 §7.1（单 BASE）/ §7.3 判据 C；域规范「前端验证入口固定 http://192.168.1.9:18091/（禁 8090；18090 被并行验证栈占用；Web 容器内监听 80、API 代理契约不变）」

---

## 1. 部署拓扑与端口契约

```
浏览器 ──► http://192.168.1.9:18091/        （宿主 18091，新前端唯一验证入口）
              │ docker -p 18091:80
              ▼
        datara-newweb-web 容器（nginx:1.27-alpine，容器内 listen 80）
              │ /api/v1/ → proxy_pass http://datara-rebuild-api:8001（Docker DNS）
              ▼
        datara-rebuild-api 容器（uvicorn :8001，docker-compose.rebuild.yml 栈）
```

| 端口 | 归属 | 纪律 |
|---|---|---|
| **18091** | 新前端验证入口（宿主→Web 容器 80） | 唯一入口，禁 8090 |
| 18090 | 并行验证栈占用 | **禁用** |
| 18092 | 本机 dev（vite server） | 仅本机开发用 |
| 80 | Web 容器内监听 | nginx.conf 契约，不改 |
| 8001 | datara-rebuild-api | 唯一 API 源（单 BASE 红线 1） |

**同网约定（关键）**：`deploy/nginx.conf` 上游写死 Docker DNS 名 `datara-rebuild-api:8001`，Web 容器必须与 API 容器处于同一 docker 网络（compose 默认网络或显式 `--network`），否则 DNS 解析失败。API 容器 8001 **不发布宿主端口**（compose 无 ports 段），仅容器网内可达——这天然满足「无第二后端旁路」。

## 2. 1.9 隔离工作目录布局

以下 `<ISO_DIR>` 为 1.9 隔离工作目录占位（以监督线/用户指定为准；部署/E2E 验收证据必须出自该目录）。建议布局：

```
<ISO_DIR>/
├── dist/                        # 本机构建产物（构建冒烟通过的 dist 原样上传）
├── deploy/
│   ├── Dockerfile               # 本仓库 datara-newweb/deploy/Dockerfile 原样
│   ├── nginx.conf               # 本仓库 datara-newweb/deploy/nginx.conf 原样
│   └── docker-compose.rebuild.yml   # 仓库根 docker-compose.rebuild.yml 原样（API 栈）
├── rebuild-source/rebuild/      # API 代码挂载源（与 compose 卷映射一致）
├── files/                       # compose ./files 挂载源
├── .env                         # REBUILD_DB_URL / REBUILD_TOKEN_SECRET / REBUILD_LEGACY_META_URL（compose 必填三值，由运维侧提供，禁入库）
└── evidence/                    # 部署/E2E 验收证据落位处
```

> compose 卷映射 `./rebuild-source/rebuild` 与 `./files` 为相对路径，故 compose 文件、rebuild-source、files 三者必须同在 `<ISO_DIR>` 下按上述相对关系落位；`.env` 与 compose 同目录自动加载。

## 3. 部署步骤（在 1.9 上执行）

### 3.1 API 栈（若 1.9 尚未运行）

```bash
cd <ISO_DIR>
docker compose -f deploy/docker-compose.rebuild.yml up -d
docker compose -f deploy/docker-compose.rebuild.yml ps        # 等 healthcheck healthy
curl -sf http://localhost:8001/api/v1/rebuild/health          # 容器内直连验证（宿主无端口映射则经临时 exec 验证）
```

> 若 1.9 已有运行中的 rebuild 栈（并行验证栈），跳过本步，仅确认容器名 `datara-rebuild-api` 与网络可达即可。

### 3.2 Web 镜像构建（两条路线二选一）

**路线 A（推荐）：本机构建镜像 → docker save/load 搬运**（1.9 无需 node 环境，镜像仅 ~50MB）

```powershell
# 本机（datara-newweb/ 下）：构建产物已在（1.5 冒烟通过）
npx vite build          # 或 npm run build（候 1.4 收编 TSC 绿后用全量命令）
docker build -t datara-newweb:inc1 -f deploy/Dockerfile .
docker save datara-newweb:inc1 -o datara-newweb-inc1.tar
# 传输 datara-newweb-inc1.tar 至 1.9 <ISO_DIR>
```

```bash
# 1.9
docker load -i <ISO_DIR>/datara-newweb-inc1.tar
```

**路线 B：源码 + dist 上传，1.9 现场构建**

```bash
# 上传 dist/ 与 deploy/（Dockerfile、nginx.conf）至 <ISO_DIR>，保持相对结构
cd <ISO_DIR>
docker build -t datara-newweb:inc1 -f deploy/Dockerfile .
```

### 3.3 Web 容器起服（18091 入口）

```bash
# 确认 API 容器所在网络（compose 项目默认网络）
docker inspect datara-rebuild-api --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}'

docker run -d --name datara-newweb-web \
  --network <上一步得到的网络名> \
  -p 18091:80 \
  --restart unless-stopped \
  datara-newweb:inc1
```

> 网络名形如 `<ISO_DIR 目录名>_default`；必须与 datara-rebuild-api 同网，`datara-rebuild-api` DNS 名才可解析。

## 4. 部署后验证判据自测清单（判据 C 本地预演已在 1.5 前置冒烟通过，1.9 侧复测）

| # | 判据 | 命令 | 期望 |
|---|---|---|---|
| V1 | 三 URL 同壳（根/path 式/深层 path） | `curl -s http://192.168.1.9:18091/`、`/login`、`/p/1/dashboard` | 三者均返回**同一** index.html（引用同一 `/assets/index-*.js`） |
| V2 | History 回退 | `curl -s -o /dev/null -w '%{http_code}' http://192.168.1.9:18091/任意深层path` | 200（try_files 回退 index.html，非 404） |
| V3 | API 单源代理 | `curl -s http://192.168.1.9:18091/api/v1/rebuild/health` | 经 18091 → 8001 返回健康包络 |
| V4 | 无第二后端旁路 | 抓包/日志核查 | 所有 `/api/v1/` 请求上游均落 `datara-rebuild-api:8001`，无 8000 出现（红线 1） |
| V5 | 资源缓存契约 | 响应头核查 | `/assets/*` 带 `immutable` 缓存头；`index.html` 带 `no-cache` |

## 5. 本机构建冒烟实况（1.5 前置证据，2026-10-21）

| 步骤 | 命令 | 结果 |
|---|---|---|
| 构建 | `npx vite build` | EXIT=0，1614 modules，dist/index.html 0.35KB + index-Dg7A2CJ9.css 360.74KB + index-Durv0zV6.js 1018.59KB |
| 同壳冒烟 | `vite preview --port 18093` + 探测 `/`、`/login`、`/p/1/dashboard`、`/dag` | 四 URL 均 200 / LEN=350 / 同一 bundle `/assets/index-Durv0zV6.js`；JS 资源 HEAD 200（1,018,593B） |
| 全量类型检查 | `npm run build`（vue-tsc -b 段） | **被阻塞**：resourceApi.ts L127/L138 TS2552——Claude 1.4 收编件在飞半成品（四 api 文件 import 已改调用点未完），归 Claude 域本线不触碰；1.4 收口三绿门（vitest+TSC+build）后正式构建复跑刷新 dist |

> 披露（O7 诚实纪律）：本次 dist 产物含 Claude 1.4 在飞件混入态，仅用于验证「构建链+产物结构+History 回退」；**上 1.9 的正式 dist 候 1.4 收口三绿门后以 `npm run build` 复跑产出**。

## 6. 边界与不做

- 不改 `deploy/nginx.conf`、`deploy/Dockerfile`（1.5 首版已交付并随增量 1 收口冻结；18091 由部署栈 `-p 18091:80` 发布，容器内维持 80）；
- 不触碰 Claude 1.4 在飞件（http.ts、四个 rebuild api 文件）；
- `.env` 三值（REBUILD_DB_URL/REBUILD_TOKEN_SECRET/REBUILD_LEGACY_META_URL）由 1.9 运维侧提供，本物料不承载、不入库；
- 镜像搬运/1.9 现场执行属后续 1.5 正式票动作，本前置仅备妥物料与判据。
