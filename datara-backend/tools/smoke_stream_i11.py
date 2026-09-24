"""I11 流处理组件冒烟脚本（D2 实测驱动）：三工作流 定义→保存→启动→API 数据验证。

对齐 stream-realtime-demos 三 use_case：
- WF1 电商大盘：3 模拟源（order_pay/user_click/cart_event）→ 各 10s 窗口聚合 → union → API → 电商看板；
- WF2 IoT 监控：温/压/振 3 源按 device 5s 窗口（avg/max/rms）+ 告警透传 → union → API → IoT 看板；
- WF3 站点分析：Redis Stream 双源（order_stream/user_stream）→ 全局窗口 gmv + page 分组窗口 → union → API → 站点看板。

用法（本机或任意可达 1.9 的环境）：
  python tools/smoke_stream_i11.py --base http://192.168.1.9:8000/api/v1
  python tools/smoke_stream_i11.py --only wf1          # 只跑单个工作流
  python tools/smoke_stream_i11.py --wait 60           # 数据观察窗口秒数
"""

import argparse
import json
import sys
import threading
import time

import requests

ARGS = argparse.Namespace()
FAILS: list[str] = []


def _p(msg: str) -> None:
    print(msg, flush=True)


def _fail(msg: str) -> None:
    FAILS.append(msg)
    _p(f"  [FAIL] {msg}")


def _pass(msg: str) -> None:
    _p(f"  [PASS] {msg}")


def api(method: str, path: str, token: str = "", **kwargs) -> dict:
    headers = dict(kwargs.pop("headers", {}))
    if token:
        headers["token"] = token
    r = requests.request(method, f"{ARGS.base}{path}", headers=headers, timeout=15, **kwargs)
    r.raise_for_status()
    body = r.json()
    if isinstance(body, dict) and body.get("code") not in (0, None):
        raise RuntimeError(f"{method} {path} -> {body}")
    return body.get("data", body) if isinstance(body, dict) else body


# ---------- 画布构造 ----------

def _n(nid: str, ntype: str, name: str, x: float, data: dict) -> dict:
    return {"id": nid, "type": ntype, "position": {"x": x, "y": 0}, "data": {"name": name, **data}}


def _e(s: str, t: str) -> dict:
    return {"id": f"e_{s}_{t}", "source": s, "target": t, "kind": "flow"}


def _doc(name: str, nodes: list, edges: list) -> dict:
    return {"id": name, "name": name, "version": 1, "meta": {"profile": "stream"},
            "nodes": nodes, "edges": edges}


def _win(name: str, x: float, group_keys: str, aggs: list, size: int) -> dict:
    return _n(name, "stream_fuse", name, x, {
        "fuseType": "window", "groupKeys": group_keys, "aggs": aggs,
        "windowType": "tumbling", "windowSizeSec": size, "slideSec": size, "watermarkSec": 0,
    })


def _sim_src(nid: str, name: str, events: str, eps: float) -> dict:
    return _n(nid, "stream_input", name, 0, {
        "srcType": "simulate", "simDataset": "ecommerce", "simEvents": events, "simEps": eps,
    })


def _sim_src_iot(nid: str, name: str, events: str, eps: float) -> dict:
    d = _sim_src(nid, name, events, eps)
    d["data"]["simDataset"] = "iot"
    return d


def _redis_src(nid: str, name: str, stream: str) -> dict:
    return _n(nid, "stream_input", name, 0, {
        "srcType": "redis", "redisUrl": "redis://redis:6379/0", "streamsText": stream,
        "redisGroup": "datara-flink", "redisConsumer": "c1",
    })


def _union(nid: str, name: str, x: float) -> dict:
    return _n(nid, "stream_fuse", name, x, {"fuseType": "union", "alignMap": []})


def _api_out(nid: str, name: str, x: float) -> dict:
    # keepLast=600：窗口行速率低（~0.3 行/s）而原始行持续透传占缓冲，缓冲过小会把最新窗口行挤出
    return _n(nid, "stream_output", name, x, {"outType": "api", "keepLast": 600, "schemaText": ""})


