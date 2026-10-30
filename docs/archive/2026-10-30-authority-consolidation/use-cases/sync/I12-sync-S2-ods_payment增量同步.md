# S2 · ods_payment 增量同步（定时定差值法）

## 1. 意图
验证 C17「库→库增量同步」：增量列 + 增量条件表达式 + 工作流变量渲染，用定差值法（两次运行写行数之差 = 两次边界间新插入行数）证明增量边界正确（C1/C2/C17 + 工作流变量）。

## 2. 业务意义与作用
周期性把业务库新增/变更行搬运到数仓是数仓最日常的链路。核心风险是增量边界（重复拉取或漏拉），本用例用可控注入的 50 行新数据验证：上一次运行完成时刻为界，下一次只搬运其后的行。

## 3. 业务逻辑（DAG）

```
(开始) ──> [C17 数据同步 ods_payment（增量 pay_time >= ${last_sync_time}）] ──> (结束)
```

工作流变量 `last_sync_time`：初值 `$[yyyy-MM-dd 000000]`（渲染为当日零点），run1 结束后由脚本更新为 run1 完成时刻。

## 4. 操作步骤
1. 页面新建工作流 `i12_S2_ods_payment_incr`。
2. 变量面板新增变量：名称 `last_sync_time`、类型「文本」、值 `$[yyyy-MM-dd 000000]`、描述「增量边界：上次同步完成时刻」。
3. 画布拖入：开始(C1) → 数据同步(C17) → 结束(C2)，连线。
4. 按 §5 配置 C17 参数。
5. 保存 → run1 运行（建目标表 + 拉当日基线）；完成后把变量值更新为 run1 完成时刻（页面编辑或 API PUT）；向源表注入 50 行 `pay_time=NOW()` 新单；再 run2。

## 5. 逐节点配置参数与脚本

### 工作流变量
| 名称 | 类型 | 初值 | 说明 |
|---|---|---|---|
| last_sync_time | 文本 | `$[yyyy-MM-dd 000000]` | 时间模板，运行时渲染为当日零点；run1 后改为 run1 完成时刻 |

### C17 数据同步
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 读端类型 readerType | mysql | |
| 读端数据源 readerDs | 内置源库-ec_retail（id=9） | |
| 读端表名 readerTable | ods_payment | 源表 20 万行 |
| 参与 schema readerSchemasText | ec_retail | |
| 新增 schema 自动纳入 autoSchema | 关 | |
| 增量列 incrementalColumn | pay_time | 源表支付时间列 |
| 增量条件表达式 incrementalExpr | `${last_sync_time}` | 渲染后 `WHERE pay_time >= '边界'`（注意是 >= 语义） |
| 合并策略 strategy | union | |
| 写端数据源 writerDs | 内置数仓-datara_dw（id=4） | |
| 目标表名 writerTable | ods_payment | |
| 自动建表 autoCreate | 开 | 首跑建表，结构按源 |
| 写入前清空 truncate | 关 | 增量追加，绝不能清表 |
| 批大小 batchSize | 2000 | |

### 注入新单（run2 前，prep/脚本执行）
```sql
-- 源库容器内执行：注入 50 行 pay_time=NOW() 的订单（order_id 取源表未占用区间）
INSERT INTO ec_retail.ods_payment (order_id, pay_time, ...)
SELECT ... , NOW() FROM ... LIMIT 50;   -- 以实际表结构补全列，脚本已内置
```

## 6. 注意事项
- 增量条件是 `>=` 语义：边界行会重复拉取一次，下游按主键幂等消费；本用例 50 行注入时刻晚于边界，不受影响。
- run1 基线：prep 注入 100 行 `pay_time=当日`，故 run1 期望 write_rows=当日行数（含基线 100）；若源表历史数据含当日行，以 SQL 实测口径为准。
- run2 前必须先更新变量，再注入 50 行、再触发 run2，顺序不能颠倒。
- 幂等性：truncate=关，整链依赖变量边界推进；若要全量重演，需 TRUNCATE 目标表并把变量改回 `$[yyyy-MM-dd 000000]`。

## 7. 验收标准
1. run1 终态 success，write_rows = run1 时源表 `pay_time >= 当日零点` 行数（含 prep 基线 100 行）。
2. run2 终态 success，write_rows = 增量窗口行数（源表 `pay_time >= 边界` 实测值），与数仓侧行数增量、源侧窗口计数三者一致。
3. 我方注入精确 50 行落库：窗口内非哨兵行（`pay_time < '2038-01-01'`）恰为 50。

> 哨兵行口径：源表 ods_payment 存量含 200 行 `pay_time = 2099-12-31`（他人测试 fixture，本用例不修改源数据）。该 200 行满足任何 `>= 边界` 条件，会被每个增量窗口重复扫入，故 run2 写行数 = 哨兵 200 + 新注入 50 = 250 属预期；断言按「窗口总数 = 哨兵 + 新注入」动态三分一致判定，不写死 50。

## 8. 验收方法
① 查库 SQL（双容器分查）：

```sql
-- 源库容器：run2 后增量窗口三分解
SELECT COUNT(*) FROM ec_retail.ods_payment WHERE pay_time >= '<run1完成时刻>';                          -- 窗口总数（哨兵+新注入）
SELECT COUNT(*) FROM ec_retail.ods_payment WHERE pay_time >= '<run1完成时刻>' AND pay_time >= '2038-01-01';  -- 哨兵行（预期 200）
SELECT COUNT(*) FROM ec_retail.ods_payment WHERE pay_time >= '<run1完成时刻>' AND pay_time < '2038-01-01';   -- 新注入（预期 50）
-- 数仓容器：两次运行后的总行数差 = 窗口总数
SELECT COUNT(*) FROM datara_dw.ods_payment;  -- run1 后记 N1，run2 后记 N2，期望 N2-N1 = 窗口总数
```

② API curl：

```bash
# 登录取 TOKEN 同 S1；查两次实例
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/instances/{run1InstanceId} | python3 -m json.tool
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/instances/{run2InstanceId} | python3 -m json.tool
# 期望 run2 实例 sync 节点 outputs.write_rows=窗口总数（哨兵 200 + 新注入 50 = 250）；变量更新：
curl -s -X PUT localhost:8000/api/v1/workflow-variables/{varId} -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"wf":"{wfId}","name":"last_sync_time","value":"<run1完成时刻>","type":"文本","encrypted":false,"options":[],"desc":"增量边界"}'
```

③ 页面：任务中心两次实例均成功；run2 实例 C17「同步运行详情」写行数=50 截图；日志含边界渲染后的 WHERE 条件、无 ERROR。

## 9. 运行要求
- 数据源：id=9（读）、id=4（写）；运行节点 id=2「1.9宿主机」。
- 需对源库具备 INSERT 权限（注入新单）；脚本账号 admin。

## 10. 日志查看
同 S1；关注 `[sync]` 行中增量条件渲染结果（`pay_time >= '…'`）与两次运行的参与 schema、写行数，对照变量值。

## 11. 日志存放位置
`/mnt/lei/datara/logs/{instance_id}/{task_id}.log`；定差不符时按「run1 边界值 → 注入时刻 → run2 边界值」顺序核对三处时间戳。
