# I19 数据开发 IDE 对象编辑与跨 Schema 查询

## 目标

对齐 DBX 类数据库开发体验：从左侧资源树浏览并打开表、视图、存储过程、函数、触发器和事件；跨 Schema 对象可直接生成可执行 SQL；常规治理标识符不再被无意义的反引号包裹。

## 实现口径

- `GET /datasources/{id}/databases/{schema}/routines` 统一返回 procedure、function、trigger、event 元数据，按 Schema 懒加载并限制返回上限。
- `GET .../routines/{name}/ddl?kind=...` 使用数据库 `SHOW CREATE` 返回编辑器文本；点击资源树对象只填充编辑器，不自动执行。
- 表、视图、列、索引 SQL 使用标准标识符规则：`schema.object` 直接输出；名称含空格、短横线或其他非标准字符时才按需转义，避免破坏可执行性。
- SQL 执行器支持普通多语句、`BEGIN … END` 复合例程以及 `DELIMITER //` 脚本，防止过程/函数内部分号被错误拆分。

## 联调取证

1. 1.9 实例 `datara_dw` 展开后可见 Tables、Views、Procedures、Functions、Triggers、Events 六类节点。
2. 后端例程列表请求均返回 200；已准备 `ide_demo_proc`、`ide_demo_func` 用于界面演示。
3. 点击 `ide_demo_proc` 发起 `/routines/ide_demo_proc/ddl?kind=procedure`，编辑器显示可编辑 SHOW CREATE 内容；点击不自动执行。
4. 表菜单“行数统计”对常规表生成 `SELECT COUNT(*) AS cnt FROM datara_dw.i12_ods_order_file;`，无反引号污染；非标准名称仍保留必要转义。
5. 后端回归：`558 passed in 46.84s`；SQL splitter 专项 4/4 通过；前端 `npm run build` 通过（仅保留既有 Monaco 大包告警）。

## 约束

数据库返回的 SHOW CREATE 原文可能包含数据库为保证执行语义而生成的反引号，此类反引号不属于资源树 SQL 引用污染，不做破坏性剥离。
