# `tt` 工作流保存网络证据

## 验证入口

- 脚本：`deploy/wsl-frontend/verify-tt-save-network.cjs`
- 命令：`DATARA_DS_VERIFY_TOKEN=<admin短时token> node deploy/wsl-frontend/verify-tt-save-network.cjs http://192.168.1.9:18091 33`

## 1.9 结果（重新合并部署后）

- 工作流：`tt`，项目 33，DS workflow code `188346193457664`。
- 保存请求：`PUT /dolphinscheduler/projects/188273928846848/workflow-definition/188346193457664`。
- 请求体摘要：非 JSON 文本体，长度 `3185` 字节（脚本不输出脚本内容或凭据）。
- 响应：HTTP `200`，`code=0`，`msg=success`，`failed=false`，`success=true`；版本从 3 到 4，随后重复验证版本继续递增。

## 判定

当前 1.9 重新合并部署版本无法复现用户报告的“请求参数无效”错误；保存链路已实际成功。保留诊断脚本用于后续若再次出现非 2xx 时自动采集 URL、请求体摘要与响应 code/msg。

## 遗留

- 本次为无业务字段改动的保存回验，但 DS 版本号会递增；后续复测应避免高频重复点击。
- 若问题再次出现，需保存脚本输出中的失败响应后再进入编排后端修复，不凭旧现象改写参数契约。

## 涉及节号

收口计划 §三 B5；权威设计 §六、§10.4、§10.8。
