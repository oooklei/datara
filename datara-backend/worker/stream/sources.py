"""流输入源统一接口（I8 F36~F38，设计 §3.2）。

- Source 契约：open(offset) → poll(max_rows) → offset → close()；
- 行事件统一内部格式 {source, ts, data}（ts=事件时间，供窗口/水位线）；
- 连接类故障抛 SourceError，由引擎统一重连（指数退避，连续 10 次失败转 failed）；
- 依赖包（kafka-python / mysql-replication）缺失时在 open() 报可读错误（镜像构建后可用）；
- 连接性注册化（09-21）：kafka/redis/mqtt/http 四分型支持 dsRef 引用数据源中心注册源
  （连接层=注册源，业务语义=节点参数；无 dsRef 走内联高级模式，存量画布零改动）。
"""

import json
import queue as pyqueue
import random
import socket
import time
from typing import Optional
from urllib.parse import quote as _urlquote

from common.dsconn import resolve_file_path
from common.db import new_session
from common.log import get_logger
from common.models import DataSource

logger = get_logger("worker.stream.sources")

ENCODINGS = ("utf-8", "gbk")


class SourceError(RuntimeError):
    """源级可恢复错误（引擎按 reconnecting 处理）。"""


def lookup_datasource(ref) -> Optional[DataSource]:
    """按名称查 t_data_source，纯数字兜底按 id（与 executors/sql.py 同口径）。"""
    session = new_session()
    try:
        ds = session.query(DataSource).filter(DataSource.name == str(ref or "")).first()
        if ds is None and str(ref or "").isdigit():
            ds = session.get(DataSource, int(ref))
        return ds
    finally:
        session.close()


def resolve_ds_ref(params: dict, expect_types: tuple, what: str) -> Optional[DataSource]:
    """解析节点 dsRef 引用（09-21 连接性注册化）：未配置返回 None；配置了则查存在+类型匹配。"""
    ref = str((params or {}).get("dsRef") or "").strip()
    if not ref:
        return None
    ds = lookup_datasource(ref)
    if ds is None:
        raise SourceError(f"{what} 引用的数据源不存在: {ref}（数据源中心已改名或删除）")
    if ds.type not in expect_types:
        raise SourceError(f"{what} 引用数据源类型不匹配: {ds.name} 为 {ds.type}，需要 {'/'.join(expect_types)}")
    return ds


def _dot_get(payload, path: str):
    """点路径取值（如 data.list）；路径为空返回原值，逐层缺失返回 None。"""
    if not path:
        return payload
    cur = payload
    for part in str(path).split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if 0 <= idx < len(cur) else None
        else:
            return None
    return cur


def _kv_list(p: dict, key: str) -> dict:
    """表单 kv-table（[{key,value}]）→ dict。"""
    rows = p.get(key) or []
    out = {}
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict) and str(r.get("key") or "").strip():
                out[str(r["key"]).strip()] = str(r.get("value") or "")
    return out


class SourceBase:
    """流输入源基类（分型子类实现 open/poll/close）。"""

    def __init__(self, node_id: str, src_type: str, params: dict):
        self.node_id = node_id
        self.src_type = src_type
        self.params = params or {}
        self.source_key = f"{node_id}:{src_type}"

    def open(self, offset: Optional[dict]) -> None:  # noqa: ANN201
        raise NotImplementedError

    def poll(self, max_rows: int) -> list:  # noqa: ANN201
        raise NotImplementedError

    @property
    def offset(self) -> dict:
        """当前位点（引擎周期落 t_stream_offset，重启续跑）。"""
        return {}

    def close(self) -> None:
        pass


def build_source(node_id: str, params: dict) -> SourceBase:
    """分型工厂（C18 七源）。"""
    src_type = str((params or {}).get("srcType") or "kafka")
    if src_type == "kafka":
        return KafkaSource(node_id, params)
    if src_type == "cdc":
        return CdcSource(node_id, params)
    if src_type == "http":
        return HttpSource(node_id, params)
    if src_type == "file":
        return FileSource(node_id, params)
    if src_type == "simulate":
        return SimulateSource(node_id, params)
    if src_type == "redis":
        return RedisStreamSource(node_id, params)
    if src_type == "mqtt":
        return MqttSource(node_id, params)
    raise SourceError(f"未知流输入分型: {src_type}")


# ---------- C18 分型一：Kafka（F36） ----------

