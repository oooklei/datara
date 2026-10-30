# Codex T-1 复验回执：DBX × 原版 SQLIDE 融合对照清单 v2.1

- 评审对象：`docs/increments/2026-10-17-DBX-原版SQLIDE-融合对照清单.md`
- 评审版本：v2.1，提交 `45317c2`
- 复验范围：前次回执 `2026-10-17-Codex-T1-P1-7-review-v2-recheck.md` 的第 1 项；核对 §2.4 的对象覆盖、路由分组、L/G/N 逐操作状态、E/V/D/X/R 注记和证据锚点。
- **结论：FAIL（有实质补充，但矩阵仍有未定义单元格，未达到闭环条件）**。

## 复验结果

§2.4 已有显著改进：补入 MATERIALIZED_VIEW 与此前缺少的 EVENT、SEQUENCE、SYNONYM、JOB、PACKAGE、PACKAGE_BODY、TYPE、TYPE_BODY；按 8 个后端路由组合分组，提供源码行锚、声明面差异，并声明编辑/校验/依赖/执行/回滚共性及证据边界。**未见遗漏对象行**，未知情况总体有诚实披露。

但其表头将每个路由格定义为 **L/G/N = list/get-definition/generate**，取值又定义 V/C/U/N/NA。表中部分格未为三个操作逐一给状态，也未定义空白的语义；若空白表示未知，应明确写 U，若不适用或不支持则应写 NA/N 并给出理由。具体例子：

1. **SQLite 族列多处只写 `G=U`**：SEQUENCE、MATERIALIZED_VIEW、EVENT、SYNONYM、PACKAGE/PACKAGE_BODY、TYPE、TYPE_BODY、JOB 均没有显式 L 与 N 状态。现有注记只解释了若干 G getter 路由，不能推出对象发现和 DDL 生成状态。
2. **其他路由格也有缺项**：EVENT × Agent Driver 只列 L/G；SYNONYM × OceanBase Oracle mode 只列 L/G；PACKAGE/PACKAGE_BODY × OceanBase Oracle mode 只列 L/G；TYPE_BODY × Agent Driver 只列 L/G；JOB × Agent Driver 只列 L/G。缺失的 N（DDL generate）状态没有定义。
3. **裸 `N` 的含义不确定**：TYPE_BODY × OceanBase、TYPE_BODY × PostgreSQL/PG 特殊路由、JOB × OceanBase、JOB × PG 特殊路由格只写 `N`。由于 `N` 同时是操作符号（generate）和状态值（unsupported），且这些格没有 `L=`/`G=`/`N=` 前缀，不能判断它是“该对象全部不支持”还是“仅 DDL 生成不支持”。

以上不是要求把未知能力补成已支持，而是要求把所有缺失操作明确标为 **U/Unknown**、**NA** 或 **N**，并保留相应理由和源码锚点。修订时可为各对象/路由格统一填写 `L=… G=… N=…`；对合并的对象类型要证明共享相同路由/状态，或拆行。E 列共性 `U` 与 PG trigger 显式只读例外的解释可保留；V 仅证源码路径、不证运行成功的限制也应保留。

## 判断及边界

- §2.4 已满足补入缺失对象行、路由组、主要锚点及 Unknown 诚实披露的要求，但尚未完整映射每格的发现/定义读取/DDL 生成操作，因此不能据此关闭前次复评第 1 项。
- 复验结论仅针对这份文档的矩阵完备性；不否认 DBX 源码能力，也不要求将未知项推断为不支持。
- 本次不修改 v2.1 正文，不改 R5 契约，不触碰业务代码或 `datara-web`；文档复验未运行测试，无远端 push。