def _board(nid: str, name: str, x: float, preset: str) -> dict:
    return _n(nid, "page_board", name, x, {"preset": preset})


def build_wf1() -> tuple[str, dict]:
    """WF1 电商大盘（use_case1）：3 模拟源 → 各自 10s 窗口 → union → API → 看板。"""
    nodes = [
        _sim_src("t1", "订单流", "order_pay", 2),
        _sim_src("t2", "点击流", "user_click", 3),
        _sim_src("t3", "加购流", "cart_event", 2),
        _win("w1", 200, "", [
            {"key": "amount", "value": "sum:amt_total"},
            {"key": "order_id", "value": "count:ord_cnt"},
            {"key": "user_id", "value": "count_distinct:uv"},
        ], 10),
        _win("w2", 200, "goods_id", [{"key": "user_id", "value": "count:click_cnt"}], 10),
        _win("w3", 200, "goods_id", [{"key": "user_id", "value": "count:cart_cnt"}], 10),
        _union("u1", "三路合并", 400),
        _api_out("o1", "API通道", 600),
        _board("b1", "电商实时大盘", 800, "ecommerce"),
    ]
    edges = [_e("t1", "w1"), _e("t2", "w2"), _e("t3", "w3"),
             _e("w1", "u1"), _e("w2", "u1"), _e("w3", "u1"), _e("u1", "o1"), _e("o1", "b1")]
    return "I11_电商实时大盘", _doc("wf_i11_ecommerce", nodes, edges)


def build_wf2() -> tuple[str, dict]:
    """WF2 IoT 监控（use_case2）：温/压/振 按 device 5s 窗口（avg/max/rms）+ 告警透传 → union → API → 看板。"""
    nodes = [
        _sim_src_iot("i1", "温度流", "temp", 2),
        _sim_src_iot("i2", "压力流", "press", 2),
        _sim_src_iot("i3", "振动流", "vib", 2),
        _sim_src_iot("i4", "告警流", "alert", 1),
        _win("w1", 200, "device", [{"key": "value", "value": "avg:temp_avg"}], 5),
        _win("w2", 200, "device", [{"key": "value", "value": "max:press_max"}], 5),
        _win("w3", 200, "device", [{"key": "value", "value": "rms:vib_rms"}], 5),
        _union("u1", "四路合并", 400),
        _api_out("o1", "API通道", 600),
        _board("b1", "IoT设备监控", 800, "iot"),
    ]
    edges = [_e("i1", "w1"), _e("i2", "w2"), _e("i3", "w3"), _e("i4", "u1"),
             _e("w1", "u1"), _e("w2", "u1"), _e("w3", "u1"), _e("u1", "o1"), _e("o1", "b1")]
    return "I11_IoT设备监控", _doc("wf_i11_iot", nodes, edges)


def build_wf3() -> tuple[str, dict]:
    """WF3 站点分析（use_case3）：Redis Stream 双源 → 全局窗口 gmv + page 分组窗口 → union → API → 看板。"""
    nodes = [
        _redis_src("r1", "订单流(Redis)", "order_stream"),
        _redis_src("r2", "访问流(Redis)", "user_stream"),
        _win("w1", 200, "", [{"key": "amount", "value": "sum:gmv"}], 10),
        _win("w2", 200, "page", [{"key": "user_id", "value": "count:page_pv"}], 10),
        _union("u1", "双路合并", 400),
        _api_out("o1", "API通道", 600),
        _board("b1", "站点访问分析", 800, "visit"),
    ]
    edges = [_e("r1", "w1"), _e("r2", "w2"), _e("w1", "u1"), _e("w2", "u1"), _e("u1", "o1"), _e("o1", "b1")]
    return "I11_站点访问分析", _doc("wf_i11_visit", nodes, edges)


# ---------- 运行与验证 ----------