class KafkaSource(SourceBase):
    """kafka-python 消费者：组消费 + 指定位点 seek（auto_commit 关闭，处理成功后引擎提交 t_stream_offset）。"""

    def __init__(self, node_id: str, params: dict):
        super().__init__(node_id, "kafka", params)
        p = self.params
        self.brokers = [b.strip() for b in str(p.get("brokers") or "").split(",") if b.strip()]
        self.topic = str(p.get("topic") or "")
        self.group = str(p.get("group") or "datara-flink")
        self.start_from = str(p.get("startFrom") or "earliest")
        self.fmt = str(p.get("format") or "json")
        self.delim = str(p.get("delimiter") or ",")
        self.consumer = None
        self._offsets: dict[str, int] = {}  # {topic:partition: 下一条 offset}
        self._saved: dict[str, int] = {}  # open 注入的 t_stream_offset 位点（poll 分配就绪后 seek）
        self._seeked = False  # 本次 open 后是否已恢复位点（组分配就绪前不消费）
        self._bad = 0
        self._idle = 0
        self._resolved_ip: Optional[str] = None  # open 成功时缓存的 broker IP（DNS 抖动时探测兜底）
        # 连接性注册化（09-21）：dsRef 引用注册源时 brokers 一律来自注册层（连接层归一）
        ds = resolve_ds_ref(p, ("kafka",), "Kafka")
        if ds is not None:
            self.brokers = [b.strip() for b in str((ds.params or {}).get("brokers") or "").split(",") if b.strip()]
            if not self.brokers:
                raise SourceError(f"Kafka 数据源 {ds.name} 未配置 brokers，请先在数据源中心补全并测试")

    def open(self, offset: Optional[dict]) -> None:
        if not self.brokers or not self.topic:
            raise SourceError("Kafka brokers/topic 未配置")
        try:
            from kafka import KafkaConsumer
        except ImportError as exc:  # 镜像未装依赖给可读错误
            raise SourceError("kafka-python 未安装（重建 backend/worker 镜像后可用）") from exc
        self.consumer = KafkaConsumer(
            self.topic,
            bootstrap_servers=self.brokers,
            group_id=self.group,
            auto_offset_reset="earliest" if self.start_from == "earliest" else "latest",
            enable_auto_commit=False,
            consumer_timeout_ms=500,
        )
        # I9 修复 I8 seek 时机 bug：不再 open 后立即 poll+seek（组 join/assignment 未就绪时
        # seek 被跳过 → 重启按 auto_offset_reset 整题重放）。位点暂存 _saved，由 poll 在
        # assignment 就绪后 seek（见 poll 门控）。
        self._saved = {k: int(v) for k, v in ((offset or {}).get("partitions") or {}).items()}
        self._seeked = False
        logger.info("Kafka 源打开: %s topic=%s group=%s saved=%s",
                    self.source_key, self.topic, self.group, bool(self._saved))
        try:  # 缓存 broker IP：docker stop/start 后 embedded DNS 别名恢复有延迟，探测时兜底直连
            self._resolved_ip = socket.gethostbyname(self.brokers[0].split(":")[0])
        except OSError:
            pass

    def _tcp_ok(self, host: str, port: int) -> bool:
        # 超时 10s：KRaft 半就绪窗口 9092 SYN 排队 accept 抖动，宽超时能过而短超时必超时（门5 恢复期误判教训）；
        # 真断流是 refused/gaierror 秒失败，感知不受影响
        try:
            socket.create_connection((host, port), timeout=10.0).close()
            return True
        except OSError as exc:
            logger.warning("Kafka 探测失败: %s:%s → %s: %s", host, port, type(exc).__name__, exc)
            return False

    def _brokers_alive(self) -> bool:
        """TCP 层探测任一 broker 可达（kafka-python 掉线静默空转，需应用层显式探测）。

        两轮重试 + 3s 超时；主机名解析失败（docker stop 后别名移除/恢复延迟）时
        用 open 成功时缓存的 IP 或重新解析结果直连兜底，避免 DNS 抖动误报。
        """
        for _ in range(2):
            for b in self.brokers:
                host, _, port = b.partition(":")
                port = int(port or 9092)
                if self._tcp_ok(host, port):
                    return True
                try:
                    ip = socket.gethostbyname(host)
                except OSError:
                    ip = ""
                self._resolved_ip = ip or self._resolved_ip
                if self._resolved_ip and self._tcp_ok(self._resolved_ip, port):
                    return True
            time.sleep(0.5)
        return False

    def _idle_probe(self) -> None:
        """空闲 ~25 次后做一次 TCP 探测（给组 join 分配留时间）：broker 全挂时抛错触发引擎重连。"""
        self._idle += 1
        if self._idle >= 25:
            self._idle = 0
            if not self._brokers_alive():
                logger.error("Kafka 探测判定不可达: brokers=%r", self.brokers)
                raise SourceError("Kafka broker 不可达（TCP 探测全部失败）")

    def poll(self, max_rows: int) -> list:
        # 位点恢复门控（I9 修复 I8 seek 时机 bug）：有续跑位点且尚未 seek 时，等组分配就绪再消费
        if self._saved and not self._seeked:
            assigned = self.consumer.assignment()
            if assigned:
                restored = 0
                for tp in assigned:
                    key = f"{tp.topic}:{tp.partition}"
                    if key in self._saved:
                        self.consumer.seek(tp, int(self._saved[key]))
                        restored += 1
                self._seeked = True
                logger.info("Kafka 位点恢复: %s assigned=%d 恢复=%d", self.source_key, len(assigned), restored)
            else:
                # 分配未就绪：仅推进组协调，不消费——即便本轮恰好完成分配预取到 auto_reset 位点
                # 记录，也不计入 _offsets，seek 后会重新拉取（不丢不重）。
                self.consumer.poll(timeout_ms=200, max_records=1)
                self._idle_probe()
                return []
        batches = self.consumer.poll(timeout_ms=500, max_records=max_rows)
        if not batches:
            self._idle_probe()
        else:
            self._idle = 0
        rows = []
        for tp, records in batches.items():
            key = f"{tp.topic}:{tp.partition}"
            for rec in records:
                self._offsets[key] = rec.offset + 1  # 已消费到 offset，下一条从 +1 起
                data = self._decode(rec.value)
                if data is None:
                    continue
                rows.append({"source": self.source_key, "ts": (rec.timestamp or 0) / 1000 or time.time(), "data": data})
        return rows

    def _decode(self, raw) -> Optional[dict]:  # noqa: ANN001
        try:
            if isinstance(raw, bytes):
                text = raw.decode("utf-8", errors="replace")
            else:
                text = str(raw)
            if self.fmt == "csv":
                parts = text.split(self.delim)
                return {f"c_{i + 1}": v for i, v in enumerate(parts)}
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else {"value": obj}
        except (ValueError, UnicodeDecodeError):
            self._bad += 1
            if self._bad % 100 == 1:
                logger.warning("Kafka 消息解析失败（%s）: %.120r", self.source_key, raw)
            return None

    @property
    def offset(self) -> dict:
        return {"partitions": dict(self._offsets)}

    def close(self) -> None:
        if self.consumer is not None:
            try:
                self.consumer.close()
            except Exception:  # noqa: BLE001 关闭容错
                pass
            self.consumer = None


