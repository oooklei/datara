# 前端环境组默认选择收口卡

## 改动文件

- `datara-newweb/src/services/rebuild/environmentContext.ts`
  - 首次加载项目环境组时优先选择 `default-env`，无该名称时按接口顺序选择第一项。
  - 用 `null` 保存用户显式“未选择”，刷新不会抢回默认值。
  - 选择仍由同一 context 同时提供给 DBX 与 Dolphin 会话桥。
- `datara-newweb/src/services/rebuild/__tests__/environmentContext.contract.test.ts`
  - 覆盖默认选择与显式空态保持。

## 验证

- `npx vitest run src/services/rebuild/__tests__/environmentContext.contract.test.ts src/views/__tests__/taskCenterView.contract.test.ts`：`33 passed`。
- `npm run build`：通过（`vue-tsc -b` + Vite）。首次增量检查遇到删除文件缓存，执行 `npx vue-tsc -b --force` 后复核构建通过；删除文件为工作区既有改动，未在本票恢复。

## 遗留项

- C7–C14 仿真/治理清理仍未完成；本票只收口环境组跨 DBX/海豚上下文。

## 涉及节号

收口计划 §三 B5；权威设计 §六、§10.8、§10.9。
