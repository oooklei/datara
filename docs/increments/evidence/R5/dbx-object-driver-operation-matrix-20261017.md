# DBX SQL IDE：对象类型 × 驱动 × 操作证据矩阵

范围：只读静态检查 `D:\dbx-main`，未运行测试。支持只表示发现明确代码路径；driver UI capability、服务端权限、运行成功彼此不等同。“未发现”仅限本次核对的 SQL IDE/schema 路径。

## 驱动清单与后端选路

前端侧栏按 database type 显式声明的对象集合（不是完整操作能力认证）：

| database type | 声明对象 |
|---|---|
| postgres、gaussdb、opengauss | TABLE/VIEW/MATERIALIZED_VIEW/PROCEDURE/FUNCTION/SEQUENCE/TYPE |
| kwdb | 同上但不含 TYPE |
| kingbase | 上述集合 + TRIGGER |
| vastbase | 上述集合但不含 TRIGGER |
| highgo、uxdb、redshift | TABLE/VIEW/MATERIALIZED_VIEW/PROCEDURE/FUNCTION |
| oracle、oceanbase-oracle | TABLE/VIEW/MATERIALIZED_VIEW/PROCEDURE/FUNCTION/SEQUENCE/SYNONYM/PACKAGE/PACKAGE_BODY |
| dameng | Oracle 集合但无 SYNONYM |
| xugu | TABLE/VIEW/PROCEDURE/FUNCTION/TRIGGER/SEQUENCE/SYNONYM/PACKAGE/PACKAGE_BODY/TYPE/TYPE_BODY |
| mysql | TABLE/VIEW/PROCEDURE/FUNCTION/TRIGGER/EVENT |
| sqlserver | TABLE/VIEW/PROCEDURE/FUNCTION |
| sqlite、rqlite、turso、cloudflare-d1、duckdb、clickhouse、doris | TABLE/VIEW |
| starrocks | TABLE/VIEW/MATERIALIZED_VIEW |
| hive、argo | TABLE/VIEW/PROCEDURE/FUNCTION |
| transwarp | TABLE/VIEW/PROCEDURE/FUNCTION/PACKAGE/PACKAGE_BODY |
| kyuubi、impala、spark、trino、prestosql、cassandra、bigquery、spanner、kylin、ignite、ignite3、tdengine、iotdb、neo4j、nebula | TABLE/VIEW |
| influxdb、influxdb3、victoriametrics、hbase、salesforce | TABLE |
| questdb | TABLE/VIEW/MATERIALIZED_VIEW |
| manticoresearch | TABLE/FUNCTION |
| databend | TABLE/VIEW/PROCEDURE |

证据：[databaseObjectCapabilities.ts:3-10,42-110](D:/dbx-main/apps/desktop/src/lib/database/databaseObjectCapabilities.ts)。此文件说明 sourceReadable 是 sidebar 集合过滤后的值（TYPE 另受 Xugu 限制），并非后端实现认证；PG 家族 TYPE 可列举但没有统一 CREATE TYPE getter；Doris 因后端缺 MV 分类路径暂不开放。未显式列出的 DB type 会走默认集合，不因此获得操作保证（同文件:112-129,174-190）。

后端实际路由分为 Native Pool、Agent、ExternalDriver/JDBC 与专用/sidecar，不是每个连接类型都有独立 crate：

