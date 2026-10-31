# Datara / DBX / DolphinScheduler 源码真源与发布同步

> 2026-11-01 用户裁定。此文件记录源码位置与发布流程；业务实现仍以 `docs/designs/2026-10-29-dbx-unified-target-design.md` 为准。运行镜像、容器、编译输出、部署目录中的临时改动不得反向定义源码。

| 系统 | 唯一可修改真源 | 发布/本机镜像 |
| --- | --- | --- |
| Datara | `D:\需求\数据治理工具\Datara` 的 Git `main`，含 `datara-backend/`、`datara-newweb/`、`deploy/` 等 | 发布前将 Git 工作树快照及清单同步至 `192.168.1.9:/lei/datara/deployments/<release>/datara-source/`；远端仅用于构建、联调和取证 |
| DBX | `192.168.1.9:/lei/apps/dbx/` 中的可构建源码（当前非 Git 仓库） | 每次发布后同步至本机 `.source-mirrors/<release>/dbx/`；排除 `data/`、`backups/`、`dist/`、`node_modules/`、密钥及构建缓存 |
| DolphinScheduler | 3.4.3 基线 `192.168.1.9:/lei/dolphinscheduler/ds-pristine/dolphinscheduler-3.4.3/` **加**本仓库 `deploy/dolphinscheduler/3.4.3/` 的 Datara 补丁。只有这一组合构成集成源码 | 远端在隔离发布目录按顺序应用补丁并构建；发布后把已应用补丁的源码快照同步至本机 `.source-mirrors/<release>/dolphinscheduler-3.4.3/` |

DBX 目前缺少提交号，海豚基线也不是 Git 工作树；发布记录必须保存源码压缩包 SHA-256、Datara 提交号及补丁 SHA-256，不能仅记镜像标签。本机 `.source-mirrors/` 是只读核对副本，不得在其中直接开发或作为另一套真源。DBX 需要改动时先核对本机镜像与 1.9 真源的差异，在真源中集成；海豚需要改动时编辑本仓库补丁，并在干净基线上验证可应用。

## 发版门禁

1. 在 Datara `main` 运行 `python scripts/release_source.py preflight`：拉取 `origin/main`，检查当前分支、工作树、冲突索引、未合并本地分支及远端领先提交。其他分支或工作区中的待发布内容先合并；有冲突就在原分支或隔离工作区解决，再回到真源。
2. 核对 DBX 真源与上一次本机镜像、海豚基线与补丁。发现两端都有改动时先合并并复核，不得用覆盖同步处理冲突。
3. 运行 `python scripts/release_source.py snapshot --release-id <release>`，将生成的 `datara-source.tar.gz` 和 `datara-source.json` 同步至 1.9 对应隔离发布目录，比较两端 SHA-256 后从该快照构建。部署证据留在 1.9 隔离目录。唯一前端入口仍为 `http://192.168.1.9:8090/`。
4. DBX、海豚发布后，从本次实际构建源码制作排除运行数据与密钥的快照，核对 SHA-256 并同步到本机 `.source-mirrors/<release>/`。记录镜像 ID、源码包与补丁 hash；之后的工作先比对这些记录。

## 2026-11-01 已发布快照

- 隔离发布目录：`192.168.1.9:/lei/datara/deployments/codex-main-20261101-0635/`。
- Datara：`main` HEAD `4c805c59d64f7c00d2cbea29747bad1d1f9fb96f`，`origin/main` 当时落后 3 提交；发布时存在未提交修改。此次为**既有发布的追溯快照**，不满足今后的清洁工作树门禁，不能作为跳过合并的先例。
- DBX 与海豚实际构建源码包及 `archives.sha256`：远端 `source-sync/`；本机 `.source-mirrors/2026-11-01-codex-main/`。海豚源码包取自两份补丁已应用后的隔离源码。
- DBX 源码包 SHA-256：`3f8b567a2bebd806fc964a649a1ae039d33ccd8358aee81346ce73ccff5ade57`；海豚源码包：`c7bfe47c17c5327d5ab459dcfcd90a97a6ac5f0a7e870c50f087f6932b17b061`。两份补丁分别为 `ed19e8a2867adc01b0c881f727f63d8c16159e803cb243e2201c6aeacd46b7ee` 与 `64e1d58b843b857000bc4ae32d5b2ceb529353fb09bdb5ff509741f26296f7bb`。
- Datara **发布后补录**的完整工作树包 SHA-256：`7cb83144a3b90df927967a9f28f9556147525c6fdff7a313b4280f03828bf693`，本机与远端 `source-sync/datara-source.tar.gz` 一致。此包包含补录时新增的真源规则文件，不能追认成发布前的构建输入；本次前后端实际构建输入分别保留在远端 `backend/rebuild/` 和 `frontend/dist/`。今后的发布必须在构建前完成完整源码同步。
- 镜像 ID、HTTP 和容器检查：远端 `release-manifest.txt`、`final-container-check-2.log`、`final-http-check-2.log`。
