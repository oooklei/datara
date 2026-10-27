# COMP-E2E-03 摘要
1. 入口：正式 `http://192.168.1.9:18091/`，结果 PASS。
2. 认证：validation-token API 签发 900 秒 token；未写 URL/静态产物/持久存储。
3. 复用 project 26 / workflow 25 的 SQL、Python、Shell version 1 资源。
4. 新建隔离 workflow 33；未改 workflow 25，未改产品代码。
5. 变量优先级实测：task(node) > workflow > env-group(303) > global。
6. 运行输出同时打印 NODE/WORKFLOW/ENV/GLOBAL 四层解析值，均正确。
7. snapshot 13：5 节点，三项 resourceRef 均固定 version 1，digest 已记录。
8. 成功实例 11：SUCCEEDED；任务 5/5 成功；统计 success=5/failure=0/skipped=0。
9. SQL 输出 row_count=1；Python=`resource-python-e2e`；Shell=`resource-shell-e2e`。
10. dependency mock=SUCCEEDED 日志已核验。
11. 失败实例 12：FAILED；资源与变量节点 4 成功，dependency 1 失败。
12. 失败统计 success=4/failure=1/skipped=0；mock=FAILED 日志已核验。
13. 两次运行均绑定 snapshot 13，运行变量快照命中 task/node-value。
14. 四层测试变量均已删除；logout 成功；注销 token 再访问返回 401。
15. 观察项：长变量名可保存，但运行快照 source 超列宽导致 HTTP 500；短标识主链不受影响。
16. 详细证据：`run-report.json`；环境探测：`probe-existing.json`；异常：`long-name-observation.txt`。
