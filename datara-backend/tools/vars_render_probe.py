"""I12-D5 变量渲染边界探针（本机直跑 / 容器内均可）。

用法：python tools/vars_render_probe.py
边界断言（I12 缺陷排查 D5），全部通过打印 PROBE_OK：
- 空值变量：None → 渲染为空串（修复前 str(None)="None"）
- VarResolver workflow/env 层 None 值 → 空串（I12-D5 补漏：levels 分支与引擎口径统一）
- 空串变量 → 空串
- 嵌套占位 ${a${b}} → 不递归、原样保留
- 含引号值进入 SQL → 渲染层原样透传（不转义；SQL 拼接安全归使用方/执行口径）
- 未知变量 → 保留原样 + snapshot 记 unresolved
- 循环引用 → MAX_DEPTH 截断不死循环
- 时间变量 / date(N) / 日期命名模式基础回归（基准 now 固定，输出可断言）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.vars_render import MAX_DEPTH, render_text  # noqa: E402

FAILS = []

BASE = __import__("datetime").datetime(2026, 9, 22, 10, 30, 0)


def check(name, cond, detail=""):
    if cond:
        print("  ok  %s" % name)
    else:
        FAILS.append(name)
        print("  FAIL %s %s" % (name, detail))


# ---- 空值/空串 ----
out, _ = render_text("A=${v}", {"v": None}, BASE)
check("None 值渲染为空串", out == "A=", repr(out))
out, _ = render_text("A=${v}", {"v": ""}, BASE)
check("空串渲染为空串", out == "A=", repr(out))

# ---- 嵌套占位（不递归：${a${b}} 不拆解 ${b}） ----
out, _ = render_text("${a${b}}", {"a": "X", "b": "Y"}, BASE)
check("嵌套占位原样保留", out == "${a${b}}", repr(out))

# ---- 含引号值进入 SQL 形态（口径固化：渲染层不转义） ----
out, _ = render_text("WHERE name='${name}'", {"name": "O'Brien"}, BASE)
check("单引号值原样透传", out == "WHERE name='O'Brien'", repr(out))
out, _ = render_text("${v}", {"v": 'x"y\\z'}, BASE)
check("引号反斜杠原样透传", out == 'x"y\\z', repr(out))

# ---- 未知变量 ----
out, snap = render_text("S=${nope}", {}, BASE)
check("未知变量保留原样", out == "S=${nope}", repr(out))
check("unresolved 留痕", any(s.get("resolved") is False and s.get("name") == "${nope}" for s in snap), repr(snap))

# ---- 循环引用（MAX_DEPTH 截断） ----
out, _ = render_text("${a}", {"a": "${a}"}, BASE)
check("循环引用不死循环", out == "${a}" and len(out) >= 0, repr(out))
deep = "${a}"
params = {"a": "${b}", "b": "${a}"}
out, _ = render_text(deep, params, BASE)
check("互环引用 MAX_DEPTH 截断", isinstance(out, str), repr(out))

# ---- 时间变量 / date(N) / 日期命名模式（固定 now 回归） ----
out, _ = render_text("$[yyyyMMdd-1]", {}, BASE)
check("时间模板偏移", out == "20260921", repr(out))
out, _ = render_text("${date(-1)}", {}, BASE)
check("date(N) 函数式", out == "2026-09-21", repr(out))
out, _ = render_text("${yyyyMMdd_HHmmss}", {}, BASE)
check("日期命名模式", out == "20260922_103000", repr(out))
out, _ = render_text("${biz_date}", {}, BASE)
check("内置 biz_date=T-1", out == "2026-09-21", repr(out))

# ---- VarResolver 四级链 workflow/env 层 None 值（I12-D5 补漏：levels 分支 str(None)="None"） ----
from master.variables import VarResolver  # noqa: E402

resolver = VarResolver(
    "inst-probe", 1,
    {"workflow": {"wv": None}, "env": {"envv": None}, "global": {}},
    BASE,
)
out = resolver.resolve_text("A=${wv}", {}, 0, {})
check("workflow 级 None 渲染为空串", out == "A=", repr(out))
out = resolver.resolve_text("B=${envv}", {}, 0, {})
check("env 级 None 渲染为空串", out == "B=", repr(out))

# ---- 递归上限语义（全局参数值再含占位） ----
out, _ = render_text("${a}", {"a": "${b}", "b": "ok"}, BASE)
check("全局参数递归解析", out == "ok", repr(out))
check("MAX_DEPTH 常量生效", MAX_DEPTH == 5, str(MAX_DEPTH))

print()
if FAILS:
    print("PROBE_FAILED: %d 项未过 -> %s" % (len(FAILS), FAILS))
    raise SystemExit(1)
print("PROBE_OK")
