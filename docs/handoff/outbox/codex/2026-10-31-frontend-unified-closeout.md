# 前端统一收口交接（2026-10-31）

## 本票范围

- 单域：前端页面。
- 涉及：组件规格首载失败回显/重试、项目成员业务码保留与中文映射、资源文件页删除残留核查。

## 已落地

- `datara-newweb/src/components/Palette.vue`
  - 组件规格首载失败显示“组件清单加载失败，请重试”。
  - 增加可操作“重试”，重试成功恢复组件列表；无匹配空态不再覆盖错误态。
- `datara-newweb/src/services/rebuild/memberApi.ts`
  - 成员四端点启用 `preserveEnvelopeCode`。
  - 4041/4042/4091 保留业务码并映射中文释义。
- 契约测试：
  - `src/components/__tests__/palette.contract.test.ts`
  - `src/services/rebuild/__tests__/memberApi.contract.test.ts`

## 验证

- `npx vitest run src/services/rebuild/__tests__/memberApi.contract.test.ts src/components/__tests__/palette.contract.test.ts`：28 passed。
- `npm run build`：通过（仅已有 chunk size warning）。
- 1.9 已直接同步构建产物至 `datara-newweb-web` 并 reload nginx。
- 1.9 `verify-auth-switch-wsl.cjs`：通过，IDE 200、匿名 DBX API 401、admin 页面可见、无持久化 token、无 page error。
- 1.9 组件规格接口实测：`GET /api/v1/rebuild/components/spec?workflow_type=NORMAL` 返回 200、强 ETag、有效 `items`。

## 待继续

- 1.9 DAG 真实页面的组件栏/重试按钮浏览器回验需在正确打开工作流画布后执行；当前直接访问 `/p/33/dag` 只到工作流列表。
- 交接给后续 dbx/编排域：DBX 升级状态失败、Dolphin patch 重新部署与 §10.7 全量回归。
- 用户已授权：后续可直接在 1.9 改前后端并联调；未经通知不回灌本机 main。

## 提交

- 本机前端代码：`af2ead91`。