# ---------- C18 分型二：CDC binlog（F37） ----------

class CdcSource(SourceBase):
    """mysql-replication BinLogStreamReader：库表白名单 + file:pos 位点（at-least-once）。"""

    def __init__(self, node_id: str, params: dict):
        super().__init__(node_id, "cdc", params)
        p = self.params
        self.ds_ref = p.get("cdcDs")
        self.schemas = [s.strip() for s in str(p.get("schemasText") or "").split(",") if s.strip()]
        self.tables = [t.strip() for t in str(p.get("tablesText") or "").split(",") if t.strip()]
        self.pos_mode = str(p.get("posMode") or "latest")
        self.pos_file = str(p.get("posFile") or "") or None
        self.pos_pos = int(p.get("posPos") or 0) or None
        self._stream = None
        self._conn_cfg: Optional[dict] = None

    def _resolve_conn(self) -> dict:
        ds = lookup_datasource(self.ds_ref)
        if ds is None:
            raise SourceError(f"CDC 数据源不存在: {self.ds_ref}")
        if ds.type not in ("mysql", "greatdb"):
            raise SourceError(f"CDC 数据源类型须为 mysql/greatdb: {ds.type}")
        return {
            "host": ds.host or "127.0.0.1",
            "port": int(ds.port) if ds.port else (3316 if ds.type == "greatdb" else 3306),
            "user": ds.user or "root",
            "passwd": ds.pwd or "",
        }

    def open(self, offset: Optional[dict]) -> None:
        try:
            from pymysqlreplication import BinLogStreamReader
            from pymysqlreplication.row_event import DeleteRowsEvent, UpdateRowsEvent, WriteRowsEvent
        except ImportError as exc:
            raise SourceError("mysql-replication 未安装（重建镜像后可用）") from exc
        self._conn_cfg = self._resolve_conn()
        off = offset or {}
        # 位点优先级：t_stream_offset > 表单 custom > 表单 latest（resume_stream）/ earliest
        log_file = off.get("log_file") or (self.pos_file if self.pos_mode == "custom" else None)
        log_pos = off.get("log_pos") or (self.pos_pos if self.pos_mode == "custom" else None)
        resume = self.pos_mode != "earliest" or bool(log_file)
        import random

        self._stream = BinLogStreamReader(
            connection_settings=self._conn_cfg,
            server_id=random.randint(60001, 94999),  # 每次打开唯一（避免复制通道冲突）
            only_schemas=self.schemas or None,
            only_tables=self.tables or None,
            only_events=[WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent],
            resume_stream=resume,
            blocking=False,
            log_file=log_file,
            log_pos=log_pos,
        )
        logger.info("CDC 源打开: %s ds=%s schemas=%s tables=%s offset=%s",
                    self.source_key, self.ds_ref, self.schemas or "*", self.tables or "*", (log_file, log_pos))

    def poll(self, max_rows: int) -> list:
        rows = []
        while len(rows) < max_rows:
            event = self._stream.fetchone()
            if event is None:
                break
            schema = getattr(event, "schema", "") or ""
            table = getattr(event, "table", "") or ""
            ts = float(getattr(event, "timestamp", 0) or 0) or time.time()
            for r in getattr(event, "rows", []) or []:
                if "after_values" in r:  # Update
                    op, data = "update", r["after_values"]
                    before = r.get("before_values")
                elif "values" in r:  # Write / Delete
                    op = "delete" if event.__class__.__name__.startswith("Delete") else "insert"
                    data, before = r["values"], None
                else:
                    continue
                row = {"source": self.source_key, "ts": ts,
                       "data": {"op": op, "schema": schema, "table": table, "row": data}}
                if before is not None:
                    row["data"]["before"] = before
                rows.append(row)
        return rows

    @property
    def offset(self) -> dict:
        if self._stream is None:
            return {}
        return {"log_file": self._stream.log_file, "log_pos": self._stream.log_pos}

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:  # noqa: BLE001 关闭容错
                pass
            self._stream = None


