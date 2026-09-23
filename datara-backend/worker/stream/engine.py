"""流引擎宿主（I8 裁定②，设计 §3.1/§3.2）：worker 进程内每任务 1 条 daemon 常驻线程。

- 控制：Redis pubsub datara:flink:ctl 广播（start 带 generation 先停旧线程再起新；stop 本地命中即停）；
- 认领：API 置 status=starting + host=NULL，worker 原子 UPDATE host=me 抢占（多 worker 单宿主）；
- 恢复：worker 启动扫 status∈{starting,running,reconnecting} 且 host=me 重新拉起（t_stream_offset 位点续跑）；
  收割线程周期自愈（宿主失联时其余 worker 抢占接手，对齐门 6 容错语义）；
- 状态机：starting→running↔reconnecting（指数退避 1s×2ⁿ 上限 30s，连续 30 次→failed + 告警）；
  stopped/failed 终态；指标 Hash datara:flink:metrics:{job}（2s 周期 TTL 90s）、日志 List Last-500。
"""

import json
import os
import queue as pyqueue
import socket
import threading
import time
from datetime import datetime
from typing import Optional

import redis

from common import queue as rq
from common.config import get_settings
from common.db import new_session
from common.log import get_logger
from common.models import AlertRecord, StreamJob, StreamOffset
from worker.stream.ops import JoinOp, WindowAggOp, build_op
from worker.stream.sinks import build_sink
from worker.stream.sources import SourceBase, build_source

logger = get_logger("worker.stream.engine")

CTL_CHANNEL = "datara:flink:ctl"
METRICS_PREFIX = "datara:flink:metrics:"
LOGS_PREFIX = "datara:flink:logs:"
ALIVE_PREFIX = "datara:flink:alive:"
ACTIVE_STATUSES = ("starting", "running", "reconnecting")
MAX_RETRIES = 30          # 连续失败上限 → failed（实测 KRaft 冷启动恢复 >180s，10 次/190s 会在恢复期误判死）
REAPER_INTERVAL = 30      # 收割/自愈周期（秒）
METRICS_INTERVAL = 2      # 指标周期（秒）
OFFSET_INTERVAL = 5       # 位点提交周期（秒）


class JobRuntime:
    """单流任务运行时：共享停止/失败信号、计数与位点。"""

    def __init__(self, job_id: int, generation: int, spec: dict):
        self.job_id = job_id
        self.generation = generation
        self.spec = spec
        self.stop_event = threading.Event()
        self.fail_event = threading.Event()
        self.fail_msg = ""
        self.status = "starting"
        self.total_in = 0
        self.total_out = 0
        self.errors = 0
        self.window_op: Optional[WindowAggOp] = None  # window 算子实例（windowEmits 指标用）
        self.offsets: dict = {}
        self._lock = threading.Lock()

    def request_stop(self) -> None:
        self.stop_event.set()

    def set_fail(self, msg: str) -> None:
        with self._lock:
            if not self.fail_event.is_set():
                self.fail_msg = msg
                self.errors += 1
            self.fail_event.set()

    def bump_in(self, n: int) -> None:
        with self._lock:
            self.total_in += n

    def bump_out(self, n: int) -> None:
        with self._lock:
            self.total_out += n

    def set_offsets(self, key: str, offset: dict) -> None:
        with self._lock:
            self.offsets[key] = offset

    def offsets_snapshot(self) -> dict:
        """位点快照（深拷贝，供跨线程读：提交落库 / 指标上报）。"""
        with self._lock:
            return {k: dict(v) for k, v in self.offsets.items()}


def _redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


