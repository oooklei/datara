# 9-T55-fix：SKIP 扫描宽限修正

- 日期：2026-10-21 Asia/Shanghai
- 执行线：Codex
- 裁定：R-05 采用 B，`SCAN_SECONDS` 扫描宽限；R-26 单列现网修正票
- 提交：无，工作区改动，待监督线代提交

## 实现

`master/schedule.py` 新增 `_within_scan_window(planned, current)`，以 `0 <= delay < SCAN_SECONDS` 判定当前扫描轮内的准点触发。`SKIP` 从严格 `due[0] == current` 改为：在所有已到期时点中取最新一个，若它处于扫描宽限内则触发，否则跳过并推进到下一时点。

这保留了四字段现有语义：

- `misfirePolicy` 默认 `FIRE_ONCE`，`SKIP` 使用扫描宽限，`FIRE_ALL_LIMITED` 保持最多 100 次；
- `concurrencyPolicy` 的 `ALLOW/FORBID/QUEUE` 分支未改；
- `maxRunningInstances` 仍约束可用容量；
- `timezone` 仍由 `_schedule_now` 和带时区 cron 游标处理。

## 边界回归

- 5 秒扫描迟到：`SKIP` 触发最新到期点；
- 9 秒迟到：仍在 10 秒扫描宽限内，触发；
- 恰好 10 秒：不在半开区间内，跳过；
- `QUEUE + SKIP` 忙时保留，容量释放后旧时点超窗则丢弃并推进；
- `FIRE_ONCE/FIRE_ALL_LIMITED/FORBID/ALLOW/timezone/maxRunningInstances` 既有用例保持通过。

## 验证

```text
python -m pytest -q tests/test_schedule_policies.py
10 passed in 0.61s

python -m pytest -q tests/test_schedule_policies.py tests/rebuild/test_schedule_api.py
12 passed in 5.01s

python -m py_compile master/schedule.py tests/test_schedule_policies.py
exit 0
```

一次错误命令引用不存在的 `tests/test_schedule.py`，pytest 报 `file or directory not found`；随后按仓库真实测试路径改为 `tests/rebuild/test_schedule_api.py`，12 项终态全绿。该命令错误未执行测试，不是产品失败。

## SHA256

```text
62803d57defbaeee0958d3f7e2e72b7ad504e084dff1f2731dd1fa56595ee07b  datara-backend/master/schedule.py
b76d9a2f0b405fc0680ad3120028f3eed70d84c9ca15f52185c440c1c04ac72f  datara-backend/tests/test_schedule_policies.py
```

未修改 R6 冻结前端契约，未调用 AOCI，`.git` 只读，未 push。
