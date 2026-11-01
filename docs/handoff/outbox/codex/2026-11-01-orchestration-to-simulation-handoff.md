# 编排网关 → 仿真测试交接卡

## 已落地文件/证据

- C7 治理清理契约证据：`2026-11-01-governance-cleanup-evidence.md`，专项回归 17 passed。
- 环境组默认选择与 `tt` 保存诊断已分别登记。
- C8 仿真样本已在 1.9 隔离环境导入：`ecom_sim_20261030` 库 13 张事实表行数与 fixture manifest 一致，
  `fixture_namespace` 唯一值 `ECOM_SIM_20261030`；project 33 的 4 个 `ecom_sim_20261030_*` 变量幂等校验 unchanged。
- 三条 `[ECOM-SIM-20261030]` 工作流均 ONLINE 并在 1.9 真实运行 SUCCESS（实例 13/14/15，任务 49/50/51），
  SQL 节点输出真实业务行。
- 1.9 证据目录：`/lei/datara/deployments/codex-main-20261101-0635/evidence/`，
  汇总卡 `2026-11-01-orchestration-e2e-evidence.md`。

## 1.9 部署变更（需 codex 侧知悉，均已备份）

1. `/lei/apps/dbx/deploy-1.9/docker-compose.yml`：`DBX_DATARA_GATEWAY_ONLY=0→1`
   （备份 `docker-compose.yml.bak-gateway-only-20261101`），修复内部连接参数 503。
2. `/lei/apps/ds-3.4.3-deploy-20261029/.env`：追加 `WORKER_TENANT_CONFIG_DEFAULT_TENANT_ENABLED=true`
   （备份 `.env.bak-tenant-20261101`），修复 tenantCode=default 校验失败。
3. `/lei/apps/ds-3.4.3-deploy-20261029/docker-compose.yml`：worker 增加
   `./jdbc/mysql-connector-j-8.0.33.jar` 单文件挂载（备份 `docker-compose.yml.bak-jdbc-20261101`），
   修复 `ClassNotFoundException: com.mysql.cj.jdbc.Driver`。正式做法应把驱动打进 worker 镜像。

## 未完事项

- `DATARA_PUBLIC_BASE_URL` 仍为 `http://192.168.1.9:18091`，与「入口固定 8090」裁定不一致；
  海豚 UI 跨源回退守卫当前不阻断，建议随下次发版改 8090。
- 浏览器级逐页验收（8090 画布实际渲染、节点表单数据源下拉）未取证，当前证据止于
  HTTP + 网关 API + 海豚侧真实执行三层。

## 下次第一步

在 8090 用 browser-use 打开 `/p/33/dag`，确认画布渲染、三条定义可见、节点表单数据源下拉非空，
并回填本卡浏览器证据。

## 涉及节号

收口计划 §三 C8；权威设计 §六、§10.7、§10.9。
