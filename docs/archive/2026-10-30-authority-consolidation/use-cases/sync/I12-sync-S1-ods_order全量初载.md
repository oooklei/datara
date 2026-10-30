# S1 · ods_order 全量初载（库→库）

## 1. 意图
验证 C17 数据同步组件「库→库全量同步」主链路（单 schema、truncate 幂等重载）与 C25 对账校验行数闸门；覆盖 开始→同步→校验→结束 基础 DAG（C1/C2/C17/C25）。

## 2. 业务意义与作用
数仓初始化或重建分层时，把业务库整表搬运到数仓是最基础的同步场景。全量重载要求：可反复执行（幂等）、行数与源一致、坏行零容忍。本用例即该场景的最小闭环。

## 3. 业务逻辑（DAG）

```
(开始) ──> [C17 数据同步 ods_order] ──> [C25 对账校验] ──> (结束)
```

## 4. 操作步骤
1. 前置：确认数仓侧已按源表结构预建 `datara_dw.ods_order`（prep 脚本 `SHOW CREATE TABLE ec_retail.ods_order` 克隆；已存在则跳过）。
2. 页面 http://192.168.1.9:8090 → 任务中心 → 新建工作流，命名 `i12_S1_ods_order_load`。
3. 画布拖入：开始(C1) → 数据同步(C17) → 数据校验(C25) → 结束(C2)，顺序连线（对账节点亦可由 C23「同步编排」模板物化后把 SQL 对账替换为 C25）。
4. 按 §5 配置节点参数。
5. 保存 → 运行。

## 5. 逐节点配置参数与脚本

### C17 数据同步
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 读端类型 readerType | mysql | |
| 读端数据源 readerDs | 内置源库-ec_retail（id=9） | 默认库 ec_retail |
| 读端表名 readerTable | ods_order | table-picker 级联选择 |
| 参与 schema readerSchemasText | ec_retail | 留空亦取默认库，显式写出更稳 |
| 新增 schema 自动纳入 autoSchema | 关 | 全量单表场景无需运行时探测 |
| 合并策略 strategy | union | 单 schema 无合并差异 |
| 写端类型 writerType | mysql | |
| 写端数据源 writerDs | 内置数仓-datara_dw（id=4） | |
| 目标表名 writerTable | ods_order | 沿用源表名（prep 预建） |
| 自动建表 autoCreate | 关 | 目标表已按源结构预建 |
| 写入前清空 truncate | 开 | 幂等重载的关键 |
| 标识列名 flagColumn | src_schema | 策略为 union 时不生效，保持默认 |
| 字段映射 fieldMap | 空 | 同名全列 |
| 批大小 batchSize | 2000 | 25 万行批量写入 |
| 错误阈值 errorThreshold | 0 | 零坏行容忍 |

### C25 数据校验
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 校验对象 assertSrc | upstream | 自动取上游 C17 写端表 |
| 上游节点引用 assertUpstream | 空（自动解析） | 可显式选 C17 节点 |
| 规则集 rules | key=rows，value=min=250000 | 行数下限（源表 250000 行） |
| 不达标动作 onFail | fail | 断流失败 |

## 6. 注意事项
- 幂等性：truncate=开，可直接重跑，无需手工清表。
- 目标表若被外部变更结构，需先删除后由 prep 重建，否则 autoCreate=关 会报列不匹配。
- 源表 25 万行，批大小 2000，正常数十秒内完成；超时优先查源库负载。
- 源库 ec_retail 同时被其他用例使用，本用例只读源表，无写入冲突。

## 7. 验收标准
1. 行数一致：源 `ec_retail.ods_order` 行数 = 目标 `datara_dw.ods_order` 行数 = 250000。
2. 实例终态 `success`，C17 outputs：read_rows=250000、write_rows=250000、bad_rows=0；C25 节点 success。
3. 页面：实例成功，同步运行详情读写行数 250000，日志无 ERROR / 无 Traceback。

## 8. 验收方法
① 查库 SQL（源/数仓是两个 MySQL 容器，分查后比对；容器名以 1.9 `docker ps` 实测为准并在验证单留痕）：

```sql
-- 源库容器内执行
SELECT COUNT(*) FROM ec_retail.ods_order;    -- 期望 250000
-- 数仓容器内执行
SELECT COUNT(*) FROM datara_dw.ods_order;    -- 期望 250000
```

② API curl（1.9 本机执行）：

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/login -H 'Content-Type: application/json' \
  -d '{"user_name":"admin","user_pwd":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/instances/{instanceId} \
  | python3 -m json.tool
# 期望 data.status=success；taskInstances 中 sync 节点 outputs.write_rows=250000、assert 节点 status=success
```

③ 页面：任务中心 → 运行 → 实例「成功」截图；点开 C17 节点「同步运行详情」读写行数截图；日志页确认无 ERROR。

## 9. 运行要求
- 数据源：id=9 内置源库-ec_retail（读）、id=4 内置数仓-datara_dw（写）。
- 运行节点：id=2「1.9宿主机」（online）。
- 无外部服务依赖。

## 10. 日志查看
页面「任务中心 → 运行 → 日志」在线查看；容器内路径 `/datara/logs/{instance_id}/{task_id}.log`，关注 `[sync]` 前缀行（参与 schema、批次写入速率）与校验结论行。

## 11. 日志存放位置
宿主机归档 `/mnt/lei/datara/logs/{instance_id}/{task_id}.log`；失败排查顺序：先按 instance_id 找到失败 task_id → 看日志尾部 ERROR/Traceback → 结合 C17 outputs（read_rows/write_rows/bad_rows）定位读端或写端。
