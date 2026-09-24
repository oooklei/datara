# S4 · CSV 文件入仓（运行时节点 SFTP 拉取）

## 1. 意图
验证 C24 文件同步组件「远端文件 → 库表入仓」全链路：运行时节点 SFTP 拉取暂存（批次号=instance_id，暂存即清）→ 表头解析 → 自定义 DDL 建表 → 覆盖写入 → 三行数输出（C1/C2/C24/C25）。

## 2. 业务意义与作用
外部合作方/上游系统常以 CSV 投递订单文件，数仓需定时把文件可靠入仓：文件不在共享卷时要经运行时节点拉取，行数要与文件数据行严格一致，且可重复执行（覆盖模式）。

## 3. 业务逻辑（DAG）

```
(开始) ──> [C24 文件同步 orders.csv] ──> [C25 对账校验] ──> (结束)
```

prep 在宿主机 `/mnt/lei/datara/i12files/orders.csv` 预置 500 数据行 + 1 表头行。

## 4. 操作步骤
1. prep：宿主机建目录 `/mnt/lei/datara/i12files/` 并生成 `orders.csv`（表头 `order_no,user_id,amount,status,create_time` + 500 数据行）。
2. 页面新建工作流 `i12_S4_file_to_db`。
3. 画布拖入：开始(C1) → 文件同步(C24) → 数据校验(C25) → 结束(C2)，连线。
4. 按 §5 配置 C24/C25。
5. 保存 → 运行。

## 5. 逐节点配置参数与脚本

### C24 文件同步
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 运行时节点 runtimeNode | 1.9宿主机 | 文件不在共享卷，经该节点 SFTP 拉取 |
| 文件来源路径 filePath | /mnt/lei/datara/i12files/orders.csv | 远端绝对路径（dir-select 经节点浏览选择） |
| 文件名 fileName | 空 | 已选到具体文件 |
| 上传暂存路径 stagedPath | 空 | 与 filePath 二选一，本例走 SFTP |
| 文件类型 fileType | csv | |
| 分隔符 delimiter | , | |
| 编码 encoding | utf-8 | |
| 表头行数 headerRows | 1 | 首行为列名 |
| 目标数据源 targetDs | 内置数仓-datara_dw（id=4） | |
| 目标 schema → 表 targetTable | `{"schema":"datara_dw","table":"i12_ods_order_file"}` | table-picker 级联（schemaTable 对象） |
| 自动建表 autoCreate | 开 | 按下方 DDL 建 |
| DDL ddl | `CREATE TABLE IF NOT EXISTS i12_ods_order_file (order_no VARCHAR(64), user_id BIGINT, amount DECIMAL(12,2), status VARCHAR(16), create_time DATETIME)` | 自定义建表口径 |
| 写入模式 writeMode | overwrite | 覆盖（先 TRUNCATE），重跑幂等 |
| 字段映射 fieldMap | 空 | 按表头同名对齐 |

### C25 数据校验
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 校验对象 assertSrc | upstream | 自动取 C24 目标表 |
| 规则集 rules | key=rows，value=`min=500,max=500`；key=unique，value=order_no | 文件数据行 500，主键唯一 |
| 不达标动作 onFail | fail | |

## 6. 注意事项
- 文件不在 `/datara/files` 共享卷时必须配运行时节点，否则报「文件不在共享卷且未配置运行时节点」。
- SFTP 拉取暂存文件名含批次号（`{instance_id}_filesync_` 前缀），入仓完成后自动清理，日志可见暂存与清理两行。
- writeMode=overwrite 保证重跑幂等；若改 append，重跑前必须 TRUNCATE 目标表。
- CSV 数值/时间列靠 DDL 显式定义类型，避免自动推断偏差。

## 7. 验收标准
1. 目标 `datara_dw.i12_ods_order_file` 行数 = 500，order_no 无重复；抽样行与文件内容一致。
2. 实例终态 success，C24 outputs：rows_read=500、rows_written=500、skipped=0；C25 通过。
3. 日志可见 SFTP 拉取、暂存（`_filesync_`）与清理痕迹；无 ERROR / Traceback。

## 8. 验收方法
① 查库 SQL（数仓容器）：

```sql
SELECT COUNT(*) FROM datara_dw.i12_ods_order_file;            -- 期望 500
SELECT COUNT(DISTINCT order_no) FROM datara_dw.i12_ods_order_file;  -- 期望 500
SELECT * FROM datara_dw.i12_ods_order_file LIMIT 3;           -- 与 orders.csv 首数据行比对
```

② API curl：

```bash
# 登录取 TOKEN 同 S1
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/instances/{instanceId} | python3 -m json.tool
# 期望 file_sync 节点 outputs.rows_read=500、rows_written=500、skipped=0、batch_id=instance_id；assert 节点 success
```

③ 页面：任务中心实例成功；C24 节点详情三行数截图；日志含「暂存/清理」与批次号关键字。

## 9. 运行要求
- 数据源：id=4（写）；运行节点 id=2「1.9宿主机」（既是运行节点又是 SFTP 文件来源节点）。
- prep 需宿主机写权限建 `/mnt/lei/datara/i12files/orders.csv`。

## 10. 日志查看
同 S1；本用例关注 `[file_sync]` 前缀行：取文件方式（SFTP/共享卷）、暂存路径、解析列数、写入模式、三行数汇总。

## 11. 日志存放位置
`/mnt/lei/datara/logs/{instance_id}/{task_id}.log`；行数不符时按「rows_read（解析）→ skipped（坏行）→ rows_written（入库）」逐段核对。
