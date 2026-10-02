# I11 工作流同步任务——终审取证记录（本会话内证词，跨会话可接管）

> 生成：2026-09-22 · 会话 Sisyphus · 项目 `D:\需求\数据治理工具\Datara\datara-backend`
> 性质：**机械取证报告**（grep / git log / ORM 反查 / docker 探活），非记忆。所有「缺失」均有代码层铁证，可复核。

---

## 1. 头号问题：你把「同步任务」做完了吗？——分两层回答

**结论：只做完一层（流数据同步），测试工作流用例（同步任务在画布/部署侧的交付物）从未做。**

| 层 | 交付物 | 状态 | 机械证据 |
|---|---|---|---|
| 流数据同步 | `tools\seed_stream.py`（kafka/mqtt/redis 三通道种子）+ `tools\smoke_stream_i11.py` + `worker\stream\` 消费端 | ✅ 完成 | 全文件存在 |
| 测试工作流用例 | **向 `t_wf_definition` 表插入 3 条工作流定义（喂画布/画布工作流），对齐 seed_stream 风格** | ❌ **从未完成** | 全仓库 `WfDefinition(` 实例化点仅 2 处：ORM 类定义 + POST 创建端点**内部**。**没有任何 seed 脚本向该表插过一行** → 表必空 → `GET /workflow-definitions` 返回 `{list:[]}` |

**为什么漏（诚实归因）**：把「同步」误理解为**数据流同步**（Kafka/MQTT/Redis 喂流），而你要的「测试工作流用例」是**喂定义表 `t_wf_definition`（画布侧）**。两个「同步」是两件事，我只交付了前者；大量篇幅耗在 CJK 路径取证，迟迟没对「定义表有没有货」下决定性结论——而这个结论**在代码层早已可判**。

## 2. 为什么我（宿主）连不上库查 COUNT？

```
OperationalError: (pymysql) Can't connect to MySQL server on 'mysql-meta' (getaddrinfo failed)
```
- `mysql-meta` 是 **docker compose 内网主机名**，宿主 Windows DNS 解析不了；
- 当前无跑着的 datara 容器 → 本环境无法直连 MySQL。
- **因此「COUNT t_wf_definition = 0」这行数字在本会话无法真连实锤**；但代码层铁证与之等价：无 seed ⇒ 空。

## 3. 已写盘、待执行的交付物（B 方案）

`D:\需求\数据治理工具\Datara\datara-backend\tools\seed_wf_definition.py`
- 对齐 `seed_stream.py` 的 argparse + seed_* 风格，幂等（code 已存在跳过）
- 插 3 条测试工作流定义：`wf_month_sync`(月度数据同步,同步) / `wf_etl_incr`(增量ETL同步,ETL) / `wf_stream_mon`(实时流监控,流) —— tags 对齐画布调色板分组
- 运行：`python tools\seed_wf_definition.py`（**须在 DB 可达环境**：docker 栈内或把 `mysql-meta` 映射为宿主可达地址）

## 4. 留给后续会话的机械检查清单（避免重演空转）

1. **先 grep 定存在性**（`Select-String 'WfDefinition\(' ... `），比猜快、比记忆可信；
2. 别把「数据流同步」和「测试工作流用例」两个「同步」混为一件；
3. DB 是否可达：`docker ps` 看容器 → 不可达就**明说**，不要假装 COUNT；
4. CJK 路径取证到此为止——本仓库根是 `D:\需求\数据治理工具\Datara\datara-backend`，**无嵌套双份**（已 Test-Path 证实）。

---

### 剩余待办（依赖 DB 可达，非本环境可完成）
- [ ] 起 docker 栈后执行 `seed_wf_definition.py` 落库
- [ ] `SELECT COUNT(*) FROM t_wf_definition` 实锤非 0
- [ ] 验证 `GET /workflow-definitions` 返回非空、画布刷新有货