- Native MySQL pool：OceanBase Oracle、Manticore、SHOW metadata 特判；常规 list 对象由 MySQL handler 处理。[native.rs:81-109](D:/dbx-main/crates/dbx-core/src/schema/providers/native.rs) [schema/mod.rs:7238-7249](D:/dbx-main/crates/dbx-core/src/schema/mod.rs)
- Native PostgreSQL pool：QuestDB、Cloudberry、Redshift、openGauss 有单独分支；常规 PG 可列 relations/routines/custom types，openGauss packages 独立追加。[schema/mod.rs:7252-7293](D:/dbx-main/crates/dbx-core/src/schema/mod.rs)
- Native SQLite/rqlite/Turso/Cloudflare D1/DuckDB/ClickHouse：定义读取有专门分支，ClickHouse 只对 VIEW 有 source getter。[schema/mod.rs:10838-10905](D:/dbx-main/crates/dbx-core/src/schema/mod.rs) [native.rs:278-320](D:/dbx-main/crates/dbx-core/src/schema/providers/native.rs)
- SQL Server：专用 list 与 catalog SQL source getter。[schema/mod.rs:7101-7104,10779-10789](D:/dbx-main/crates/dbx-core/src/schema/mod.rs)
- Agent：listObjects constrained 与 getObjectSourceForRelation RPC；Oracle 另有目录查询分支。具体对象支持依 Agent 实现。[schema/mod.rs:7105-7153,10790-10837](D:/dbx-main/crates/dbx-core/src/schema/mod.rs)
- ExternalDriver/JDBC：通过 listObjects/getObjectSource 插件 RPC；Presto-like 列表走 information_schema 特判。RPC 存在不证明每种插件都实现每种对象。[schema/mod.rs:7067-7099,7331-7342,10738-10777](D:/dbx-main/crates/dbx-core/src/schema/mod.rs)

### 1.3 执行路径 × 对象 × 操作的证据矩阵

下表把同一后端路由的 database types 合并，不把路由说成独立适配器。单元格以 **L/G/E/N/V/D/X/R** 对应 list / get-definition / edit / generate / validate / dependency / execute / rollback；各格列出状态与源码可证范围：**V=Verified（源码直接路由/实现）**、**C=Conditional（路径存在，但受对象类型、DB配置、Agent/JDBC实现、数据库版本或权限约束）**、**U=Unknown（本次不能证明）**、**N=Unsupported（源码明确拒绝/只读）**、**NA=Not applicable（对象不属于该API类型）**。这里的 Verified 只证明代码路径，不证明外部数据库运行成功。