def deploy_wf(token: str, name: str, doc: dict) -> int:
    """创建定义 → 保存画布 → 启动流任务 → 返回 job id。"""
    wid = api("POST", "/workflow-definitions", token, json={"name": name})["id"]
    doc["id"] = wid  # save 校验 doc.id 与路径一致
    doc["name"] = name
    api("PUT", f"/workflow-definitions/{wid}/save", token, json={"doc": doc, "remark": "I11 冒烟"})
    _p(f"  画布已保存: {name} (id={wid}, nodes={len(doc['nodes'])})")
    job = api("POST", "/stream-jobs/start", token, json={"doc_id": wid})
    _p(f"  流任务启动: job={job['id']} restarted={job['restarted']}")
    return int(job["id"])


def wait_running(token: str, job_id: int, timeout: int = 60) -> str:
    deadline = time.time() + timeout
    status = ""
    while time.time() < deadline:
        row = api("GET", f"/stream-jobs/{job_id}", token)
        status = str(row.get("status") or "")
        if status in ("running", "failed", "stopped"):
            break
        time.sleep(2)
    return status


def verify(token: str, tag: str, job_id: int) -> None:
    """数据观察窗口后拉取 API 通道快照，按 WF 语义断言核心字段。"""
    tag = tag.upper()
    _p(f"  等待 {ARGS.wait}s 产出窗口数据…")
    time.sleep(ARGS.wait)
    snap = api("GET", f"/stream-jobs/{job_id}/data?mode=poll&limit=800", token)
    rows = snap.get("rows") or []
    metrics = snap.get("metrics") or {}
    _p(f"  metrics: {json.dumps(metrics, ensure_ascii=False)}")
    if not rows:
        _fail(f"{tag}: API 通道无数据行")
        return
    _pass(f"{tag}: API 通道 {len(rows)} 行（Last-N 保留）")

    win_rows = [r for r in rows if r.get("win_start") is not None]
    events = {r.get("event") for r in rows}
    if tag == "WF1":
        gmv_rows = [r for r in win_rows if r.get("amt_total") is not None]
        click_rows = [r for r in win_rows if r.get("click_cnt") is not None]
        cart_rows = [r for r in win_rows if r.get("cart_cnt") is not None]
        if gmv_rows and click_rows and cart_rows:
            latest = max(r["win_start"] for r in gmv_rows)
            cur = next(r for r in gmv_rows if r["win_start"] == latest)
            _pass(f"WF1: 三路窗口行齐备（gmv={len(gmv_rows)}, click={len(click_rows)}, cart={len(cart_rows)}）；"
                  f"最新窗口 GMV={cur.get('amt_total')} 订单={cur.get('ord_cnt')} UV={cur.get('uv')}")
        else:
            _fail(f"WF1: 窗口行不全 gmv={len(gmv_rows)} click={len(click_rows)} cart={len(cart_rows)}")
    elif tag == "WF2":
        temp_rows = [r for r in win_rows if r.get("temp_avg") is not None]
        press_rows = [r for r in win_rows if r.get("press_max") is not None]
        vib_rows = [r for r in win_rows if r.get("vib_rms") is not None]
        alert_rows = [r for r in rows if r.get("event") == "alert"]
        if temp_rows and press_rows and vib_rows:
            _pass(f"WF2: 三聚合窗口行齐备（temp={len(temp_rows)}, press={len(press_rows)}, vib={len(vib_rows)}），"
                  f"设备分组 {len({r.get('device') for r in temp_rows})} 个，告警透传 {len(alert_rows)} 条")
        else:
            _fail(f"WF2: 聚合行不全 temp={len(temp_rows)} press={len(press_rows)} vib={len(vib_rows)} alert={len(alert_rows)}")
        if alert_rows:
            _pass(f"WF2: 告警事件行到达看板通道（样例 {alert_rows[0]})")
    elif tag == "WF3":
        gmv_rows = [r for r in win_rows if r.get("gmv") is not None]
        page_rows = [r for r in win_rows if r.get("page_pv") is not None]
        if gmv_rows and page_rows:
            latest = max(r["win_start"] for r in gmv_rows)
            cur = next(r for r in gmv_rows if r["win_start"] == latest)
            pages = sorted({r.get("page") for r in page_rows if r["win_start"] == latest})
            _pass(f"WF3: Redis 双流窗口行齐备（gmv={len(gmv_rows)}, page={len(page_rows)}）；"
                  f"最新窗口 GMV={cur.get('gmv')}，页面分布 {pages}")
        else:
            _fail(f"WF3: 窗口行不全 gmv={len(gmv_rows)} page={len(page_rows)}（检查灌数与消费组）")
    _p(f"  事件集合: {sorted(x for x in events if x)}；样例行: {json.dumps(rows[-1], ensure_ascii=False)[:200]}")