# ---------- C18 分型三：HTTP 拉取（F38） ----------

class HttpSource(SourceBase):
    """requests 周期轮询：数据点路径提取数组 + 游标参数（响应序号/分页 token）。"""

    def __init__(self, node_id: str, params: dict):
        super().__init__(node_id, "http", params)
        p = self.params
        self.url = str(p.get("httpUrl") or "")
        self.method = str(p.get("httpMethod") or "GET").upper()
        self.interval = max(1, int(p.get("intervalSec") or 10))
        self.headers = _kv_list(p, "headers")
        self.data_path = str(p.get("dataPath") or "")
        self.cursor_param = str(p.get("cursorParam") or "")
        self.cursor_path = str(p.get("cursorPath") or "")
        self._cursor = None
        self._next_poll = 0.0
        # 连接性注册化（09-21）：dsRef 时注册层供 baseUrl+基础鉴权头，节点配业务路径/头（覆盖注册头）
        ds = resolve_ds_ref(p, ("http",), "HTTP")
        self._reg_base = ""
        self._reg_headers: dict = {}
        if ds is not None:
            self._reg_base = str((ds.params or {}).get("baseUrl") or "").strip()
            if not self._reg_base.lower().startswith(("http://", "https://")):
                raise SourceError(f"HTTP 数据源 {ds.name} baseUrl 非法（需 http(s):// 开头）")
            raw_h = (ds.params or {}).get("headers") or {}
            if isinstance(raw_h, dict):
                self._reg_headers = {str(k): str(v) for k, v in raw_h.items() if str(k).strip()}

    def _effective_url(self) -> str:
        """dsRef 模式 URL 拼接：节点 httpUrl 空=直打 baseUrl；相对路径=base+path；完整 URL=节点优先（高级覆盖）。"""
        if not self._reg_base:
            return self.url
        u = self.url.strip()
        if not u or u.lower().startswith(("http://", "https://")):
            return u or self._reg_base
        return self._reg_base.rstrip("/") + "/" + u.lstrip("/")

    def open(self, offset: Optional[dict]) -> None:
        if not self._effective_url():
            raise SourceError("HTTP URL 未配置（或引用数据源 baseUrl 为空）")
        self._cursor = (offset or {}).get("cursor")
        self._next_poll = 0.0
        logger.info("HTTP 源打开: %s url=%s interval=%ss cursor=%r",
                    self.source_key, self._effective_url(), self.interval, self._cursor)

    def poll(self, max_rows: int) -> list:
        if time.time() < self._next_poll:
            return []
        self._next_poll = time.time() + self.interval
        import requests

        try:
            params = {self.cursor_param: self._cursor} if (self.cursor_param and self._cursor is not None) else None
            merged = {**self._reg_headers, **self.headers}  # 注册层基础头 + 节点业务头（同名覆盖）
            resp = requests.request(self.method, self._effective_url(), headers=merged or None,
                                    params=params, timeout=10)
        except requests.RequestException as exc:
            raise SourceError(f"HTTP 请求失败: {exc}") from exc
        if resp.status_code >= 400:
            raise SourceError(f"HTTP {resp.status_code}: {resp.text[:120]}")
        try:
            payload = resp.json()
        except ValueError:
            payload = {"value": resp.text}
        items = _dot_get(payload, self.data_path)
        if items is None:
            items = []
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            items = [{"value": items}]
        rows = []
        now = time.time()
        for item in items[:max_rows]:
            data = item if isinstance(item, dict) else {"value": item}
            rows.append({"source": self.source_key, "ts": now, "data": data})
        if self.cursor_path:
            cur = _dot_get(payload, self.cursor_path)
            if cur is not None:
                self._cursor = cur
        return rows

    @property
    def offset(self) -> dict:
        return {"cursor": self._cursor}


