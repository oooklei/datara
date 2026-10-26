# datara-newweb 1.9 隔离部署与 E2E

## 固定契约

- 唯一浏览器入口：`http://192.168.1.9:18091/`；禁止使用 8090，18090 保留给并行验证栈。
- Web 容器监听 80，`/api/v1/` 仍代理到 `datara-rebuild-api:8001`。
- 本机只做静态、类型、单元测试与构建校验。容器启动、数据库、中间件、联调和 Playwright 真实执行全部在 1.9 的隔离目录完成。
- 验证 key、密码和短时 token 只通过 1.9 进程环境注入；不得写入仓库、静态产物、命令行 URL、截图、报告或 `localStorage`/`sessionStorage`。

## 制品同步

在本机完成 `npm ci`、`npm run test -- --reporter=dot`、`npx vue-tsc --noEmit` 与 `npm run build` 后，仅同步受控源码/构建制品到 1.9 隔离目录。例如：

```powershell
scp -r dist deploy e2e playwright.config.ts package.json package-lock.json <user>@192.168.1.9:<ISO_DIR>/datara-newweb/
```

`<ISO_DIR>` 和 `<user>` 由执行环境提供。不得把 `.env`、密钥文件、`playwright-report/` 或本机证据目录随包上传。

## 1.9 部署

在 1.9 上从隔离目录构建并启动 Web 容器，确保它与 `datara-rebuild-api` 位于同一 Docker 网络：

```bash
cd <ISO_DIR>/datara-newweb
docker build -t datara-newweb:fusion-b6 -f deploy/Dockerfile .
docker rm -f datara-newweb-fusion-b6 2>/dev/null || true
docker run -d --name datara-newweb-fusion-b6 --network <REBUILD_NETWORK> -p 18091:80 datara-newweb:fusion-b6
curl -fsS http://192.168.1.9:18091/ >/dev/null
```

删除旧容器前先确认名称和隔离目录归属；不得停止无关验证栈。

## 短时鉴权与 E2E

测试通过 `/api/v1/rebuild/login` 获取短时 token。页面启动前只把 token 放入 `globalThis.__DATARA_TEST_TOKEN__`，应用首次读取后即删除该全局值并转入模块内存；Playwright 路由同时仅在请求期补鉴权头。用例禁止读取或写入浏览器持久存储。

凭据仅在 1.9 当前 shell 注入；不要把值直接写进命令历史或日志：

```bash
read -r -p 'E2E user: ' E2E_USER
read -r -s -p 'E2E password: ' E2E_PASS; echo
export E2E_USER E2E_PASS
export E2E_PROJECT_ID='<existing-project-positive-id>'
export E2E_ASSET_ID='<asset-positive-id-owned-by-project>'
npm ci
npx playwright test
unset E2E_PASS
```

LLM 成功路径如需测试端点，使用执行环境临时注入 `E2E_LLM_TEST_BASE`/`E2E_LLM_TEST_KEY`；缺省只验证不可路由探针的结构化失败路径。不得把真实 key 打印或截屏。

`E2E_PROJECT_ID` 与 `E2E_ASSET_ID` 是质量规则用例的必填正整数，且资产必须属于指定项目；测试不提供默认业务 ID，缺失或非法时在发起请求前失败。

## 验收证据

证据必须出自 1.9 隔离目录，至少包括：部署容器/镜像摘要、三组 E2E 汇总、失败 trace（若有）、入口响应与浏览器 console-error 汇总。报告完成审计后再归档；生成的 `playwright-report/`、编译出的 `playwright.config.js/.d.ts`、`e2e/**/*.js/.d.ts` 永不入库。