class StreamEngine:
    """worker 内流引擎：控制订阅 + 收割自愈 + 每任务常驻线程。"""

    def __init__(self):
        self.identity = f"{socket.gethostname()}#{os.getpid()}"
        self._jobs: dict[int, JobRuntime] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ---------- 生命周期 ----------

    def start(self) -> None:
        for target, name in ((self._ctl_loop, "flink-ctl"), (self._reaper_loop, "flink-reaper")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        self.recover()
        logger.info("流引擎启动（identity=%s）", self.identity)

    def stop(self) -> None:
        self._stop.set()
        for rt in list(self._jobs.values()):
            rt.request_stop()
        for job_id in list(self._jobs):
            self._join_job(job_id)

    # ---------- 对外动作 ----------

    def submit(self, job_id: int, generation: int, spec: dict) -> None:
        """启动/重启任务线程（同 job 旧线程先停再起，generation 对齐）。"""
        with self._lock:
            old = self._jobs.get(job_id)
        if old is not None:
            old.request_stop()
            self._join_job(job_id)
        rt = JobRuntime(job_id, generation, spec)
        with self._lock:
            self._jobs[job_id] = rt
        threading.Thread(target=self._job_main, args=(rt,), name=f"flink-job-{job_id}", daemon=True).start()

    def stop_job(self, job_id: int) -> None:
        with self._lock:
            rt = self._jobs.get(job_id)
        if rt is not None:
            rt.request_stop()
            logger.info("流任务本地停止信号: job=%s", job_id)

    def recover(self) -> None:
        """worker 启动恢复：host=me 的活跃任务按 t_stream_offset 位点续跑。"""
        session = new_session()
        try:
            rows = (
                session.query(StreamJob)
                .filter(StreamJob.host == self.identity, StreamJob.status.in_(ACTIVE_STATUSES))
                .all()
            )
            for row in rows:
                try:
                    spec = json.loads(row.spec_json or "{}")
                except ValueError:
                    continue
                logger.info("流任务恢复（位点续跑）: job=%s gen=%s", row.id, row.generation)
                self.submit(row.id, row.generation, spec)
        finally:
            session.close()

    # ---------- 控制订阅 ----------

    def _ctl_loop(self) -> None:
        client = _redis()
        while not self._stop.is_set():
            pubsub = None
            try:
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(CTL_CHANNEL)
                for msg in pubsub.listen():
                    if self._stop.is_set():
                        break
                    if not msg or msg.get("type") != "message":
                        continue
                    try:
                        payload = json.loads(msg["data"])
                    except (ValueError, TypeError):
                        continue
                    self._handle_ctl(payload)
            except Exception as exc:  # noqa: BLE001 断线重连
                if not self._stop.is_set():
                    logger.warning("ctl 订阅异常 3s 重连: %r", exc)
                    self._stop.wait(3)
            finally:
                if pubsub is not None:
                    try:
                        pubsub.close()
                    except Exception:  # noqa: BLE001
                        pass

    def _handle_ctl(self, payload: dict) -> None:
        action = payload.get("action")
        try:
            job_id = int(payload.get("jobId") or 0)
            generation = int(payload.get("generation") or 0)
        except (TypeError, ValueError):
            return
        if job_id <= 0:
            return
        if action == "stop":
            self.stop_job(job_id)
            return
        if action != "start":
            return
        with self._lock:
            local = self._jobs.get(job_id)
        if local is not None:
            if local.generation == generation:
                return  # 本地已是该代号，幂等忽略
            local.request_stop()  # 旧代号线程让位（先停再起）
            self._join_job(job_id)
        claimed = self._claim(job_id, generation)
        if not claimed:
            logger.warning("流任务认领失败（代际/状态/宿主不匹配）: job=%s gen=%s", job_id, generation)
            return
        session = new_session()
        try:
            row = session.get(StreamJob, job_id)
            spec = json.loads(row.spec_json or "{}") if row else {}
        finally:
            session.close()
        if spec:
            self.submit(job_id, generation, spec)

    def _claim(self, job_id: int, generation: int) -> bool:
        """原子认领：host=NULL 或本机 → 置本机（多 worker 单宿主锚点）。"""
        session = new_session()
        try:
            updated = (
                session.query(StreamJob)
                .filter(
                    StreamJob.id == job_id,
                    StreamJob.generation == generation,
                    StreamJob.status.in_(ACTIVE_STATUSES),
                    (StreamJob.host.is_(None)) | (StreamJob.host == self.identity),
                )
                .update({"host": self.identity, "started_at": datetime.now()}, synchronize_session=False)
            )
            session.commit()
            return bool(updated)
        except Exception:  # noqa: BLE001
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- 收割/自愈 ----------

    def _reaper_loop(self) -> None:
        client = _redis()
        while not self._stop.is_set():
            try:
                client.setex(ALIVE_PREFIX + self.identity, 45, "1")
                self._reap_once(client)
            except Exception as exc:  # noqa: BLE001 自愈异常不崩线程
                logger.warning("流任务自愈扫描异常: %r", exc)
            self._stop.wait(REAPER_INTERVAL)

    def _reap_once(self, client: redis.Redis) -> None:
        session = new_session()
        try:
            # 1) 本地任务对账：host/generation/status 变化（他机接管/外部停止/重启代号）→ 停本地
            for job_id, rt in list(self._jobs.items()):
                row = session.get(StreamJob, job_id)
                if row is None or row.host != self.identity or row.generation != rt.generation \
                        or row.status not in ACTIVE_STATUSES:
                    logger.info("流任务本地对齐停止: job=%s（宿主/代号/状态变化）", job_id)
                    rt.request_stop()
            # 2) 自愈：本机宿主但无线程（如本机重启后 recover 遗漏）→ 重新拉起
            mine = (
                session.query(StreamJob)
                .filter(StreamJob.host == self.identity, StreamJob.status.in_(ACTIVE_STATUSES))
                .all()
            )
            for row in mine:
                if row.id in self._jobs:
                    continue
                try:
                    spec = json.loads(row.spec_json or "{}")
                except ValueError:
                    continue
                logger.info("流任务自愈拉起: job=%s gen=%s", row.id, row.generation)
                self.submit(row.id, row.generation, spec)
            # 3) 失联宿主接管：alive 缺失 → 清 host，广播 start 让健康 worker 抢占
            orphans = (
                session.query(StreamJob)
                .filter(StreamJob.status.in_(ACTIVE_STATUSES), StreamJob.host.isnot(None),
                        StreamJob.host != self.identity)
                .all()
            )
            for row in orphans:
                if client.exists(ALIVE_PREFIX + str(row.host)):
                    continue
                logger.info("流任务宿主失联接管: job=%s（原 host=%s）", row.id, row.host)
                updated = (
                    session.query(StreamJob)
                    .filter(StreamJob.id == row.id, StreamJob.host == row.host)
                    .update({"host": None}, synchronize_session=False)
                )
                session.commit()
                if updated:
                    rq.get_client().publish(CTL_CHANNEL, json.dumps(
                        {"action": "start", "jobId": row.id, "generation": row.generation}))
        finally:
            session.close()

    # ---------- 任务主流程 ----------

    def _job_main(self, rt: JobRuntime) -> None:
        backoff = 1.0
        consecutive = 0
        try:
            self._db_update(rt.job_id, rt.generation, status="starting", last_error=None)
            rt.status = "starting"
            self._log(rt.job_id, "INFO", f"流任务线程启动（gen={rt.generation}）")
            while not rt.stop_event.is_set():
                try:
                    self._pipeline_once(rt)
                    break  # 正常退出 = 收到停止
                except Exception as exc:  # noqa: BLE001 管道级可恢复错误 → 重连
                    if rt.stop_event.is_set():
                        break
                    consecutive += 1
                    rt.status = "reconnecting"
                    self._db_update(rt.job_id, rt.generation, status="reconnecting", last_error=str(exc)[:2000])
                    self._log(rt.job_id, "ERROR", f"管道异常（连续第 {consecutive} 次）: {exc}")
                    if consecutive >= MAX_RETRIES:
                        self._mark_failed(rt, str(exc))
                        return
                    rt.stop_event.wait(min(backoff, 30.0))
                    backoff = min(backoff * 2, 30.0)
            if rt.stop_event.is_set():
                rt.status = "stopped"
                self._db_update(rt.job_id, rt.generation, status="stopped")
                self._log(rt.job_id, "INFO", "流任务已停止")
        finally:
            with self._lock:
                self._jobs.pop(rt.job_id, None)

    def _mark_failed(self, rt: JobRuntime, err: str) -> None:
        rt.status = "failed"
        self._db_update(rt.job_id, rt.generation, status="failed", last_error=err[:2000])
        self._log(rt.job_id, "ERROR", f"连续 {MAX_RETRIES} 次重连失败，转 failed: {err}")
        session = new_session()
        try:
            session.add(AlertRecord(
                instance_id=None,
                title=f"流任务失败: {rt.spec.get('name') or rt.job_id}",
                content=str(err)[:2000],
                channel="system",
                state="wait",
            ))
            session.commit()
        except Exception:  # noqa: BLE001 告警失败不阻断状态收口
            session.rollback()
        finally:
            session.close()

    def _pipeline_once(self, rt: JobRuntime) -> None:
        """装配一次管道并运行至停止/失败（异常上抛由 _job_main 重连）。"""
        # 每次装配=全新尝试：清上轮残留失败信号，否则主循环开局即秒败旧 fail_msg（门5 恢复期卡死根因）
        rt.fail_event.clear()
        rt.fail_msg = ""
        spec = rt.spec
        nodes = {n["id"]: n for n in spec.get("nodes") or []}
        edges = spec.get("edges") or []
        outs: dict[str, list] = {}
        ins: dict[str, list] = {}
        for e in edges:
            outs.setdefault(e["source"], []).append(e["target"])
            ins.setdefault(e["target"], []).append(e["source"])
        queues: dict[tuple, pyqueue.Queue] = {
            (e["source"], e["target"]): pyqueue.Queue(maxsize=10000) for e in edges
        }
        out_queues = lambda nid: [queues[(nid, t)] for t in outs.get(nid, [])]  # noqa: E731
        in_queues = lambda nid: [queues[(s, nid)] for s in ins.get(nid, [])]  # noqa: E731

        sources: dict[str, SourceBase] = {}
        ops = {}
        sinks = []
        threads: list[threading.Thread] = []

        def emit_of(nid):
            targets = out_queues(nid)

            def _emit(row: dict) -> None:
                for q in targets:
                    _put(q, row, rt)
            return _emit

        for nid, node in nodes.items():
            ntype = node.get("type")
            params = node.get("params") or {}
            if ntype == "stream_input":
                src = build_source(nid, params)
                sources[src.source_key] = src
                threads.append(threading.Thread(
                    target=self._source_loop, args=(rt, src, out_queues(nid)),
                    name=f"flink-src-{nid}", daemon=True))
            elif ntype == "stream_fuse":
                op = build_op(str(params.get("fuseType") or "union"), params)
                ops[nid] = op
                if isinstance(op, WindowAggOp):
                    rt.window_op = op  # windowEmits 指标统计入口
                    op.bind_emit(emit_of(nid))  # 定时触发线程经同一 emit 投递聚合结果
                threads.append(threading.Thread(
                    target=self._fuse_loop, args=(rt, op, in_queues(nid), emit_of(nid)),
                    name=f"flink-op-{nid}", daemon=True))
            elif ntype == "stream_output":
                sink = build_sink(rt.job_id, nid, params)
                sinks.append(sink)
                threads.append(threading.Thread(
                    target=self._sink_loop, args=(rt, sink, in_queues(nid)),
                    name=f"flink-sink-{nid}", daemon=True))

        if not sources:
            raise RuntimeError("流子图缺少可用输入源")
        if not sinks:
            raise RuntimeError("流子图缺少输出汇")

        # 位点续跑：装配时读 t_stream_offset（源线程直接取 rt.offsets，不重复查库）
        saved = self._load_offsets(rt.job_id)
        for src in sources.values():
            rt.set_offsets(src.source_key, saved.get(src.source_key) or {})

        for t in threads:
            t.start()
        rt.status = "running"
        self._db_update(rt.job_id, rt.generation, status="running", started_at=datetime.now())
        self._log(rt.job_id, "INFO", f"管道装配完成并开始消费（源 {len(sources)} / 算子 {len(ops)} / 汇 {len(sinks)}）")

        try:
            last_metrics = 0.0
            last_offset_commit = 0.0
            prev_in, prev_t = 0, time.time()
            rate = 0.0
            while not rt.stop_event.is_set() and not rt.fail_event.is_set():
                if all(not t.is_alive() for t in threads):
                    break
                now = time.time()
                if now - last_metrics >= METRICS_INTERVAL:
                    dt = max(now - prev_t, 0.001)
                    inst = (rt.total_in - prev_in) / dt
                    rate = rate * 0.5 + inst * 0.5  # EMA 平滑
                    prev_in, prev_t = rt.total_in, now
                    self._metrics_tick(rt, rate)
                    last_metrics = now
                if now - last_offset_commit >= OFFSET_INTERVAL:
                    self._commit_offsets(rt)
                    last_offset_commit = now
                rt.stop_event.wait(0.2)
            if rt.fail_event.is_set() and not rt.stop_event.is_set():
                raise RuntimeError(rt.fail_msg or "管道异常退出")
        finally:
            for op in ops.values():
                try:
                    op.close()
                except Exception:  # noqa: BLE001
                    pass
            for s in sinks:
                try:
                    s.close()
                except Exception:  # noqa: BLE001
                    pass
            for src in sources.values():
                try:
                    src.close()
                except Exception:  # noqa: BLE001
                    pass
            for t in threads:
                t.join(timeout=3)
            self._commit_offsets(rt, force=True)
            self._metrics_tick(rt, 0.0)
            self._log(rt.job_id, "INFO", "管道收口（源/算子/汇已关闭）")

    # ---------- 各 stage 线程 ----------

    def _source_loop(self, rt: JobRuntime, src: SourceBase, targets: list) -> None:
        try:
            src.open(rt.offsets.get(src.source_key))
            while not rt.stop_event.is_set() and not rt.fail_event.is_set():
                rows = src.poll(200)
                if not rows:
                    rt.stop_event.wait(0.2)
                    continue
                for q in targets:
                    for row in rows:
                        _put(q, row, rt)
                rt.bump_in(len(rows))
                rt.set_offsets(src.source_key, src.offset)
        except Exception as exc:  # noqa: BLE001 上抛引擎统一重连
            if not rt.stop_event.is_set():
                rt.set_fail(f"源 {src.source_key}: {exc}")
                self._log(rt.job_id, "ERROR", f"源 {src.source_key} 异常: {exc}")
        finally:
            src.close()

    def _fuse_loop(self, rt: JobRuntime, op, in_qs: list, emit) -> None:
        """融合算子消费线程：join 双入边打 _side 标；其余多入边轮询合并（union 语义）。"""
        is_join = isinstance(op, JoinOp)
        if is_join and len(in_qs) < 2:
            rt.set_fail("join 融合须两条入边（装配校验缺失）")
            return
        try:
            op.open()
            while not rt.stop_event.is_set() and not rt.fail_event.is_set():
                got = False
                if is_join:
                    for side, q in (("left", in_qs[0]), ("right", in_qs[1])):
                        try:
                            row = q.get(timeout=0.2)
                        except pyqueue.Empty:
                            continue
                        row.pop("_side", None)
                        op.process({**row, "_side": side}, emit)
                        got = True
                else:
                    for q in in_qs:
                        try:
                            row = q.get(timeout=0.05)
                        except pyqueue.Empty:
                            continue
                        row.pop("_side", None)
                        op.process(row, emit)
                        got = True
                if not got:
                    rt.stop_event.wait(0.1)
        except Exception as exc:  # noqa: BLE001
            if not rt.stop_event.is_set():
                rt.set_fail(f"算子 {op.__class__.__name__}: {exc}")
                self._log(rt.job_id, "ERROR", f"算子异常: {exc}")
        finally:
            op.close()

    def _sink_loop(self, rt: JobRuntime, sink, in_qs: list) -> None:
        try:
            while not rt.stop_event.is_set() and not rt.fail_event.is_set():
                batch = []
                try:
                    batch.append(in_qs[0].get(timeout=1.0))
                except (pyqueue.Empty, IndexError):
                    continue
                while len(batch) < 200:
                    try:
                        batch.append(in_qs[0].get_nowait())
                    except pyqueue.Empty:
                        break
                n = sink.write(batch)
                rt.bump_out(n)
        except Exception as exc:  # noqa: BLE001
            if not rt.stop_event.is_set():
                rt.set_fail(f"汇 {sink.__class__.__name__}: {exc}")
                self._log(rt.job_id, "ERROR", f"汇异常: {exc}")
        finally:
            sink.close()

    # ---------- 落库/Redis 助手 ----------

    def _load_offsets(self, job_id: int) -> dict:
        session = new_session()
        try:
            rows = session.query(StreamOffset).filter(StreamOffset.job_id == job_id).all()
            return {r.source_key: (r.offset_json or {}) for r in rows}
        finally:
            session.close()

    def _commit_offsets(self, rt: JobRuntime, force: bool = False) -> None:
        """变更位点落 t_stream_offset（周期批量，避免逐条写库）。

        rt.offsets 仅含本管道源节点键；force=True 收口时最后一次对齐。
        """
        snapshot = rt.offsets_snapshot()
        if not snapshot:
            return
        session = new_session()
        try:
            for key, offset in snapshot.items():
                if not offset:
                    continue
                row = session.get(StreamOffset, (rt.job_id, key))
                if row is None:
                    session.add(StreamOffset(job_id=rt.job_id, source_key=key,
                                             offset_json=offset, updated_at=datetime.now()))
                elif row.offset_json != offset:
                    row.offset_json = offset
                    row.updated_at = datetime.now()
            session.commit()
        except Exception:  # noqa: BLE001 位点提交失败不阻断运行（下轮重试）
            session.rollback()
            self._log(rt.job_id, "WARN", "位点提交失败（下轮重试）")
        finally:
            session.close()

    def _metrics_tick(self, rt: JobRuntime, rate: float) -> None:
        try:
            client = rq.get_client()
            window_op = rt.window_op
            client.hset(METRICS_PREFIX + str(rt.job_id), mapping={
                "status": rt.status,
                "ratePerSec": f"{rate:.1f}",
                "totalIn": str(rt.total_in),
                "totalOut": str(rt.total_out),
                "errors": str(rt.errors),
                "windowEmits": str(window_op.emits if window_op is not None else 0),
                "offsets": json.dumps(rt.offsets_snapshot(), ensure_ascii=False, default=str),
                "lastBeat": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            client.expire(METRICS_PREFIX + str(rt.job_id), 90)
        except Exception as exc:  # noqa: BLE001 指标上报失败不阻断
            logger.warning("流指标上报失败: %r", exc)

    def _db_update(self, job_id: int, generation: Optional[int] = None, **fields) -> None:
        """状态更新；传 generation 时原子代际守卫——代号不匹配（已被重启接管）放弃写入，
        防止旧代号线程退出终态覆盖 API 为新代号预置的 starting（重启竞态 → 认领 0 行 → 任务卡死）。"""
        session = new_session()
        try:
            q = session.query(StreamJob).filter(StreamJob.id == job_id)
            if generation is not None:
                q = q.filter(StreamJob.generation == generation)
            updated = q.update(fields, synchronize_session=False)
            session.commit()
            if generation is not None and not updated:
                logger.warning("状态写入放弃（代际已变化）: job=%s gen=%s fields=%s", job_id, generation, fields)
        except Exception:  # noqa: BLE001
            session.rollback()
        finally:
            session.close()

    def _log(self, job_id: int, level: str, msg: str) -> None:
        line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{level}] {msg}"
        logger.info("flink job=%s %s", job_id, msg)
        try:
            client = rq.get_client()
            client.lpush(LOGS_PREFIX + str(job_id), line)
            client.ltrim(LOGS_PREFIX + str(job_id), 0, 499)
        except Exception:  # noqa: BLE001
            pass

    def _join_job(self, job_id: int) -> None:
        """等待本地任务线程退出（先停再起的确定性收口）。"""
        rt = self._jobs.get(job_id)
        if rt is None:
            return
        deadline = time.time() + 8
        while time.time() < deadline and job_id in self._jobs:
            time.sleep(0.1)
        if job_id in self._jobs:
            logger.warning("流任务旧线程未按时退出: job=%s（后台继续收口）", job_id)


def _put(q: pyqueue.Queue, item, rt: JobRuntime) -> None:
    """带停止检查的阻塞投递（防下游卡死拖垮源线程）。"""
    while not rt.stop_event.is_set() and not rt.fail_event.is_set():
        try:
            q.put(item, timeout=0.5)
            return
        except pyqueue.Full:
            continue
