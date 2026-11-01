# 领域文档

Engineering skills 探索 codebase 时，应如何消费这个 repo 的 domain documentation。

## 探索前先读取这些

1. **`docs/designs/2026-11-01-datara-current-authority.md`**（现时唯一实施权威）：系统边界与角色见 §二，数据分层与七级变量见 §八，身份与权限见 §九。这些节即当前领域术语的权威定义。
2. **`GLOSSARY.md`**（repo 根目录）：**当前不存在**。术语暂以权威设计 §二/§八/§九 为准；只有确实出现跨文件术语漂移时才新建，不要提前创建。
3. **`docs/adr/`**：**当前为空**（2026-10-31 前的 ADR 已归档至 `docs/archive/2026-11-01-authority-refresh/`）。新的架构裁定优先直接写入权威设计的「已裁定前提」与「已知冲突」两节；只有在需要记录被否决的备选方案时才重建 ADR。

如果这些文件不存在，**静默继续**。不要标记缺失；不要提前建议创建。

## 使用统一词汇

当你的输出命名某个 domain concept 时（issue title、refactor proposal、hypothesis、test name），使用权威设计中已定义的 term：

| 概念 | 权威用词 | 避免的同义漂移 |
| --- | --- | --- |
| 数据访问层 | dbx | dbx-ide、DBX 服务（作为系统名时用 dbx） |
| 画布与调度 | 海豚 / DolphinScheduler | DS、调度平台 |
| 门户前端 | datara-newweb | 新前端、web |
| 后端 | datara-rebuild-api（容器 `dt-rebuild`） | rebuild 服务、薄后端 |
| 画布接入方式 | iframe 同源直连 | 编排网关、代理网关（均已取消） |
| 嵌入令牌 | `X-Datara-Embed-Token`（cookie `datara_dbx_embed`） | 前端 token、localStorage token |

如果你需要的概念还不在上表或权威设计中，这是一个信号：要么你正在发明项目没有使用的语言（重新考虑），要么确实存在缺口（补入权威设计对应章节）。

## 标记冲突

如果你的输出与权威设计矛盾，明确指出，而不是静默覆盖：

> _与权威设计 §三「三条唯一正确路径」冲突（该路径已取消），但值得重开，因为…_
