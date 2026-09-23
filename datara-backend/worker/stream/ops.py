"""流融合算子（I8 F39，C19 五分型，设计 §3.3）。

- 统一 Op 契约：process(row, emit)（row=内部行事件，emit 0..N 次向下游投递）；
- 表达式求值统一走 simpleeval 安全子集（与条件分支 C3 同款依赖）；
- 有态算子（join/window）带锁保护：行推进线程与窗口触发定时线程并发。
"""

import threading
import time
from typing import Callable, Optional

from simpleeval import simple_eval

from common.log import get_logger

logger = get_logger("worker.stream.ops")

AGG_FUNCS = ("sum", "count", "avg", "min", "max", "count_distinct", "rms")


class OpError(RuntimeError):
    """算子级可恢复错误（引擎按 reconnecting 处理）。"""


def build_op(fuse_type: str, params: dict) -> "OpBase":
    """分型工厂（C19 五算子）。"""
    params = params or {}
    if fuse_type == "union":
        return UnionOp(params)
    if fuse_type == "join":
        return JoinOp(params)
    if fuse_type == "window":
        return WindowAggOp(params)
    if fuse_type == "filter":
        return FilterOp(params)
    if fuse_type == "map":
        return MapOp(params)
    raise OpError(f"未知流融合分型: {fuse_type}")


def _kv_rows(p: dict, key: str) -> list:
    rows = p.get(key) or []
    return [r for r in rows if isinstance(r, dict) and str(r.get("key") or "").strip()]


class OpBase:
    """流融合算子基类。"""

    def open(self) -> None:
        pass

    def process(self, row: dict, emit: Callable[[dict], None]) -> None:  # noqa: ANN001
        raise NotImplementedError

    def close(self) -> None:
        pass

    @property
    def emits(self) -> int:
        """窗口触发计数等运维指标（无态算子恒 0，由引擎按输出条数统计）。"""
        return 0


def _safe_eval(expr: str, names: dict):
    """沙箱求值：表达式异常上抛由调用方按坏行处理（不吞错）。"""
    return simple_eval(expr, names=names)


class FilterOp(OpBase):
    """filter：条件表达式（真值行放行）。"""

    def __init__(self, params: dict):
        self.expr = str((params or {}).get("filterExpr") or "").strip()

    def process(self, row: dict, emit) -> None:  # noqa: ANN001
        if not self.expr:
            emit(row)
            return
        if _safe_eval(self.expr, dict(row["data"])):
            emit(row)


class MapOp(OpBase):
    """map：字段转换表达式表（目标字段 ← 表达式，基于行字段求值后合并）。"""

    def __init__(self, params: dict):
        self.fields = [(str(r["key"]).strip(), str(r.get("value") or "").strip())
                       for r in _kv_rows(params or {}, "fieldMap") if str(r.get("value") or "").strip()]

    def process(self, row: dict, emit) -> None:  # noqa: ANN001
        data = dict(row["data"])
        for target, expr in self.fields:
            data[target] = _safe_eval(expr, dict(row["data"]))
        emit({**row, "data": data})


class UnionOp(OpBase):
    """union：字段对齐映射（目标 ← 来源；空映射 = 同名透传），多入边由引擎合并推进。"""

    def __init__(self, params: dict):
        self.align = [(str(r["key"]).strip(), str(r.get("value") or "").strip())
                      for r in _kv_rows(params or {}, "alignMap") if str(r.get("value") or "").strip()]

    def process(self, row: dict, emit) -> None:  # noqa: ANN001
        if not self.align:
            emit(row)
            return
        data = dict(row["data"])
        for target, source in self.align:
            data[target] = row["data"].get(source)
        emit({**row, "data": data})


class JoinOp(OpBase):
    """join：两路流窗口内缓存匹配（左流推进时查右缓存，反之亦然；inner/left）。"""

    def __init__(self, params: dict):
        p = params or {}
        self.key_left = str(p.get("joinKeyLeft") or "").strip()
        self.key_right = str(p.get("joinKeyRight") or "").strip()
        self.window = max(1, int(p.get("joinWindowSec") or 60))
        self.join_type = str(p.get("joinType") or "inner")
        if not self.key_left or not self.key_right:
            raise OpError("join 须配置左右流关联键")
        self._left: list = []   # [(ts, key, data)]
        self._right: list = []

    def process(self, row: dict, emit) -> None:  # noqa: ANN001
        side = row.get("_side", "left")
        ts = row.get("ts") or time.time()
        if side == "left":
            key = row["data"].get(self.key_left)
            self._prune(ts)
            matches = [(t, k, d) for (t, k, d) in self._right if k == key]
            self._left.append((ts, key, row["data"]))
            if matches:
                emit({**row, "data": {**row["data"], **matches[-1][2]}})
            elif self.join_type == "left":
                emit(row)
        else:
            key = row["data"].get(self.key_right)
            self._prune(ts)
            matches = [(t, k, d) for (t, k, d) in self._left if k == key]
            self._right.append((ts, key, row["data"]))
            if matches:
                emit({**row, "data": {**matches[-1][2], **row["data"]}})

    def _prune(self, now: float) -> None:
        horizon = now - self.window
        self._left = [x for x in self._left if x[0] >= horizon]
        self._right = [x for x in self._right if x[0] >= horizon]


