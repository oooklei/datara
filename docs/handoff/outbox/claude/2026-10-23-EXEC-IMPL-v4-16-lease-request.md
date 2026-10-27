# RT 租约请求 · RT-IMPL-V4-16-MONITOR-COMPONENT

- **请求席**：Execution EXEC-3（claude 载体）
- **票**：IMPL-v4-16（17.3 集群监控页组件段，v3-0060 派单）
- **时间**：2026-10-23T02:2x+08:00｜**水位**：v3-0060
- **目标主机**：192.168.1.9（唯一测试执行面，TEST-ENVIRONMENT-POLICY / A5-E2：本机 vitest 属越界）

## 请求内容

在 1.9 面执行 IMPL-v4-16 组件测试（仅组件测试，无路由注册故无 e2e 面）：

```
cd <隔离树>/datara-newweb
npx vitest run src/views/__tests__/monitorView.contract.test.ts
```

- **用例数**：6（清单见 `2026-10-23-EXEC-IMPL-v4-16-EVIDENCE-claude.md` §4）
- **制品身份**：两新文件（`src/views/depops/MonitorView.vue` + `src/views/__tests__/monitorView.contract.test.ts`），commit 未产生（候集成窗）
- **单环境串行**：可并入在途 RT 队列（当前 READY：RT-IMPL-V4-03、RT-IMPL-V4-02a、RT-IMPL-V4-07；LEASE-01 在途），由 Integration 裁定回执与排窗
- **证据绑定要求**：租约 ID、commit/制品身份、执行命令、时间戳、退出码、日志、执行者——七要素齐备

## 红线声明

- 本机零 vitest 执行（A5-E2 口径）；本请求先于任何 1.9 执行
- 不改 FE-SHELL（routes/menu）、不改 monitorApi.ts 与后端；契约缺陷即停票上报
- RED/GREEN 证据独立留存，重跑不覆盖

—— Execution EXEC-3（claude），租约请求呈递，候 Integration 回执。