# ---------- C18 分型四：文件尾随（F38） ----------

class FileSource(SourceBase):
    """逐行尾随 + inode 滚动跟随（滚动重开从头）；位点=字节偏移+inode+表头缓存。"""

    CHUNK = 65536

    def __init__(self, node_id: str, params: dict):
        super().__init__(node_id, "file", params)
        p = self.params
        self.raw_path = str(p.get("filePath") or "")
        self.encoding = str(p.get("fileEncoding") or "utf-8")
        if self.encoding not in ENCODINGS:
            self.encoding = "utf-8"
        self.delim = str(p.get("fileDelimiter") or "")
        self.use_header = bool(p.get("fileHeader", True))
        self._fh = None
        self._inode: Optional[int] = None
        self._pos = 0
        self._buf = b""          # 未凑整行残余
        self._headers: Optional[list] = None

    def open(self, offset: Optional[dict]) -> None:
        if not self.raw_path:
            raise SourceError("文件路径未配置")
        self.path = resolve_file_path(self.raw_path)
        off = offset or {}
        saved_inode = off.get("inode")
        if saved_inode is not None and self.path.exists() and self.path.stat().st_ino == saved_inode:
            self._pos = int(off.get("pos") or 0)
            self._headers = off.get("header_names")
        else:
            self._pos, self._headers = 0, None  # 新文件/滚动后从头
        self._inode = self.path.stat().st_ino if self.path.exists() else None
        self._fh = None
        logger.info("文件源打开: %s path=%s pos=%d inode=%s", self.source_key, self.path, self._pos, self._inode)

    def _reopen_if_rotated(self) -> None:
        cur = self.path.stat().st_ino if self.path.exists() else None
        if cur != self._inode:
            if self._fh is not None:
                self._fh.close()
                self._fh = None
            self._inode = cur
            self._pos, self._buf, self._headers = 0, b"", None
            logger.info("文件滚动跟随: %s 重开（inode %s → %s）", self.source_key, self._inode, cur)

    def poll(self, max_rows: int) -> list:
        if not self.path.exists():
            return []
        self._reopen_if_rotated()
        if self._fh is None:
            self._fh = open(self.path, "rb")  # noqa: SIM115 生命周期由 close 统一管
            self._fh.seek(self._pos)
        chunk = self._fh.read(self.CHUNK)
        if not chunk:
            return []
        self._buf += chunk
        lines = self._buf.split(b"\n")
        self._buf = lines.pop()  # 最后一段可能是半行，留到下轮
        rows = []
        now = time.time()
        for raw in lines:
            if self._pos == 0 and self.use_header and self._headers is None:
                first = raw.decode(self.encoding, errors="replace").rstrip("\r")
                self._headers = [h.strip() for h in first.split(self.delim)] if self.delim else [first]
                self._pos += len(raw) + 1
                continue
            text = raw.decode(self.encoding, errors="replace").rstrip("\r")
            self._pos += len(raw) + 1
            if self.delim:
                parts = text.split(self.delim)
                data = dict(zip(self._headers, parts)) if self._headers \
                    else {f"c_{i + 1}": v for i, v in enumerate(parts)}
            else:
                data = {"line": text}
            rows.append({"source": self.source_key, "ts": now, "data": data})
            if len(rows) >= max_rows:
                break
        return rows

    @property
    def offset(self) -> dict:
        return {"pos": self._pos, "inode": self._inode, "header_names": self._headers}

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:  # noqa: BLE001 关闭容错
                pass
            self._fh = None


