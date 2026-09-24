# S5 · 多表并行同步（fork/join 三路）

## 1. 意图
验证 C5 并行分叉 / C6 汇合下的多表并行同步：3 路 C17 同时搬运三张业务表（行数量级不同），各路 C25 独立闸门，日志时间戳重叠证明真并行（C1/C2/C5/C6/C17/C25）。

## 2. 业务意义与作用
数仓每日常规批量搬运往往涉及多张表，串行耗时难以接受；并行分叉 + 各表独立行数闸门是「一张表失败不拖垮其他表、总时长=最慢表」的标准做法。

## 3. 业务逻辑（DAG）

```
              ┌──> [C17 ods_cart]   ──> [C25 rows>=9872]  ──┐
(开始) ── [C5 fork] ──> [C17 ods_coupon] ──> [C25 rows>=5000]  ──┼── [C6 join] ──> (结束)
              └──> [C17 ods_refund]  ──> [C25 rows>=14750] ──┘
```

三源表行数：ods_cart=9872、ods_coupon=5000、ods_refund=14750。

## 4. 操作步骤
1. 页面新建工作流 `i12_S5_multi_fork`。
2. 画布拖入：开始(C1) → 并行分叉(C5) → 三路各「数据同步(C17) + 数据校验(C25)」→ 汇合(C6) → 结束(C2)，连线。
3. C5 并行度设为 3。
4. 按 §5 配置三路 C17/C25（仅表名与行数下限不同）。
5. 保存 → 运行。

## 5. 逐节点配置参数与脚本

### C5 并行分叉
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 并行度 parallel | 3 | 三路同时下发 |

### 三路 C17（公共参数一致，仅 readerTable/writerTable 不同）
| 字段（表单键） | 路A | 路B | 路C | 说明 |
|---|---|---|---|---|
| readerDs | 内置源库-ec_retail（id=9） | 同 | 同 | |
| readerTable / writerTable | ods_cart | ods_coupon | ods_refund | 源表名沿用至目标 |
| readerSchemasText | ec_retail | 同 | 同 | |
| autoSchema | 关 | 关 | 关 | 单表场景不探测 |
| strategy | union | 同 | 同 | |
| writerDs | 内置数仓-datara_dw（id=4） | 同 | 同 | |
| autoCreate | 开 | 开 | 开 | 首跑按源结构建表 |
| truncate | 开 | 开 | 开 | 重跑幂等 |
| batchSize | 2000 | 同 | 同 | |

### 三路 C25
| 字段（表单键） | 路A | 路B | 路C |
|---|---|---|---|
| assertSrc | upstream | upstream | upstream |
| rules | rows：`min=9872` | rows：`min=5000` | rows：`min=14750` |
| onFail | fail | fail | fail |

## 6. 注意事项
- 三路写端为同库不同表，autoCreate=开 首跑建表；truncate=开 保证可重跑。
- join 为 AND 语义：任一路失败整体仍等全部路结束后实例失败，便于一次看全三路证据。
- 并行证据：三路 C17 日志的起止时间戳应重叠（若串行则依次相接）；worker 并发数不足时可能退化为排队，需核对日志判定。
- 源表行数为创作时快照，若源数据被其他用例追加，以验收时 SQL 实测为准（C25 用下限口径即为此留余量）。

## 7. 验收标准
1. 实例终态 success；三路 C17 outputs.write_rows 分别 ≥ 9872 / 5000 / 14750 且与各自源表 COUNT 一致。
2. 三路 C25 全部 success；join 后 end 正常到达。
3. 日志三路 C17 起止时间戳存在重叠区间（并行证据）；无 ERROR / Traceback。

## 8. 验收方法
① 查库 SQL（双容器分查）：

```sql
-- 源库容器
SELECT 'ods_cart' t, COUNT(*) c FROM ec_retail.ods_cart
UNION ALL SELECT 'ods_coupon', COUNT(*) FROM ec_retail.ods_coupon
UNION ALL SELECT 'ods_refund', COUNT(*) FROM ec_retail.ods_refund;
-- 期望 9872 / 5000 / 14750
-- 数仓容器（同名对账）
SELECT 'ods_cart' t, COUNT(*) c FROM datara_dw.ods_cart
UNION ALL SELECT 'ods_coupon', COUNT(*) FROM datara_dw.ods_coupon
UNION ALL SELECT 'ods_refund', COUNT(*) FROM datara_dw.ods_refund;
```

② API curl：

```bash
# 登录取 TOKEN 同 S1
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/instances/{instanceId} | python3 -m json.tool
# 期望 3 个 sync 节点 outputs.write_rows 分别命中；3 个 assert 节点均 success；end 节点 success
```

③ 页面：任务中心实例成功、DAG 视图三路并行着色截图；三个 sync 任务日志的起止时间戳截图；无 ERROR。

## 9. 运行要求
- 数据源：id=9（读）、id=4（写）；运行节点 id=2「1.9宿主机」。
- worker 并发能力 ≥ 3（并行度前提）。

## 10. 日志查看
同 S1；并行验证需同时打开三个 sync 任务日志比对各自首行/末行时间戳。

## 11. 日志存放位置
`/mnt/lei/datara/logs/{instance_id}/{task_id}.log`；单路失败时先看该路 assert 结论，再看对应 sync 日志尾部。
