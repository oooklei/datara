# RT 租约请求 · RT-IMPL-V4-08-OPENAPI-CONTRACT

- **请求席**：Execution EXEC-3（claude）
- **票**：IMPL-v4-08（API 管理 15-P0 契约冻结，v3-0072 重派本席）
- **时间**：2026-10-23T03:1x+08:00｜**水位**：v3-0074
- **目标主机**：192.168.1.9（唯一测试执行面，A5-E2 口径：本机 vitest 属越界）

## 请求内容

在 1.9 面执行 IMPL-v4-08 契约测试（纯契约层 RED 套件，零后端依赖）：

```
cd <隔离树>/datara-newweb
npx vitest run src/services/rebuild/__tests__/openapiAdminApi.contract.test.ts
```

- **用例数**：9（清单见 `2026-10-23-EXEC-IMPL-v4-08-EVIDENCE-claude.md` §4）
- **制品身份**：三新件（`services/rebuild/openapiAdminApi.ts` + 契约测试 + `docs/increments/evidence/API/2026-10-22-15-P0-契约冻结.md`），commit 未产生（候集成窗）
- **单环境串行**：并入在途 RT 队列（现序 RT-03→RT-02a→RT-07→RT-16），排尾即可，无窗口紧迫性（纯契约套件、秒级完成）；由 Integration 裁定回执
- **证据绑定**：租约 ID、commit/制品身份、执行命令、时间戳、退出码、日志、执行者——七要素齐备

## 红线声明

- 本机零 vitest 执行；本请求先于任何 1.9 执行
- 不建表、不写业务实现（RED 骨架零 I/O 验收 ⑦）；不改 identity/后端任何件
- 契约冻结候 Acceptance A2 独立评审 PASS（验收 ⑤，与 1.9 GREEN 并行链）

—— Execution EXEC-3（claude），租约请求呈递，候 Integration 回执。
