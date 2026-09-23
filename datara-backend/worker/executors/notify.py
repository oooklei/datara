"""C26 通知执行器（I12 设计 §3.3）：webhook POST / 仅日志；触发时机由 master 判定后派发。

- 参数（四级变量链已在 master 解析，此处经 vars_render 再兜底一跳，覆盖直发/重派路径）：
  channel=log|webhook / url / template / trigger（on_success|on_failure|always，仅留痕）/ failHard
- webhook：JSON {"text": msg} POST，超时 10s；失败默认仅告警不断流（failHard=true 才 failure）
- 输出：notified=true / error；消息模板内置变量提示 ${wf.name} ${instance_id} ${node.name} ${sys.now}
"""

import json
import urllib.request

from common.vars_render import render_text
from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS

WEBHOOK_TIMEOUT = 10  # 秒（设计 §3.3：失败不重试，超时即失败）


@register("notify")
def run_notify(ctx) -> ExecResult:
    """C26 主流程：渲染消息 →（webhook 通道）POST → 输出留痕。"""
    param = ctx.param or {}
    channel = str(param.get("channel") or "log")
    url = str(render_text(str(param.get("url") or ""), param)[0] or "").strip()
    msg = render_text(str(param.get("template") or ""), param)[0]
    ctx.log("[notify] 通道=%s 触发时机=%s url=%s 消息=%s"
            % (channel, param.get("trigger") or "on_success", "有" if url else "无", msg))
    if channel == "webhook" and url:
        req = urllib.request.Request(
            url,
            data=json.dumps({"text": msg}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=WEBHOOK_TIMEOUT) as resp:
                ctx.log("[notify] webhook 响应 %s" % getattr(resp, "status", ""))
        except Exception as exc:  # noqa: BLE001 通知失败默认不阻断（设计 §3.3）
            ctx.log("[notify] webhook 失败（不阻断）: %r" % exc)
            if param.get("failHard"):  # I12 T11 修：键名统一 camelCase
                return ExecResult(FAILURE, {"error": str(exc)}, [])
    return ExecResult(SUCCESS, {"notified": True}, [])
