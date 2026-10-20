# A3 JSON + PNG remote-final 成对归档规范（草案 v1）

状态：评审草案，未替代标准 v4、A5 冻结契约或 R6 既有验收清单。适用目标是让 Track A 修复验收与 R5-B 后续验收复用同一份可核验的 A3 规则。

## 1. 依据与边界

- 标准 v4 §3 A3 要求证据为 JSON + PNG 成对且达到 `remote-final`；A1-A7 中其他门禁仍分别判定，A3 通过不等于功能验收通过。
- Track A #280 复核指出，测试 stdout 文本不能替代 JSON+PNG 配对证据；R5-A 设计草案 §6 同样要求 A3 成对证据。
- R6 v1.0 §4 已给出 `pair_id`、PNG digest、归档时间和远端回读的先例。本草案沿用这些要素并统一命名、回读核验及配对判定。
- 本规则只定义归档证据格式和核验流程；不规定产品行为、不代表任何能力已通过，也不新增运行时端点。

## 2. 文件路径与命名

每个独立验收用例建立一个目录，避免多个场景互相覆盖：

```text
docs/increments/evidence/{track}/{capability}/{case_id}/{pair_id}.json
docs/increments/evidence/{track}/{capability}/{case_id}/{pair_id}.png
```

- `{track}` 使用稳定域名，例如 `TrackA`、`R5-B`；`{capability}` 使用小写 kebab-case 能力名；`{case_id}` 使用小写 kebab-case、在该能力内唯一。
- `pair_id` 使用 UUIDv4 小写标准格式；一组 JSON 与 PNG 必须共用同一个 `pair_id`，禁止复用到其他用例或提交。
- JSON 为机器可读的证据清单及结果摘要；PNG 为同一用例、同一次运行的 remote-final 页面/终态画面。两文件缺一、路径不匹配或无法证明属于同一次运行时，A3 判 FAIL。
- 一个验收结论涉及多个独立用例时，每例各一对；不得用一张总览截图或一份总 JSON 覆盖彼此独立的判据。

## 3. JSON 最小结构

JSON 使用 UTF-8，根对象至少包含以下字段；额外字段可扩展但不得覆盖字段语义：

```json
{
  "schema": "datara-evidence-pair/v1",
  "track": "TrackA",
  "capability": "audit-writer",
  "case_id": "audit-start-persists",
  "pair_id": "01234567-89ab-4cde-8f01-23456789abcd",
  "source": {
    "commit": "<full-git-commit-sha>",
    "dirty": false
  },
  "run": {
    "command": "<完整可复现命令>",
    "started_at": "<RFC3339 UTC>",
    "finished_at": "<RFC3339 UTC>",
    "exit_code": 0,
    "result": "PASS",
    "output_ref": "<原始 stdout/stderr 的仓库相对路径或稳定远端引用>",
    "assertions": ["<可核验断言及结果>"]
  },
  "artifacts": {
    "png": "<与本 JSON 同目录的 pair_id.png>",
    "png_sha256": "<PNG 原始字节 SHA-256 小写十六进制>"
  },
  "remote_final": {
    "json_uri": "<远端 JSON URI>",
    "png_uri": "<远端 PNG URI>",
    "verified_at": "<RFC3339 UTC>",
    "json_http_status": 200,
    "png_http_status": 200,
    "json_payload_sha256": "<规范化证据载荷摘要>",
    "png_sha256": "<远端回读 PNG 原始字节 SHA-256>"
  }
}
```

安全与真实性要求：不得在证据中包含密码、bearer/token、连接串密钥、业务样本敏感值或未脱敏个人数据。`source.dirty` 必须准确反映被测源代码工作树；若为 `true`，须在 `assertions` 中列出影响本次运行的未提交路径和摘要，不能把 dirty 运行写成干净提交验证。`output_ref` 必须能定位原始命令输出；只写“测试通过”不合格。

## 4. 配对与摘要算法

1. JSON 的 `pair_id` 必须等于文件名 stem，`artifacts.png` 必须指向同目录 `{pair_id}.png`；目录中的 JSON 与 PNG 均须存在且各自只匹配一份。大小写、相对路径和扩展名按上述格式精确匹配。
2. `artifacts.png_sha256` 与 `remote_final.png_sha256` 分别按本地 PNG 和远端 GET 回读 PNG 的原始字节计算，二者必须相同；PNG 必须可解码且非空。
3. 为避免 JSON 在自身记录摘要时发生自引用，`remote_final.json_payload_sha256` 定义为：解析 JSON 后删除整个 `remote_final` 对象，再按 RFC 8785 JSON Canonicalization Scheme 规范化为 UTF-8 字节，对其计算 SHA-256。此摘要用于识别证据载荷，不冒充文件原始字节摘要。
4. 归档器必须对 JSON 与 PNG 都执行远端上传后的 GET/read-back；`json_http_status` 与 `png_http_status` 均须为 200，且返回 HTTP 200 本身不够。JSON 回读后按第 3 条计算的载荷摘要必须与本地一致；PNG 回读原始字节摘要必须与本地一致。远端 URI 应稳定、可由授权评审者读取，不能是上传页面或短时失效的预览 URL。
5. `remote_final.verified_at` 记录两件远端对象均完成回读核验的 UTC 时间；核验前不得生成最终 PASS JSON。若更新此对象后重新上传 JSON，必须再次 GET 并验证 PNG/JSON，直到本地与远端载荷收敛。
6. PNG 截图应展示验收系统中的最终运行结果或 remote-final 归档完成状态，并可辨认对应 `case_id`/`pair_id`、状态和必要时间信息。若 UI 不显示标识，需在受控截图注释/窗口旁显示，不得覆盖产品结果或伪造 UI 状态。截图不能替代 JSON 原始输出，也不能用编辑图片方式改变验收结果。

