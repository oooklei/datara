# S3 · 目标表反推多 schema 源（反向同步 union+溯源）

## 1. 意图
验证 C17「以既有目标表为基准、反向反推多 schema 同名源表」固定操作流（严格遵设计文档 §7.2.1 五步流，不新造机制）：目标级联选表 → 源实例探测 → src_flag 溯源合并 → autoSchema 运行时纳入 → autoCreate 建表口径（C1/C2/C17/C25）。

## 2. 业务意义与作用
分库分表/多区域库（如 east/south/north 各一套同名表）需要归集到数仓一张宽表，且要求每行可溯源（知道来自哪个库）。反向以目标表为基准反推源，是数仓归集回源核对、源端扩容（新区域库上线）时的典型操作。

## 3. 业务逻辑（DAG）

```
(开始) ──> [C17 数据同步 ods_order_rev（src_flag 溯源）] ──> [C25 对账校验] ──> (结束)
```

run1：east(100 行) + south(80 行) → 目标 180 行；
run2 前 prep 新建 north(60 行) 同名表 → autoSchema 自动纳入 → 240 行。

## 4. 操作步骤（§7.2.1 五步固定流，顺序不得颠倒）
1. **选目标表（前置依赖先行）**：写端数据源选 `内置数仓-datara_dw` → 目标库 `datara_dw` → 目标表 `ods_order_rev`（table-picker 级联；表尚未建，直接输入表名）。
2. **选源实例后探测**：读端数据源选 `内置源库-ec_retail` 后，用「反选探测」控件按目标表名 `ods_order_rev` 在源实例全部 schema 中探测同名表，前端列出「schema × 同名表」清单，勾选 `ec_retail_east`、`ec_retail_south` 参与本次同步（探测回填读端表名与参与 schema）。
3. **union 或其他方案（新增溯源字段）**：合并策略选「标识列」，标识列名 `src_schema`——每个参与分支追加常量列 `'<schema>' AS src_schema`，逐行可 `WHERE src_schema='…'` 追溯来源。
4. **运行时探测**：勾选 `autoSchema`（新增 schema 自动纳入）——执行时 `SHOW DATABASES` 对比已选集，发现新增 schema 同名表自动纳入分支并打日志、outputs.schemas_included 全量回显。
5. **建表口径**：`autoCreate=开`，按首个参与 schema（east）的表结构建目标表；src_flag 策略自动追加 `src_schema VARCHAR(64)` 列。

保存后 run1 验证 180 行；随后 prep 新建 north 同名表 60 行，再 run2 验证自动纳入到 240 行。

## 5. 逐节点配置参数与脚本

### C17 数据同步
| 字段（表单键） | 值 | 说明（对应五步流） |
|---|---|---|
| 写端类型 writerType | mysql | 步骤1 |
| 写端数据源 writerDs | 内置数仓-datara_dw（id=4） | 步骤1 目标实例 |
| 目标表名 writerTable | ods_order_rev | 步骤1 目标表（专属名，主库无同名表避免被卷入） |
| 自动建表 autoCreate | 开 | 步骤5 建表口径（首 schema 结构 + src_schema 列） |
| 读端类型 readerType | mysql | 步骤2 |
| 读端数据源 readerDs | 内置源库-ec_retail（id=9） | 步骤2 选定后触发探测 |
| 反选探测 probe | 勾选 ec_retail_east、ec_retail_south | 步骤2 探测清单回填 |
| 读端表名 readerTable | ods_order_rev | 步骤2 由探测按目标表名带出 |
| 参与 schema readerSchemasText | `ec_retail_east,ec_retail_south` | 步骤2 勾选结果（部分勾选会自动置 autoSchema=关，需手动再勾开，见注意事项） |
| 新增 schema 自动纳入 autoSchema | 开 | 步骤4 运行时探测 |
| 合并策略 strategy | src_flag | 步骤3 |
| 标识列名 flagColumn | src_schema | 步骤3 溯源字段 |
| 写入前清空 truncate | 开 | 重跑幂等 |
| 批大小 batchSize | 1000 | |
| 错误阈值 errorThreshold | 0 | |

### C25 数据校验
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 校验对象 assertSrc | upstream | 自动取 C17 写端表 |
| 规则集 rules | key=rows，value=min=180 | run1 精确值；run2=240 亦通过（下限口径） |
| 不达标动作 onFail | fail | |

## 6. 注意事项
- **探测勾选与 autoSchema 联动**：探测清单部分勾选时表单会自动置 `autoSchema=关`（避免半选状态误纳入），本用例需手动把 autoSchema 再勾开——这是五步流第 4 步的关键动作，漏勾则 run2 的 north 不会被自动纳入。
- **目标表用专属名 `ods_order_rev`**：源实例主库 ec_retail 无同名表，autoSchema 差集探测不会误收主库；prep 已校验 `ec_retail`/`ec_retail_bad` 无该同名表。
- run2 前只新增 north 库表，不改 east/south 数据，240 = 100+80+60 可精确对账。
- 幂等性：truncate=开，重跑前无需清表；若删除重建目标表，src_schema 列由 autoCreate 自动带上。

## 7. 验收标准
1. run1：目标 180 行 = east 100 + south 80；溯源断言 `src_schema='ec_retail_east'` 命中 100 行、`ec_retail_south` 命中 80 行。
2. run2：autoSchema 自动纳入 north，目标 240 行；日志出现「探测到新增 schema: ec_retail_north」，outputs.schemas_included 含三个 schema。
3. 目标表结构含 `src_schema VARCHAR(64)` 列；C25 校验通过；两次实例均 success、无 ERROR / Traceback。

## 8. 验收方法
① 查库 SQL（数仓容器；源侧各 schema 行数在源库容器分查）：

```sql
-- 源库容器：各参与 schema 行数
SELECT COUNT(*) FROM ec_retail_east.ods_order_rev;   -- 期望 100
SELECT COUNT(*) FROM ec_retail_south.ods_order_rev;  -- 期望 80
SELECT COUNT(*) FROM ec_retail_north.ods_order_rev;  -- run2 前预建，期望 60
-- 数仓容器：总量与溯源断言
SELECT COUNT(*) FROM datara_dw.ods_order_rev;                        -- run1 期望 180，run2 期望 240
SELECT src_schema, COUNT(*) FROM datara_dw.ods_order_rev GROUP BY src_schema;
-- 期望 run2 后：ec_retail_east=100, ec_retail_south=80, ec_retail_north=60
```

② API curl：

```bash
# 登录取 TOKEN 同 S1
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/instances/{run2InstanceId} | python3 -m json.tool
# 期望 sync 节点 outputs.schemas_included=["ec_retail_east","ec_retail_south","ec_retail_north"]（排序以运行时为准）、write_rows=60（run2 增量写行数）
```

③ 页面：任务中心两次实例成功；run2 日志含「探测到新增 schema: ec_retail_north（同名表纳入）」关键字截图；无 ERROR。

## 9. 运行要求
- 数据源：id=9（读，需 SHOW DATABASES 权限）、id=4（写）。
- 运行节点 id=2「1.9宿主机」；prep 需在源库建 east/south/north 三库同名表并注入数据。

## 10. 日志查看
同 S1；本用例重点看两段日志：设计探测阶段的参与 schema 集合、运行时 `[sync] 探测到新增 schema: …（同名表纳入）` 行。

## 11. 日志存放位置
`/mnt/lei/datara/logs/{instance_id}/{task_id}.log`；溯源对不上时按「schemas_included → 各分支行数 → src_schema 分组」三步核对。
