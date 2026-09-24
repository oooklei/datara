# G2 · Python 文件清洗 + C22 注册预览（python→C22）

## 1. 意图
验证普通类「脚本加工 + 文件注册预览」链路：以 python 节点读 CSV → stdlib csv 清洗（去首尾空格、空行过滤、统一编码）→ 写回清洗后文件，配合 C22 文件读取节点注册预览，验证 python 执行器与文件管理共享卷协作。

## 2. 业务意义与作用
数据文件在入仓前往往需要轻量清洗：去除 BOM、统一换行、过滤空行、规整列值。python 节点用 stdlib（无需第三方依赖）完成清洗并把结果落回共享卷，C22 节点注册该文件后即可在 Inspector 预览清洗结果——是「文件级 ETL」的最小闭环。

## 3. 业务逻辑（DAG）

```
(开始) ──> [python: CSV 清洗脚本] ──> [C22 文件读取(注册预览)] ──> (结束)
```

## 4. 操作步骤
1. 前置：宿主机 `/mnt/lei/datara/i12files/raw_orders.csv` 就绪（含脏数据：首尾空格、空行、BOM）。
2. 任务中心 →「批处理」页签 → 新建工作流 `i12_G2_python_clean_file`。
3. 画布拖入：`python` → `file_read(C22)`，连线。
4. 按 §5 配置；保存 → 运行。
5. 实例成功后验证清洗后文件存在且行数正确。

## 5. 逐节点配置参数与脚本

### Python 清洗脚本（C13）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `python` | Python 执行器 |
| 脚本 script | 见下方「清洗脚本」 | python 执行，stdout 逐行实时日志 |
| 依赖清单 requirements | （空） | 仅用 stdlib，无需第三方包 |

```python
# G2 CSV 清洗脚本：去 BOM、去首尾空格、过滤空行、统一换行
import csv, os, sys

SRC = "/mnt/lei/datara/i12files/raw_orders.csv"
DST = "/mnt/lei/datara/i12files/cleaned_orders.csv"

read = 0
written = 0
skipped = 0

with open(SRC, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.reader(f)
    with open(DST, "w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        for row in reader:
            read += 1
            # 去每列首尾空格
            row = [c.strip() for c in row]
            # 过滤全空行
            if not any(row):
                skipped += 1
                continue
            writer.writerow(row)
            written += 1

print(f"[clean] 读={read} 写={written} 跳过空行={skipped}")
# 输出到 stdout 即任务日志
```

### C22 文件读取（注册预览）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `file_read` | 文件读取节点 |
| 文件路径 filePath | `/mnt/lei/datara/i12files/cleaned_orders.csv` | 清洗后文件（共享卷直读） |
| 文件格式 fileType | `csv` | |
| 分隔符 delimiter | `,` | |
| 编码 encoding | `utf-8` | |
| 表头行 headerRows | `1` | 首行为表头 |

## 6. 注意事项
- python 节点在 worker 容器内执行，脚本路径 `/mnt/lei/datara/i12files/` 是共享卷挂载（worker 与 api 同路径约定，file.py 同口径），确保 worker 可读写。
- 仅用 stdlib（csv 模块），无需第三方依赖；若误填 requirements 字段仅打印提示不安装（设计 §7.2，依赖预装归镜像层）。
- 清洗脚本 stdout（`[clean] 读=…`）写入任务日志，是验收核心证据。
- C22 节点注册文件后，Inspector 预览面板可直接查看清洗后数据行。
- 幂等：重跑前需确认 raw_orders.csv 未被改动（否则行数基准变化）；清洗输出覆盖写（overwrite），可直接重跑。

## 7. 验收标准
1. 实例终态 `success`，日志无 ERROR / Traceback。
2. 任务日志含清洗统计：`[clean] 读=N 写=M 跳过空行=K`，且 N=M+K。
3. 共享卷存在 `cleaned_orders.csv`，行数 = 源文件行数 - 空行数 - (表头?0:0)。
4. C22 预览面板可见清洗后数据（列值无首尾空格）。

## 8. 验收方法
① 查库 SQL：本用例无落库（文件级加工），不适用。文件行数核对（worker 容器内）：
```bash
# worker 容器内执行
docker exec datara-worker bash -c 'wc -l < /mnt/lei/datara/i12files/cleaned_orders.csv'
# 期望：= 源数据行数 - 空行数（表头行保留）
```

② API curl：
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/instances?wf_name=i12_G2_python_clean_file&page_no=1&page_size=1" | python3 -c '
import sys,json; rows=json.load(sys.stdin).get("list") or []
inst=rows[0]; print("status:", inst.get("status"), "id:", inst.get("id"))'
# 期望：status=success
INSTANCE_ID=<实例id>
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/instances/$INSTANCE_ID/logs?tail=30"
# 期望：含 "[clean] 读=" 关键字
```

③ 页面：任务中心 → 批处理 → 实例「成功」；日志含清洗统计；C22 节点 Inspector 预览面板可见清洗后数据；截图 `shots/G2-python文件清洗.png` 留档。

## 9. 运行要求
- 数据源：文件源（共享卷 `/mnt/lei/datara/i12files/`）。
- 外部服务：无。
- 前置文件：宿主机 `/mnt/lei/datara/i12files/raw_orders.csv`（含脏数据）。

## 10. 日志查看
页面「任务中心 → 运行 → 日志」在线查看；容器内 `/datara/logs/{instance_id}/{task_id}.log`。关键字：`[python]` 脚本执行、`[clean]` 清洗统计、`Traceback`。

## 11. 日志存放位置
宿主机 `/mnt/lei/datara/logs/{instance_id}/{task_id}.log`。排查顺序：实例终态 → 日志尾 30 行（含清洗统计）→ 共享卷确认 cleaned_orders.csv 存在 → worker 容器 `docker logs datara-worker --tail 200`。