## 5. remote-final 判定流程

按以下顺序执行并将实际结果写入 JSON：

1. 固定被测提交 SHA、运行命令、开始时间及用例标识；执行验收，保留未经改写的 stdout/stderr，并将关键断言结构化到 JSON。
2. 验收结束后采集同一运行的 PNG；确认运行状态和用例身份与 JSON 一致。失败结果也可以归档，但只能标记 `FAIL`，不能借由归档完成改写为 PASS。
3. 生成 `pair_id`、路径和 JSON/PNG 内容；上传两件文件到具备访问控制和持久 URI 的远端归档目标。
4. 分别 GET 两个远端 URI；验证状态码、JSON 载荷规范化摘要、PNG 原始摘要与本地一致，并检查远端对象可被授权评审者访问。
5. 填入 `remote_final` 回读结果后，重新上传最终 JSON 并再次 GET；确认规范化载荷摘要稳定，远端 PNG 仍与本地 PNG 字节一致。`verified_at` 记录该最终 JSON 所携带的回读轮次完成时间；最终 GET 负责核验记录本身已稳定落在远端，无需再将最终 GET 的纳秒级完成时刻回写进同一文件。
6. 按仓库提交纪律逐文件暂存和提交：先核对 staged diff 只有 JSON，再单文件提交；再核对 staged diff 只有 PNG，单文件提交。第二件提交前不得宣告 A3 PASS；两者最终必须落在同一可审查分支/基线，并可由同一 `pair_id` 配对。

远端存储无法 GET 回读、URI 无法访问、对象哈希不匹配、JSON/PNG 来自不同运行、截图缺失/损坏、提交版本与 `source.commit` 不一致，任一情况都判 A3 FAIL 或待复验，不得以本地文件存在或上传接口返回成功替代 remote-final。

## 6. 评审者核验清单

- [ ] JSON/PNG 两文件存在，目录、`pair_id`、JSON 字段和文件名相互匹配。
- [ ] JSON 可解析且符合 `datara-evidence-pair/v1`；命令、结果、退出码、时间、commit 和原始输出引用齐全。
- [ ] `source.commit` 可解析，且与所声称的实现/测试基线一致；dirty 状态如实披露。
- [ ] PNG 可解码、非空、属于相同用例/运行，并显示真实最终状态。
- [ ] 远端 JSON 与 PNG URI 均可访问并已实际 GET；载荷摘要及 PNG 字节摘要匹配。
- [ ] 无凭据/敏感数据泄露；负向结果没有被标为 PASS。
- [ ] 结论只覆盖该证据直接证明的断言；不将 A3 PASS 扩大成 A1-A7 或整项功能 GREEN。

## 7. 既有口径差异及暂行处理

R6 v1.0 §4 提出 `_meta.json.sha256`（本地 JSON digest）与远端 JSON digest 一致，但若 JSON 文件内包含自身原始字节 SHA-256 字段，会形成自引用，无法稳定计算。本草案暂以“删除 `remote_final` 后按 RFC 8785 计算的载荷摘要”消除自引用；PNG 仍按原始字节 SHA-256。R6 的 `pair_id`、PNG digest、归档时间及远端回读思想保留。此为需评审确认的规范澄清，不回写/静默改版 R6 v1.0。

本草案暂未绑定具体远端存储产品、身份认证方式、保留期或访问审计 API；各实施线须使用项目批准的远端归档设施，并在其证据中给出可访问 URI 和核验结果。若组织要求远端审计回执或签名清单，应作为后续增补，不得据此降低本草案的双对象回读要求。

## 8. 统一引用方式

- Track A 修复验收：本文件作为 A3 配对格式与 remote-final 核验流程；该规范不补足 Gap3/Gap4 的实现缺口。Track A 的 JSON 应记录实际 migration、`create_app` 装配、真实 DB 集成测试等对应证据，不得复用旧 mock 测试结果冒充修复验证。
- R5-B：在其实现/验收材料中引用本文件的路径、版本和具体 `case_id` 配对；DDL policy、impact preview、确认写入、补偿/回滚等独立场景各自归档，不得由单个截图覆盖多个权限/失败路径。
- 标准 v4 与 A5 冻结契约保持原样。本草案经监督线评审/采纳后，才能作为后续验收统一引用；在采纳前引用状态必须标注“草案”。