| 后端路由与覆盖database type | TABLE | VIEW | PROCEDURE / FUNCTION | TRIGGER | INDEX |
|---|---|---|---|---|---|
| **Native MySQL pool**（mysql及mysql protocol兼容连接；特殊分支另见下行） | L=V, G=V(table DDL), E=C(structured), N=V(DDL), V=U, D=C(Schema Diff), X=C, R=C(Schema Diff only) | L=C, G=V, E=C, N=V(view builder), V=U, D=C(view text scan), X=C, R=C(Schema Diff only) | L=V, G=V, E=C, N=C, V=U, D=U, X=C, R=U | L=V(table-scoped), G=C, E=U, N=U, V=U, D=C(trigger text scan), X=C, R=U | L=V, G=NA, E=NA, N=C(Schema Diff), V=U, D=NA, X=C, R=C(Schema Diff) |
| **OceanBase Oracle mode**（MySQL Pool独立mode） | L=V, G=C, E=C(structured), N=C, V=U, D=C, X=C, R=U | L=C, G=C, E=C, N=C, V=U, D=C, X=C, R=U | L=C, G=U, E=U, N=U, V=U, D=U, X=C, R=U | L=V(table-scoped), G=U, E=U, N=U, V=U, D=U, X=C, R=U | L=V, G=NA, E=NA, N=C, V=U, D=NA, X=C, R=C |
| **PostgreSQL pool**（postgres、gaussdb、kwdb、opengauss、kingbase、highgo、uxdb、vastbase、redshift；每个type有例外） | L=V, G=V(table DDL), E=C(structured), N=V, V=U, D=C(FK graph), X=C, R=C(Schema Diff only) | L=V, G=V, E=C, N=V, V=U, D=C(view text scan), X=C, R=C(Schema Diff only) | L=V, G=C(signature-aware), E=C, N=C, V=U, D=U, X=C, R=U | L=C, G=C, E=N(PG-family editable=false), N=U, V=U, D=C(trigger text scan), X=C, R=U | L=V(provider-dependent), G=NA, E=NA, N=C(Schema Diff), V=U, D=NA, X=C, R=C(Schema Diff) |
| **QuestDB / Cloudberry / Redshift / openGauss special routes** | L=V, G=C, E=C, N=C, V=U, D=C, X=C, R=C(Schema Diff only) | L=V, G=C(QuestDB code says view only), E=C, N=C, V=U, D=C, X=C, R=C(Schema Diff only) | L=C(Redshift/openGauss paths), G=U(QuestDB only view verified), E=U, N=U, V=U, D=U, X=C, R=U | L=C, G=C, E=N(PG-family source flag), N=U, V=U, D=C, X=C, R=U | L=C(PG provider), G=NA, E=NA, N=C, V=U, D=NA, X=C, R=C |
| **SQLite / rqlite / Turso / Cloudflare D1 / DuckDB / ClickHouse dedicated paths** | L=V, G=C(driver DDL branch), E=C(structured), N=C, V=U, D=C, X=C, R=C(Schema Diff only) | L=C, G=C(SQLite/rqlite/Turso/D1/DuckDB branches; ClickHouse VIEW only), E=C, N=C, V=U, D=C, X=C, R=C(Schema Diff only) | L=U, G=U, E=U, N=U, V=U, D=U, X=C(generic SQL only), R=U | L=U, G=U, E=U, N=U, V=U, D=U, X=C(generic SQL only), R=U | L=C(SQLite/rqlite/Turso/ClickHouse provider), G=NA, E=NA, N=U, V=U, D=NA, X=C(generic SQL only), R=U |
| **SQL Server dedicated pool**（sqlserver） | L=V, G=V但linked-server N, E=C(structured), N=C, V=U, D=C, X=C, R=C(Schema Diff only) | L=C, G=V, E=C, N=V(ALTER VIEW builder), V=U, D=C, X=C, R=C(Schema Diff only) | L=V, G=V, E=C(改写ALTER；rename N), N=V, V=U, D=U, X=C, R=U | L=U, G=U, E=U, N=U, V=U, D=U, X=C(generic SQL only), R=U | L=U, G=NA, E=NA, N=U, V=U, D=NA, X=C(generic SQL only), R=U |
| **Agent Driver**（oracle、kingbase、vastbase、xugu及配置为Agent的其他类型） | L=V(Agent RPC), G=C, E=C(structured), N=C, V=U, D=C, X=C, R=U | L=C, G=C(Agent对象实现), E=C, N=C, V=U, D=C, X=C, R=U | L=C, G=C(Agent对象实现), E=C, N=C, V=U, D=U, X=C, R=U | L=C(Agent/table-scoped), G=C, E=U, N=U, V=U, D=C, X=C, R=U | L=U(per Agent), G=NA, E=NA, N=U, V=U, D=NA, X=C, R=U |
| **ExternalDriver / JDBC plugin**（JDBC插件数据库类型；Presto-like list特殊处理） | L=V(plugin RPC), G=C(plugin DDL), E=C(structured), N=C, V=U, D=C, X=C, R=U | L=C(plugin metadata), G=C(plugin RPC), E=C, N=C, V=U, D=C, X=C, R=U | L=C(JDBC metadata), G=C(plugin RPC), E=C, N=C, V=U, D=U, X=C, R=U | L=C(per plugin), G=C(per plugin), E=U, N=U, V=U, D=C, X=C, R=U | L=U(per plugin), G=NA, E=NA, N=U, V=U, D=NA, X=C, R=U |

证据解释：Native provider和core按 PoolKind/config显式dispatch list/source/DDL/index路径；Agent与ExternalDriver通用RPC只验证“请求可路由”，不能把对象粒度能力提升为 Verified。表格中的 U 是代码检查未能证明；N只用于显式只读或拒绝，如PG-family trigger的 editable=false、linked-server DDL unsupported。索引的G/E/D=NA是因为INDEX不属于ObjectSourceKind、而是table-scoped元数据，不表示DBMS不支持索引。执行与回滚共性：statement可生成不代表能执行；source save默认逐句提交，仅Informix有多语句事务特例；Schema Diff rollback不属于source editor per-driver能力。分页与空结果边界见后节。

## 对象 × 操作矩阵

“有路径”表示找到直接实现；“条件”表示受 database type、服务端元数据或权限约束；“未发现”只针对所查路径。