# ---------- WF3 Redis 灌数（Redis Stream 源无内置数据生成，需外部持续 XADD） ----------

def _redis_feeder(url: str, eps: float) -> None:
    """后台 daemon 线程：向 order_stream/user_stream 灌数直至进程退出。

    事件 schema 与 tools/seed_stream.py gen_visit 一致（订单流 20% 带金额、访问流带 page），
    直连宿主机映射端口（1.9 redis 6380→6379），与容器内源的 redis://redis:6379/0 同库。
    """
    try:
        import redis
        from seed_stream import gen_visit
    except ImportError as exc:
        _p(f"  [WARN] 灌数依赖缺失（pip install redis）: {exc}")
        return
    try:
        r = redis.from_url(url, decode_responses=True, socket_connect_timeout=5)
        r.ping()
    except Exception as exc:  # noqa: BLE001
        _p(f"  [WARN] Redis 灌数不可达 {url}: {exc}")
        return
    _p(f"[feeder] XADD 灌数中: {url} eps={eps}")
    while True:
        stream, data = gen_visit(time.time())
        try:
            r.xadd(stream, {"data": json.dumps(data, ensure_ascii=False)})
        except Exception as exc:  # noqa: BLE001
            _p(f"  [WARN] XADD 失败: {exc}")
            time.sleep(2)
            continue
        time.sleep(1.0 / eps)


def run_suite(token: str, only: str) -> None:
    builders = {"wf1": build_wf1, "wf2": build_wf2, "wf3": build_wf3}
    jobs: dict[str, int] = {}
    for tag, build in builders.items():
        if only and tag != only:
            continue
        name, doc = build()
        _p(f"[{tag}] {name}")
        try:
            jobs[tag] = deploy_wf(token, name, doc)
        except Exception as exc:  # noqa: BLE001
            _fail(f"{tag} 部署失败: {exc}")
    time.sleep(5)
    for tag, jid in jobs.items():
        _p(f"[{tag}] job={jid} 状态确认")
        status = wait_running(token, jid)
        if status == "running":
            _pass(f"{tag}: 任务 running")
        else:
            row = api("GET", f"/stream-jobs/{jid}", token)
            _fail(f"{tag}: 任务状态 {status} lastError={row.get('lastError')}")
            continue
        verify(token, tag, jid)
    _p("")
    if FAILS:
        _p(f"冒烟结论: {len(FAILS)} 项失败")
        for f in FAILS:
            _p(f"  - {f}")
        sys.exit(1)
    _p("冒烟结论: 全部通过")


def main() -> None:
    global ARGS
    ap = argparse.ArgumentParser(description="I11 流处理冒烟")
    ap.add_argument("--base", default="http://192.168.1.9:8000/api/v1")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--pwd", default="Admin@123")
    ap.add_argument("--only", default="", choices=["", "wf1", "wf2", "wf3"])
    ap.add_argument("--wait", type=int, default=45, help="启动后数据观察秒数")
    ap.add_argument("--redis-url", default="redis://192.168.1.9:6380/0",
                    help="WF3 灌数用 Redis 地址（宿主机映射端口）")
    ARGS = ap.parse_args()

    token = api("POST", "/login", json={"user_name": ARGS.user, "user_pwd": ARGS.pwd})
    token = token["token"] if isinstance(token, dict) else token
    _p(f"登录成功 token={str(token)[:8]}…")
    if ARGS.only in ("", "wf3"):
        threading.Thread(target=_redis_feeder, args=(ARGS.redis_url, 5), daemon=True).start()
    run_suite(token, ARGS.only)


if __name__ == "__main__":
    main()