# ---------- C18 分型五：内置模拟流（对齐 stream-realtime-demos 默认模式，零外部依赖） ----------

SIM_GOODS = ["SKU_1001", "SKU_1002", "SKU_1003", "SKU_1004", "SKU_1005"]
SIM_USERS = [f"u_{i:04d}" for i in range(200)]
SIM_DEVICES = [f"dev_{i:03d}" for i in range(10)]
SIM_PAGES = ["/home", "/list", "/detail", "/cart", "/pay", "/order"]


class SimulateSource(SourceBase):
    """内置模拟流源：ecommerce（订单/点击/加购）/ iot（温压振/告警）/ visit（订单/访问）三数据集。

    - 事件 schema 与 stream-realtime-demos 三个 use_case 逐一对应，data 内含 event 字段标记事件名
      （供 filter 条件如 event == 'cart_event'）；
    - simEvents 过滤本源只产生指定事件（逗号分隔，空 = 全部），供多源分路；
    - simEps 控制每秒事件数（poll 每 200ms 被引擎调一次，按速率摊派）。
    """

    def __init__(self, node_id: str, params: dict):
        super().__init__(node_id, "simulate", params)
        p = self.params
        self.dataset = str(p.get("simDataset") or "ecommerce")
        raw = str(p.get("simEvents") or "").strip()
        self.events = {e.strip() for e in raw.split(",") if e.strip()} or None
        try:
            self.eps = min(200.0, max(0.5, float(p.get("simEps") or 5)))
        except (TypeError, ValueError):
            self.eps = 5.0
        self._quota = 0.0

    def open(self, offset: Optional[dict]) -> None:
        self._quota = 0.0
        logger.info("模拟源打开: %s dataset=%s events=%s eps=%s",
                    self.source_key, self.dataset, sorted(self.events) if self.events else "*", self.eps)

    def _emit_ok(self, name: str) -> bool:
        return self.events is None or name in self.events

    def _gen(self) -> Optional[tuple[str, dict]]:
        """产出一个 (事件名, data)；不在过滤集时跳过重抽（最多 8 次防死循环）。"""
        now = time.time()
        for _ in range(8):
            if self.dataset == "iot":
                name, data = self._gen_iot(now)
            elif self.dataset == "visit":
                name, data = self._gen_visit(now)
            else:
                name, data = self._gen_ecommerce(now)
            if self._emit_ok(name):
                data["event"] = name
                return name, data
        return None

    def _gen_ecommerce(self, now: float) -> tuple[str, dict]:
        r = random.random()
        if r < 0.2:  # 订单（demo 比例 1:3:1）
            return "order_pay", {
                "order_id": f"ord_{random.randrange(10 ** 8):08d}",
                "user_id": random.choice(SIM_USERS),
                "goods_id": random.choice(SIM_GOODS),
                "amount": round(random.uniform(9.9, 999.0), 2),
                "ts": now,
            }
        if r < 0.8:
            return "user_click", {
                "user_id": random.choice(SIM_USERS),
                "goods_id": random.choice(SIM_GOODS),
                "ts": now,
            }
        return "cart_event", {
            "user_id": random.choice(SIM_USERS),
            "goods_id": random.choice(SIM_GOODS),
            "action": random.choice(["add", "add", "remove"]),
            "ts": now,
        }

    def _gen_iot(self, now: float) -> tuple[str, dict]:
        dev = random.choice(SIM_DEVICES)
        r = random.random()
        if r < 0.32:
            return "temp", {"device": dev, "value": round(random.gauss(45, 5), 2), "ts": now}
        if r < 0.64:
            return "press", {"device": dev, "value": round(random.gauss(3.5, 0.5), 3), "ts": now}
        if r < 0.98:
            return "vib", {"device": dev, "value": round(abs(random.gauss(0, 2)), 3), "ts": now}
        kind = random.choice(["OVERHEAT", "PRESSURE_HIGH", "VIBRATION_HIGH"])
        return "alert", {"device": dev, "type": kind, "ts": now}

    def _gen_visit(self, now: float) -> tuple[str, dict]:
        if random.random() < 0.2:
            return "order", {
                "order_id": f"o_{random.randrange(10 ** 8):08d}",
                "user_id": random.choice(SIM_USERS),
                "amount": round(random.uniform(20, 800), 2),
                "ts": now,
            }
        return "visit", {
            "user_id": random.choice(SIM_USERS),
            "page": random.choice(SIM_PAGES),
            "ts": now,
        }

    def poll(self, max_rows: int) -> list:
        # 速率摊派：每轮 (eps * poll周期) 个事件配额，空闲期结余累加（突发上限单轮 max_rows）
        now = time.time()
        self._quota = min(self._quota + self.eps * 0.2, max_rows * 2.0)
        rows: list = []
        while len(rows) < max_rows and self._quota >= 1.0:
            item = self._gen()
            if item is None:
                break
            _, data = item
            self._quota -= 1.0
            rows.append({"source": self.source_key, "ts": float(data.get("ts") or now), "data": data})
        return rows

    @property
    def offset(self) -> dict:
        return {"quota": round(self._quota, 1)}