| 对象类型 | list | get-definition | edit | generate | validate | dependency | execute | rollback |
|---|---|---|---|---|---|---|---|---|
| **table** | 有路由：Native/Agent/ExternalDriver；未实现对象列表的 PoolKind 回落 table metadata | 条件：独立 get_table_ddl，按 provider 支持，不支持时报错 | 结构化 table editor 是另一流程；source edit N/A（TABLE 不在 ObjectSourceKind，sourceReadable排除TABLE） | 有条件：get_table_ddl/export DDL | 未发现独立 validate-only | 有限：Schema Diff FK图；也可被view/trigger引用 | 通用 SQL execute，受数据库权限/方言影响 | Schema Diff可生成反向DDL；source edit无自动补偿 |
| **view** | 条件：驱动列表表/view或对象目录，侧栏清单列出部分 | 条件：ObjectSource getter；Native多种、Agent、JDBC RPC | 有条件：编辑器读取 editable，false为只读 | 有路径：build_view_ddl_sql方言生成 | 未发现独立 dry-run；保存执行时由DB解析 | 有限：扫描view DDL引用表 | 保存路径执行生成SQL，可能写库 | 仅Schema Diff反向DDL；普通保存无通用rollback |
| **procedure** | 条件：PG/MySQL/Agent/JDBC metadata分支，driver-specific | 条件：source getter；重载依赖signature | 有条件：source改写后执行；无跨库语法保证 | 有条件：MySQL/PG/Oracle/SQL Server存在转换分支 | 未发现独立dry-run | 未发现通用procedure节点依赖图 | source DDL保存可执行；UI executable标志仅PROCEDURE，不能推导调用过程能力 | 未发现source save回滚 |
| **function** | 条件：同procedure | 条件：source getter/signature | 有条件：source edit并执行 | 有条件：按方言生成或原文执行 | 未发现独立dry-run | 部分：FunctionInfo文本可加入表依赖边，不是完整对象图 | 保存DDL可提交；UI executable标志不含FUNCTION，不代表函数调用功能 | 未发现source save回滚 |
| **trigger** | 条件：table-scoped list_triggers；侧栏只声明少数driver | 条件：对象源RPC/native getter；须逐driver验证 | 部分：PG家族source返回editable=false；不能外推其他驱动 | 未发现通用trigger DDL builder | 未发现独立dry-run | 有限：扫描table detail的trigger.statement引用表 | 通用SQL可提交DDL，但不等于编辑器为所有driver启用trigger编辑 | 未发现source save回滚 |
| **index** | 有条件：独立table-scoped list_indexes；Native覆盖MySQL/OceanBase、StarRocks、Doris、Manticore fallback、PG/QuestDB、SQLite/rqlite/Turso、MongoDB、ClickHouse | 按对象定义 N/A：index不属于ObjectSourceKind；可从table DDL/diff侧面获取 | source edit N/A；结构化表操作是另一契约 | standalone generator未发现；Schema Diff生成index变更DDL | 未发现独立校验 | 不作为DependencyGraph节点；是table结构 | 无index-object execute API；可执行生成SQL | Schema Diff可生成反向DDL；无source editor rollback |

### 关键实现细节

