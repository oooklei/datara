# 前端唯一入口收敛为 8090（用户裁定）

- 裁定时间：2026-11-01（权威序最高：用户最新裁定）。
- 裁定内容：datara 前端验证/集成入口**唯一**，固定 `http://192.168.1.9:8090/`，禁止多套并行部署（用户原话：「不要多套，不方便集成」）。

## 已落地（Trae，2026-11-01）

- `AGENTS.md`：前端验证入口改为 `http://192.168.1.9:8090/`（唯一前端入口，禁止多套并行部署）。
- 活跃文档/脚本同步 8090：`docs/README.md` §5、`docs/designs/2026-11-01-datara-current-authority.md`（现时唯一权威）、`docs/handoff/2026-10-31-整合部署交接.md`（入口/c5 URL/关键命令）、`deploy/wsl-frontend/{ide-verify.nginx.conf, verify-b1-api-v3.py, nginx.conf}`。2026-10-29/10-31 设计线已归档至 `docs/archive/2026-11-01-authority-refresh/`，历史执行记录（docs/plans 验证记录等）按不改写原则保留。
- 1.9 容器收敛：`datara-newweb-web` 重建为 `8090:80`（镜像 `datara-newweb:alert-center-20261031`，含 DBX IDE 首载缓存 + 加载遮罩 + KeepAlive 改动）；`datara-newweb-web-prev` 已删除；`datara-newweb-fe`(18092) 已停止；18091 不再监听。
- E2E（1.9 Playwright，admin，项目 #33）通过：首次进入遮罩 + spinner「正在准备 IDE 会话…」，二次进入 0 新增 ide-session 请求（前端 KeepAlive 缓存生效）。

## 对 codex 的要求

1. 后续所有前端部署/重建一律 `-p 8090:80`（容器内仍监听 80），**禁止再起 18091/18092 等并行前端实例**。
2. 新增文档/脚本/回执中的入口引用一律写 8090。
3. 若需回滚本次 IDE 优化，注意：后端 `rebuild/dbx/ide_proxy.py` 为**合并版**（含你的网关白名单/安全改动 + 5 处缓存改动）+ 新增 `rebuild/dbx/connection_catalog.py`；前端为 `DbxIdeView.vue` 遮罩/KeepAlive（`AppShell.vue` KeepAlive 已在 HEAD）。回滚时必须保留网关白名单改动，否则 DBX 启动 403 复发。
