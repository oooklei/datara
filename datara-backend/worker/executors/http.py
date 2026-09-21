"""C16 HTTP 执行器（I4 设计文档 §6.2，对齐海豚 HttpTask 简化版）。

- params：url / method（缺省 GET）/ headers（dict 或 [{key,value}] 表）/ body / bodyType(json|form)
  / successCodes（默认 2xx，支持 2xx/3xx 通配与显式码）/ extract（{输出名: 点路径} 或行表）/ timeout（秒）
- 提取：点路径 a.b[0].c 从 JSON 响应取子集 → 输出参数；缺失告警跳过
"""

import json
import re
import time

import requests

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


def _norm_rows(value) -> dict:
    """表单键值表兼容：[{key,value}] → dict（dict 原样）。"""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return {
            str(r["key"]).strip(): str(r.get("value") or "")
            for r in value
            if isinstance(r, dict) and str(r.get("key") or "").strip()
        }
    return {}


def _ok_code(code: int, rules) -> bool:
    """成功码判定：'2xx' 通配（任意百位段）或显式数字码；空规则视为 2xx。"""
    for rule in rules or ["2xx"]:
        text = str(rule).strip()
        if text.endswith("xx") and text[:-2].isdigit():
            base = int(text[:-2])
            if base * 100 <= code < (base + 1) * 100:
                return True
        elif text.isdigit() and int(text) == code:
            return True
    return False


def _walk_path(data, path: str):
    """点路径取值：a.b[0].c → 逐段 dict 取键 / list 取下标；缺失返回 None。"""
    cur = data
    for seg in re.findall(r"[^\.\[\]]+|\[\d+\]", path or ""):
        if seg.startswith("["):
            idx = int(seg[1:-1])
            if isinstance(cur, list) and -len(cur) <= idx < len(cur):
                cur = cur[idx]
            else:
                return None
        elif isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


@register("http")
def execute(ctx) -> ExecResult:
    """HTTP 请求：成功码校验 → 点路径提取 → 输出参数（status_code + 提取名）。"""
    param = ctx.param or {}
    url = str(param.get("url") or "").strip()
    if not url:
        ctx.log("[http] 未指定 URL")
        return ExecResult(FAILURE, {}, [])
    method = str(param.get("method") or "GET").upper()
    if method not in ("GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"):
        ctx.log("[http] 不支持的 method: %s" % method)
        return ExecResult(FAILURE, {}, [])
    headers = _norm_rows(param.get("headers"))
    body = param.get("body")
    body_type = str(param.get("bodyType") or "json").lower()
    success_rules = param.get("successCodes") or ["2xx"]
    if isinstance(success_rules, str):  # 表单侧逗号分隔字符串（如 "2xx,200"）→ 规则列表
        success_rules = [s.strip() for s in success_rules.split(",") if s.strip()] or ["2xx"]
    extract = _norm_rows(param.get("extract"))
    timeout = int(param.get("timeout") or 30)

    json_payload, data = None, None
    if body not in (None, "") and method not in ("GET", "HEAD"):
        if body_type == "json":
            try:
                json_payload = body if isinstance(body, (dict, list)) else json.loads(str(body))
            except ValueError as exc:
                ctx.log("[http] JSON 请求体解析失败: %r" % exc)
                return ExecResult(FAILURE, {}, [])
        else:
            data = str(body)

    ctx.log("[http] %s %s（timeout=%ss，成功码=%s）" % (method, url, timeout, success_rules))
    t0 = time.monotonic()
    try:
        resp = requests.request(
            method, url, headers=headers or None, json=json_payload, data=data, timeout=timeout
        )
    except Exception as exc:  # noqa: BLE001 连接/超时异常 → failure
        ctx.log("[http] 请求失败: %r" % exc)
        return ExecResult(FAILURE, {}, [])
    elapsed = int((time.monotonic() - t0) * 1000)
    outputs = {"status_code": resp.status_code}
    preview = resp.text[:200].replace("\n", " ")
    ctx.log("[http] 响应 %s %dms body≈%s" % (resp.status_code, elapsed, preview))
    if not _ok_code(resp.status_code, success_rules):
        ctx.log("[http] 状态码 %s 不在成功码列表，按失败处理" % resp.status_code)
        return ExecResult(FAILURE, outputs, [])

    if extract:
        try:
            payload = resp.json()
        except ValueError:
            payload = None
            ctx.log("[http] 响应非 JSON，跳过提取")
        for out_name, path in extract.items():
            value = _walk_path(payload, str(path))
            if value is None:
                ctx.log("[http] 提取 %s ← %r 未命中（置空串）" % (out_name, path))
                outputs[str(out_name)] = ""
            elif isinstance(value, (dict, list)):
                outputs[str(out_name)] = json.dumps(value, ensure_ascii=False)
            else:
                outputs[str(out_name)] = str(value)
            ctx.log("[http] 提取 %s ← %r = %r" % (out_name, path, outputs[str(out_name)]))
    return ExecResult(SUCCESS, outputs, [])