- `ObjectSourceKind` 有 VIEW/MATERIALIZED_VIEW/PROCEDURE/FUNCTION/TRIGGER/EVENT/SEQUENCE/SYNONYM/JOB/PACKAGE/PACKAGE_BODY/TYPE/TYPE_BODY，不含 TABLE、INDEX；`ObjectSource` 有 editable 字段。[types.rs:207-233](D:/dbx-main/crates/dbx-types/src/types.rs)
- Index 是独立 table-scoped 命令，不是对象定义接口；provider 映射见 [native.rs:172-205](D:/dbx-main/crates/dbx-core/src/schema/providers/native.rs)。未匹配类型返回空 vector，无法从静态代码区分“不支持”和“无索引”。Trigger 同样按表取：[commands.rs:422-435,497-509](D:/dbx-main/crates/dbx-tauri-schema/src/commands.rs)。
- Table DDL 与 VIEW source 分流；SQL Server linked-server table DDL 明确不支持。[schema/mod.rs:9130-9149,9215-9264](D:/dbx-main/crates/dbx-core/src/schema/mod.rs)
- Source Editor 读取 `editable=false` 后只读；保存时先构造语句、经 production SQL guard 后执行并刷新。[ObjectSourceDialog.vue:102-125,165-215](D:/dbx-main/apps/desktop/src/components/objects/ObjectSourceDialog.vue)
- Builder 有 SQL Server ALTER、DuckDB VIEW、PG 类 VIEW、Oracle 类 VIEW/routine、Informix VIEW、MySQL routine 特殊转换；View generator按数据库类型选择 CREATE/OR REPLACE。[object_source_sql.rs:129-190,233-273](D:/dbx-main/crates/dbx-sql-core/src/object_source_sql.rs)
- Source-save 默认逐条 `executeQuery`；仅 Informix 多语句 view replacement 用 `executeInTransaction`，多语句默认非原子。[objectSourceEditor.ts:72-93](D:/dbx-main/apps/desktop/src/lib/table/objectSourceEditor.ts)
- 未找到所有 driver 通用 validate-only/compile-only 端点。builder成功只表示生成文本，服务端验证发生在执行阶段。
- `DependencyGraph` 以 table 集合为节点：FK、View DDL、Trigger statement、Function definition扫描依赖；无 procedure 节点，Sequence参数未用于构图。[schema_diff.rs:601-663,664-771](D:/dbx-main/crates/dbx-sql-schema/src/schema_diff.rs) 这不是完整数据库依赖目录，也不是保存前验证。
- Source editor没有对象历史/通用自动rollback API。Schema Diff反向DDL不构成source save自动补偿；Informix事务是本source-save路径明确发现的多语句原子性特例。

## 分页、权限、错误及副作用

**分页。** Tauri `list_objects` 接收 limit/offset/object_types/filter：[commands.rs:232-289](D:/dbx-main/crates/dbx-tauri-schema/src/commands.rs)；Web route转交core：[routes/schema.rs:256-317](D:/dbx-main/crates/dbx-web/src/routes/schema.rs)。Core按 `ObjectListOutcome.paging_applied` 决定offset并过滤/分页；Oracle Agent可分页；其他Agent/ExternalDriver包装为unpaged outcome：[schema/mod.rs:6433-6483,7067-7099,7105-7153](D:/dbx-main/crates/dbx-core/src/schema/mod.rs)。接口接收limit/offset不代表每个driver服务端分页；未发现统一总数/页码协议。

**权限及错误。** Web/Tauri handler转交core并传播Result错误；handler内未见逐对象SQL权限ACL：[routes/schema.rs:303-317,353-373](D:/dbx-main/crates/dbx-web/src/routes/schema.rs) [commands.rs:278-290,321-342](D:/dbx-main/crates/dbx-tauri-schema/src/commands.rs)。目录可见性、定义读取及DDL写权限受连接账号/driver/DB影响。本次未用实例验证，不能保证统一错误表现。Unsupported object source 和 SQL Server linked-server table DDL有显式错误：[schema/mod.rs:10893-10905,9225-9227](D:/dbx-main/crates/dbx-core/src/schema/mod.rs)。

**副作用。** list/get/DDL读取走metadata/query；source save最终执行DDL，可能修改数据库对象。production guard不是事务。除Informix特例外，多条语句按序执行，前条成功后续失败可能部分提交。Schema Diff反向DDL需独立执行，不自动补偿source editor。

## 静态源码无法证明

1. 各driver/JDBC/数据库版本的真实兼容性和目标环境权限；没有运行实例验证。
2. 每种database type对procedure/function/trigger/index source的服务端成功率。
3. 统一grant、错误码、空结果语义。
4. Schema Diff之外其他部署流程的rollback不属于source editor rollback证据。
5. Sidebar对象清单不能直接当作后端所有操作能力矩阵。

R5-A契约建议按 `databaseType × objectType × operation` 分开声明 list、get-definition、edit、generate、validate、dependency、execute、rollback；分页标出服务端/客户端/未支持，权限错误与空目录区分，源编辑与结构化编辑分开，多语句原子性逐驱动写明。
