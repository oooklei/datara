# 客户观摩入口与页面品牌收口（2026-10-31）

## 已落地文件

- `datara-newweb/src/services/rebuild/embeddedBranding.ts`
- `datara-newweb/src/views/ide/DbxIdeView.vue`
- `datara-newweb/src/views/TaskCenterView.vue`
- `datara-newweb/src/components/DsRunMonitor.vue`
- `datara-newweb/src/views/depops/MonitorView.vue`
- `datara-newweb/src/views/resources/ResourceScriptEditorDialog.vue`
- `datara-newweb/src/views/qc/QualityExceptionView.vue`
- `datara-newweb/src/views/qc/QualityRuleView.vue`
- `datara-newweb/src/views/qc/QualityTaskView.vue`
- `deploy/wsl-frontend/*` 观摩入口默认地址统一为 8090
- `docs/plans/2026-10-30-consolidation-and-simulation-todo.md` §六

## 部署与验证

- 1.9 `datara-newweb-web` 已重建为 `datara-newweb:closeout-20261031`，端口 `8090:80`。
- 原 `18091` 容器重命名为 `datara-newweb-web-18091-backup`，仅保留回滚，不作为客户入口。
- `npm run build`：通过。
- `npx vitest run src/views/ide/__tests__/dbxIdeSession.contract.test.ts src/views/__tests__/taskCenterView.contract.test.ts`：37 passed。
- 1.9 浏览器：8090 HTTP 200；IDE session 200；变量面板 15 项；宿主/IDE/编排 iframe 文案禁词命中 0。

## 遗留

- DBX 运行镜像未包含内部 token patch，`/ide/api/migration/status` 仍经后端返回 502；需进入 DBX 域重建镜像或补丁后验证。
- Dolphin patch、`tt` 全量保存/运行回归仍待编排域继续。

## 下一步

1. 让用户在 `http://192.168.1.9:8090/` 实测并反馈缺陷。
2. 下一票优先处理 DBX 内部 token/迁移状态 502，再重跑 §10.7。

## 提交

- `1db647ef`：观摩入口、品牌文案与嵌入页文案收口。
