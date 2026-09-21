"""SQL 变量渲染核心（I10 设计文档 §4.2 G4；引擎 master/variables.py 与 IDE 共用）。

- ${var} 占位渲染 + $[日期模板] 求值（引擎语法保留兼容）
- 内置时间参数 14 项（biz_date 默认 T-1、today、date(N) 函数式、month_start/end、
  last_month_start/end、lyear、year、hour、timestamp、datetime、ts_nodash、nodash 系列）
- IDE 来源链：全局参数(t_global_param by env) > 内置时间参数 > date(N) > 日期命名模式
- 引擎四级链（节点参数/注入层/工作流变量/环境组/全局）仍在 master/variables.py，
  ${var} 正则与 time_var 求值下沉本模块共用（引擎行为不变，回归门覆盖）
- 变量快照明文不脱敏（09-18 裁定）
"""

import calendar
import re
from datetime import datetime, timedelta
from typing import Optional

# 与引擎同款正则（master/variables.py 原定义下沉至此共用）
VAR_RE = re.compile(r"\$\{([^}]+)\}")
TIME_RE = re.compile(r"\$\[([^\]]+)\]")
MAX_DEPTH = 5  # 嵌套引用递归上限（防循环引用）

# date(N) 函数式：${date(3)} → T+3、${date(-1)} → T-1（yyyy-MM-dd）
_DATE_FUNC_RE = re.compile(r"^date\(\s*([+-]?\d+)\s*\)$")

# 日期命名模式 token（先长后短替换，避免 mm 抢占 MM 语义）
_PATTERN_TOKENS = (("yyyy", "%Y"), ("MM", "%m"), ("dd", "%d"), ("HH", "%H"), ("mm", "%M"), ("ss", "%S"))
# 模式残留校验：替换后仅允许 strftime 占位符（%YmdHMS）与分隔符（防 summary 等普通名误命中）
_PATTERN_RESIDUAL_RE = re.compile(r"^[%YmdHMS_\-.: ]*$")


def time_var(inner: str, base: datetime) -> str:
    """内置时间变量求值：$[yyyyMMdd-1] / $[yyyy-MM-dd] / $[HHmmss] / $[yyyyMMdd 0800]。

    语法（海豚 System Variables 子集）：日期/时间模板 + 可选 ±N 天偏移 + 可选空格后定点时刻
    （0800 → 08:00，080000 → 08:00:00）。
    """
    offset = 0
    match = re.search(r"([+-]\d+)$", inner)
    if match:
        offset = int(match.group(1))
        inner = inner[: match.start()]
    fixed = ""
    if " " in inner:
        inner, fixed = inner.split(" ", 1)
        digits = re.sub(r"\D", "", fixed)
        if len(digits) == 4:
            fixed = "%s:%s" % (digits[:2], digits[2:])
        elif len(digits) >= 6:
            fixed = "%s:%s:%s" % (digits[:2], digits[2:4], digits[4:6])
    result = base + timedelta(days=offset)
    fmt = inner.replace("yyyy", "%Y").replace("MM", "%m").replace("dd", "%d")
    fmt = fmt.replace("HH", "%H").replace("mm", "%M").replace("ss", "%S")
    text = result.strftime(fmt) if fmt else ""
    return "%s %s" % (text, fixed) if fixed else text


def builtin_vars(now: Optional[datetime] = None) -> dict:
    """内置时间参数 14 项（§4.2 G4；now 为求值基准，默认当前时刻）。"""
    now = now or datetime.now()
    t1 = now - timedelta(days=1)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = first_of_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return {
        "biz_date": t1.strftime("%Y-%m-%d"),
        "biz_date_nodash": t1.strftime("%Y%m%d"),
        "today": now.strftime("%Y-%m-%d"),
        "today_nodash": now.strftime("%Y%m%d"),
        "year": str(now.year),
        "lyear": str(now.year - 1),
        "month_start": first_of_month.strftime("%Y-%m-%d"),
        "month_end": "%04d-%02d-%02d" % (
            now.year, now.month, calendar.monthrange(now.year, now.month)[1]
        ),
        "last_month_start": last_month_start.strftime("%Y-%m-%d"),
        "last_month_end": last_month_end.strftime("%Y-%m-%d"),
        "hour": now.strftime("%H"),
        "timestamp": str(int(now.timestamp())),
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "ts_nodash": now.strftime("%Y%m%d%H%M%S"),
    }


def render_pattern(name: str, now: datetime) -> Optional[str]:
    """日期命名模式：${yyyyMMdd_HHmmss} 等纯日期模板变量名 → 按模板求值。

    变量名必须仅由 yyyy/MM/dd/HH/mm/ss 与分隔符（_- .: 空格）组成且至少含一个日期
    token；否则返回 None（交回调用方按未解析处理）。
    """
    fmt = name
    hit = False
    for token, code in _PATTERN_TOKENS:
        if token in fmt:
            hit = True
        fmt = fmt.replace(token, code)
    if not hit or not _PATTERN_RESIDUAL_RE.match(fmt):
        return None
    return now.strftime(fmt)


def render_text(
    text: str,
    params: dict,
    now: Optional[datetime] = None,
    snapshot: Optional[list] = None,
    depth: int = 0,
) -> tuple:
    """IDE 口径渲染单值：全局参数 > 内置时间参数 > date(N) > 日期命名模式。

    - $[模板] 直接求值（引擎语法保留兼容）
    - 全局参数值本身仍含占位/时间变量时递归解析（上限 MAX_DEPTH，防循环引用）
    - 返回 (rendered_text, snapshot)；snapshot=[{name, value, source, resolved}] 明文
    - 未解析占位保留原样（对齐引擎容错口径）
    """
    if snapshot is None:
        snapshot = []
    if not isinstance(text, str) or depth >= MAX_DEPTH:
        return (text if isinstance(text, str) else str(text)), snapshot
    now = now or datetime.now()
    builtins = builtin_vars(now)

    def _time(match: "re.Match") -> str:
        inner = match.group(1)
        resolved = time_var(inner, now)
        snapshot.append(
            {"name": "$[%s]" % inner, "value": resolved, "source": "时间变量", "resolved": True}
        )
        return resolved

    def _var(match: "re.Match") -> str:
        name = match.group(1).strip()
        raw = match.group(0)
        if name in params:
            value = str(params[name])
            snapshot.append({"name": name, "value": value, "source": "全局参数", "resolved": True})
            return render_text(value, params, now, snapshot, depth + 1)[0]
        if name in builtins:
            value = builtins[name]
            snapshot.append({"name": name, "value": value, "source": "内置时间参数", "resolved": True})
            return value
        func = _DATE_FUNC_RE.match(name)
        if func is not None:
            value = (now + timedelta(days=int(func.group(1)))).strftime("%Y-%m-%d")
            snapshot.append({"name": name, "value": value, "source": "date(N)", "resolved": True})
            return value
        value = render_pattern(name, now)
        if value is not None:
            snapshot.append({"name": name, "value": value, "source": "日期命名模式", "resolved": True})
            return value
        snapshot.append({"name": raw, "value": raw, "source": "unresolved", "resolved": False})
        return raw

    return TIME_RE.sub(_time, VAR_RE.sub(_var, text)), snapshot
