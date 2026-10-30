# D5-v2-EXEC 监督线代执行证据

- 日期：2026-10-19 03:17–03:20 Asia/Shanghai
- 执行者：监督线（Codex rtk ssh 受沙箱策略拒 exit 255，监督线 `ssh root@192.168.1.9` 实测可达，经 S31 备案代执行；代执行先例 S17）
- 批准锚：用户批准执行窗口（S29，2026-10-19 02:49+08:00）+ 方案 v2 复评 PASS（S28，方案 03e65e9）
- 方案：docs/increments/2026-10-19-Codex-D5-远端部署方案.md（v2，bind-mount 同步形态）

## 步骤①：本地预检+基线清单
- 执行基线 HEAD：`8cc02c6e91340088159af408cf27560fe879eab6`
- `git status --short -- datara-backend/rebuild/` → 无输出（pathspec clean）
- 基线清单：`docs/increments/evidence/2026-10-19-监督线-D5v2-baseline-local.txt`（158 文件，相对路径+SHA-256，含 `__pycache__` 全量口径）

## 步骤②：备份→同步→指纹对照
- 远端备份：`/lei/datara/rebuild-source/rebuild-backup-20261019-031738.tar.gz`（176,971 字节）
  - sha256：`de159d6b6d2fe9dcabb3554b5bce4318d53e926621e4c41d861a1373fb1d1a28`
  - 归档可读核验：`tar tzf` 列目录成功（rebuild/、rebuild/__init__.py、rebuild/governance/）
  - 同步前远端文件数：82
- 同步：本地 `tar czf` 打包（-C datara-backend rebuild）→ `scp` 上传 /tmp → 远端 `find rebuild -mindepth 1 -delete`（保留目录 inode，bind-mount 安全）→ `tar xzf` 全量解压
- 同步后远端文件数：158（=本地）
- **双端 SHA-256 逐项对照：158/158 全部一致（MANIFEST_MATCH_ALL_158=yes）**

## 步骤③：单容器重启+验收
- 命令：`docker restart datara-rebuild-api`（仅此容器；无镜像构建/Compose up/其他容器操作）
- 重启后容器状态：`running|healthy`（healthcheck 就绪后）
- 验收（远端本机经 nginx :18091 只读 GET）：
  - `GET /api/v1/rebuild/health` → **HTTP 200**，body `{"code":0,"msg":"success","data":{"service":"rebuild-api","status":"ok"}}`
  - `GET /api/v1/rebuild/ai/tools` → **HTTP 401**，body `{"code":1001,"msg":"invalid token","data":null}`（受保护端点已挂载，未认证 401=预期）
- 过程记录：重启后 10s 首查为 502/starting（healthcheck start_period 20s 内），25s 后复验即达标；无回滚需要。

## 结论
- 验收 PASS，未触发任何停止条件，未执行回滚。
- **A3 remote-final PASS 达成**（远端终态=health 200 + ai tools 401，与本地已验证生产装配一致）。
- Track A GREEN 前置收敛完毕（A1 隔离基线 RED 采信闭环 S17 + A3 本条 + #322 接线局部 PASS + 45 项定向测试 PASS）。