class WindowAggOp(OpBase):
    """窗口聚合：分组键 + 聚合函数表（值=函数:别名）+ 滚动/滑动窗口 + 水位线延迟。

    - 行按事件时间 ts 归窗；水位线（end+delay ≤ now）触发后由定时线程 emit；
    - 滑动窗口行可同时归属多个桶（步长 slide）；会话窗口暂不支持（表单保留）。
    """

    def __init__(self, params: dict):
        p = params or {}
        self.group_keys = [k.strip() for k in str(p.get("groupKeys") or "").split(",") if k.strip()]
        self.aggs: list[tuple[str, str, str]] = []
        for r in _kv_rows(p, "aggs"):
            field = str(r["key"]).strip()
            val = str(r.get("value") or "").strip()
            if ":" in val:
                func, alias = (x.strip() for x in val.split(":", 1))
            else:
                func, alias = val, f"{field}_{val}"
            if func not in AGG_FUNCS:
                raise OpError(f"未知聚合函数: {func}（支持 {AGG_FUNCS}）")
            self.aggs.append((field, func, alias))
        self.window_type = str(p.get("windowType") or "tumbling")
        self.size = max(1, int(p.get("windowSizeSec") or 60))
        self.slide = max(1, int(p.get("slideSec") or 10)) if self.window_type == "sliding" else self.size
        self.watermark = max(0, int(p.get("watermarkSec") or 5))
        self._lock = threading.Lock()
        self._buckets: dict[tuple, dict] = {}   # (ws, group) → {start, end, rows}
        self._emit: Optional[Callable] = None
        self._stop = threading.Event()
        self._timer: Optional[threading.Thread] = None
        self._emit_count = 0

    def open(self) -> None:
        self._timer = threading.Thread(target=self._fire_loop, name=f"win-{id(self):x}", daemon=True)
        self._timer.start()

    def bind_emit(self, emit) -> None:  # noqa: ANN001
        """引擎在装配阶段注入下游投递函数（定时触发用）。"""
        self._emit = emit

    def process(self, row: dict, emit) -> None:  # noqa: ANN001
        ts = float(row.get("ts") or time.time())
        group = tuple(row["data"].get(k) for k in self.group_keys)
        with self._lock:
            for ws in self._bucket_starts(ts):
                key = (ws, group)
                bucket = self._buckets.get(key)
                if bucket is None:
                    bucket = {"start": ws, "end": ws + self.size, "rows": []}
                    self._buckets[key] = bucket
                bucket["rows"].append(dict(row["data"]))
        emit(row)  # 原始行继续透传（明细流不阻断），聚合结果由触发线程另行投递

    def _bucket_starts(self, ts: float) -> list:
        if self.window_type == "tumbling":
            return [int(ts // self.size) * self.size]
        first = int((ts - self.size) // self.slide) * self.slide  # 覆盖 ts 的全部滑动桶起点
        return [
            ws for ws in range(first, int(ts // self.slide) * self.slide + 1, self.slide)
            if ws <= ts < ws + self.size
        ]

    def _fire_loop(self) -> None:
        while not self._stop.is_set():
            fired: list[dict] = []
            now = time.time()
            with self._lock:
                for key, b in list(self._buckets.items()):
                    if now >= b["end"] + self.watermark:
                        fired.append(self._result(b))
                        del self._buckets[key]
            for out in fired:
                if self._emit is not None:
                    try:
                        self._emit(out)
                        self._emit_count += 1
                    except Exception as exc:  # noqa: BLE001 触发投递失败仅记日志（下游队列断开时）
                        logger.warning("窗口触发投递失败: %r", exc)
            self._stop.wait(1.0)

    def _result(self, bucket: dict) -> dict:
        rows = bucket["rows"]
        out: dict = {}
        if self.group_keys:
            first = rows[0] if rows else {}
            out = {k: first.get(k) for k in self.group_keys}
        if not self.aggs:
            out["cnt"] = len(rows)
        for field, func, alias in self.aggs:
            if func == "count":
                out[alias] = len(rows)
                continue
            if func == "count_distinct":
                # 去重计数对任意类型值生效（如 user_id 字符串），不走数值过滤
                out[alias] = len({r.get(field) for r in rows if r.get(field) is not None})
                continue
            vals = [r.get(field) for r in rows if isinstance(r.get(field), (int, float))]
            if not vals:
                out[alias] = None
            elif func == "sum":
                out[alias] = sum(vals)
            elif func == "avg":
                out[alias] = sum(vals) / len(vals)
            elif func == "min":
                out[alias] = min(vals)
            elif func == "max":
                out[alias] = max(vals)
            elif func == "rms":
                out[alias] = (sum(v * v for v in vals) / len(vals)) ** 0.5
        out["win_start"] = bucket["start"]
        out["win_end"] = bucket["end"]
        return {"source": "window", "ts": time.time(), "data": out}

    @property
    def emits(self) -> int:
        return self._emit_count

    def close(self) -> None:
        self._stop.set()
        if self._timer is not None:
            self._timer.join(timeout=3)
            self._timer = None
