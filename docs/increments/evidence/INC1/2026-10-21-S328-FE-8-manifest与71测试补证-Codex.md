# S328 FE-8 manifest 与 71 测试补证

## 补证结论

- 本文补齐 S328 对 S320 FE-8 的两项保留：完整列出 FE-8 的 7 个实现/登记文件与 6 个精确测试文件，并为 13 个文件提供当前工作区 SHA256。
- 按原 FE-8 精确命令复跑，结果为 `Test Files 6 passed (6)`、`Tests 71 passed (71)`，退出码 0。
- `scheduleApi.ts`、`sqlIdeDdlApi.ts` 仍为业务 RED/零 I/O；本补证不改变原交付边界。

## 精确测试命令与结果

工作目录：`D:\需求\数据治理工具\Datara\datara-newweb`

```text
rtk npx vitest run src/services/__tests__/http.test.ts src/services/rebuild/__tests__/syncComponentApi.contract.test.ts src/services/rebuild/__tests__/sqlIdeApi.contract.test.ts src/services/rebuild/__tests__/streamApi.contract.test.ts src/services/rebuild/__tests__/scheduleApi.contract.test.ts src/services/rebuild/__tests__/sqlIdeDdlApi.contract.test.ts

RUN  v5.0.5 D:/需求/数据治理工具/Datara/datara-newweb
Test Files  6 passed (6)
Tests       71 passed (71)
Duration    1.74s
exit code   0
```

六个测试文件精确路径：

1. `datara-newweb/src/services/__tests__/http.test.ts`
2. `datara-newweb/src/services/rebuild/__tests__/syncComponentApi.contract.test.ts`
3. `datara-newweb/src/services/rebuild/__tests__/sqlIdeApi.contract.test.ts`
4. `datara-newweb/src/services/rebuild/__tests__/streamApi.contract.test.ts`
5. `datara-newweb/src/services/rebuild/__tests__/scheduleApi.contract.test.ts`
6. `datara-newweb/src/services/rebuild/__tests__/sqlIdeDdlApi.contract.test.ts`

## 完整 manifest（当前工作区 SHA256）

| 类型 | 文件 | SHA256 |
|---|---|---|
| 实现 | `datara-newweb/src/services/http.ts` | `9688a85c70c54509922a267a22708f7670c65f92cac27da87672e2064c42f5f4` |
| 实现 | `datara-newweb/src/services/rebuild/syncComponentApi.ts` | `58bb6b1b22974adee919cf549f3842f0882397280dde5d35331cf2fbfee66cda` |
| 实现 | `datara-newweb/src/services/rebuild/sqlIdeApi.ts` | `9219639943c923023ca216397640b86ec23f8b295840bcd1672bbc2a08b89ca8` |
| 实现 | `datara-newweb/src/services/rebuild/streamApi.ts` | `013d69e76e26a6cb49452d0644e4b028624d4c318359624557aa7c16cd99a91c` |
| 实现 | `datara-newweb/src/services/rebuild/scheduleApi.ts` | `545719bd54e3971775c0f120294a1fbc478f771679ca66545ad38ae3524733a9` |
| 实现 | `datara-newweb/src/services/rebuild/sqlIdeDdlApi.ts` | `fc629624a986a3c732e4012c58e0593e126d49f5acb0d7e61727bc3cce4af7dd` |
| 登记 | `datara-newweb/src/services/rebuild/CONTRACT_REGISTRY.md` | `427fdff733475f94d4744874ec4ac7403527a5733e7feee853f128d79cd62a09` |
| 测试 | `datara-newweb/src/services/__tests__/http.test.ts` | `f10621f50419e2bc8ffc6970fc3970c149590b8d17f29e74079a4149bfd462b4` |
| 测试 | `datara-newweb/src/services/rebuild/__tests__/syncComponentApi.contract.test.ts` | `83714a54150c9b256b439f4163ef345aa2dee947ee6c28d73a242bbaf8b6aeac` |
| 测试 | `datara-newweb/src/services/rebuild/__tests__/sqlIdeApi.contract.test.ts` | `b7e32cd2fc4d9b4e0194af47790bcde0ffb418e4b4e70c8d250451ace0ec0afe` |
| 测试 | `datara-newweb/src/services/rebuild/__tests__/streamApi.contract.test.ts` | `5d948d26938ee6e6b86a7828813e0aeecf7b145e296699b39400c0bd8bcc0569` |
| 测试 | `datara-newweb/src/services/rebuild/__tests__/scheduleApi.contract.test.ts` | `bd784b89e3232312d614cb9a78176ad9fdd58d5b974b9fcf85103ac0c3dca3d2` |
| 测试 | `datara-newweb/src/services/rebuild/__tests__/sqlIdeDdlApi.contract.test.ts` | `067f0e593fcc3f9c770a776cd8b244bc7136a3ba7d6474b0cff7cb975f579113` |

说明：`CONTRACT_REGISTRY.md` 为共享登记文件，SHA256 取补证时当前工作区内容；其值较 S320 原证据变化来自后续并行登记。

提交号：无，工作区改动，待监督线代提交。