# ---------- C18 分型六：Redis Stream（XREADGROUP 消费组，位点由 group 天然续跑） ----------

class RedisStreamSource(SourceBase):
    """Redis Stream 消费源：直连 URL（redis://host:port/db），consumer group 消费。

    - 位点：XREADGROUP '>' 由 Redis group last-delivered-id 维护，重启重连自动续跑，
      t_stream_offset 仅存 stream/group 映射做装配核对；
    - 消息体兼容两种形态：field 'data' = JSON 串（demo 灌数形态）或整 fields 即数据。
    """

    def __init__(self, node_id: str, params: dict):
        super().__init__(node_id, "redis", params)
        p = self.params
        self.redis_url = str(p.get("redisUrl") or "").strip()
        self.streams = [s.strip() for s in str(p.get("streamsText") or "").split(",") if s.strip()]
        self.group = str(p.get("redisGroup") or "datara-flink")
        self.consumer = str(p.get("redisConsumer") or "c1")
        self._r = None
        # 连接性注册化（09-21）：dsRef 时由注册层 host/port/pwd/params.db 组装 URL（业务 Stream 键仍在节点）
        ds = resolve_ds_ref(p, ("redis",), "Redis")
        if ds is not None:
            if not (ds.host or "").strip() or not ds.port:
                raise SourceError(f"Redis 数据源 {ds.name} host/port 未配置，请先在数据源中心补全并测试")
            pwd_part = f":{_urlquote(ds.pwd, safe='')}@" if ds.pwd else ""
            self.redis_url = f"redis://{pwd_part}{ds.host}:{ds.port}/{int((ds.params or {}).get('db') or 0)}"

    def open(self, offset: Optional[dict]) -> None:
        if not self.redis_url or not self.streams:
            raise SourceError("Redis URL / Stream 键未配置")
        try:
            import redis.asyncio  # noqa: F401 确认 redis 包可用（同步客户端足够）
            import redis as redis_sync
        except ImportError as exc:
            raise SourceError("redis 包未安装（重建镜像后可用）") from exc
        self._r = redis_sync.Redis.from_url(self.redis_url, decode_responses=True, socket_timeout=2)
        try:
            self._r.ping()
        except Exception as exc:
            self._r = None
            raise SourceError(f"Redis 连接失败: {exc}") from exc
        for s in self.streams:
            try:
                self._r.xgroup_create(s, self.group, id="$", mkstream=True)
            except Exception as exc:  # noqa: BLE001 BUSYGROUP = 已存在（续跑）
                if "BUSYGROUP" not in str(exc):
                    logger.warning("Redis 消费组创建异常: %s/%s %r", s, self.group, exc)
        logger.info("Redis Stream 源打开: %s url=%s streams=%s group=%s",
                    self.source_key, self.redis_url, self.streams, self.group)

    def poll(self, max_rows: int) -> list:
        if self._r is None:
            return []
        resp = self._r.xreadgroup(
            self.group, self.consumer,
            streams={s: ">" for s in self.streams},
            count=max_rows, block=400,
        )
        rows = []
        now = time.time()
        for stream_name, messages in resp or []:
            sname = stream_name if isinstance(stream_name, str) else stream_name.decode()
            for _msg_id, fields in messages:
                data = self._decode(fields)
                if data is None:
                    continue
                ts = float(data.pop("ts", None) or now)
                rows.append({"source": f"{self.source_key}:{sname}", "ts": ts, "data": data})
        return rows

    def _decode(self, fields: dict) -> Optional[dict]:
        try:
            if isinstance(fields, dict):
                raw = fields.get("data")
                if raw is not None:
                    obj = json.loads(raw if isinstance(raw, str) else str(raw))
                    return obj if isinstance(obj, dict) else {"value": obj}
                return {k: v for k, v in fields.items()}
        except (ValueError, TypeError):
            return None
        return None

    @property
    def offset(self) -> dict:
        return {"streams": list(self.streams), "group": self.group}

    def close(self) -> None:
        if self._r is not None:
            try:
                self._r.close()
            except Exception:  # noqa: BLE001
                pass
            self._r = None


# ---------- C18 分型七：MQTT 订阅（paho-mqtt，回调线程 → 队列桥接） ----------

class MqttSource(SourceBase):
    """MQTT 订阅源：paho-mqtt 回调线程收包入队，poll 线程出队（无位点，QoS0 至少送达）。"""

    def __init__(self, node_id: str, params: dict):
        super().__init__(node_id, "mqtt", params)
        p = self.params
        self.host = str(p.get("mqttHost") or "").strip()
        self.port = int(p.get("mqttPort") or 1883)
        self.topics = [t.strip() for t in str(p.get("mqttTopics") or "").split(",") if t.strip()]
        self._queue: pyqueue.Queue = pyqueue.Queue(maxsize=10000)
        self._client = None
        self._reg_user = ""
        self._reg_pwd = ""
        # 连接性注册化（09-21）：dsRef 时 host/port/认证来自注册层（订阅 Topic 仍在节点）
        ds = resolve_ds_ref(p, ("mqtt",), "MQTT")
        if ds is not None:
            if not (ds.host or "").strip() or not ds.port:
                raise SourceError(f"MQTT 数据源 {ds.name} host/port 未配置，请先在数据源中心补全并测试")
            self.host = ds.host
            self.port = int(ds.port)
            self._reg_user = ds.user or ""
            self._reg_pwd = ds.pwd or ""

    def open(self, offset: Optional[dict]) -> None:
        if not self.host or not self.topics:
            raise SourceError("MQTT host/topics 未配置")
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise SourceError("paho-mqtt 未安装（重建镜像后可用）") from exc
        q = self._queue

        def _on_message(_c, _u, msg) -> None:  # noqa: ANN001 paho 回调
            try:
                data = json.loads(msg.payload.decode())
            except (ValueError, UnicodeDecodeError):
                data = {"value": msg.payload.decode("utf-8", errors="replace")}
            try:
                q.put_nowait((msg.topic, data))
            except pyqueue.Full:
                pass  # 背压：队满丢新包（QoS0 语义）

        try:
            self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self._client.on_message = _on_message
            if self._reg_user or self._reg_pwd:
                self._client.username_pw_set(self._reg_user, self._reg_pwd)
            self._client.connect(self.host, self.port, keepalive=60)
            for t in self.topics:
                self._client.subscribe(t, qos=0)
            self._client.loop_start()
        except Exception as exc:
            self._client = None
            raise SourceError(f"MQTT 连接失败: {exc}") from exc
        logger.info("MQTT 源打开: %s %s:%s topics=%s", self.source_key, self.host, self.port, self.topics)

    def poll(self, max_rows: int) -> list:
        rows = []
        now = time.time()
        while len(rows) < max_rows:
            try:
                topic, data = self._queue.get(timeout=0.2)
            except pyqueue.Empty:
                break
            ts = float(data.pop("ts", None) or now)
            rows.append({"source": f"{self.source_key}:{topic}", "ts": ts, "data": data})
        return rows

    @property
    def offset(self) -> dict:
        return {"topics": list(self.topics)}

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
