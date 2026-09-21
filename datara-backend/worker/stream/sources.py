"""流输入源统一接口（I8 F36~F38，设计 §3.2）。

- Source 契约：open(offset) → poll(max_rows) → offset → close()；
- 行事件统一内部格式 {source, ts, data}（ts=事件时间，供窗口/水位线）；
- 连接类故障抛 SourceError，由引擎统一重连（指数退避，连续 10 次失败转 failed）；
- 依赖包（kafka-python / mysql-replication）缺失时在 open() 报可读错误（镜像构建后可用）。
"""

import json
import socket
import time
from typing import Optional

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
    """分型工厂（C18 四源）。"""
    src_type = str((params or {}).get("srcType") or "kafka")
    if src_type == "kafka":
        return KafkaSource(node_id, params)
    if src_type == "cdc":
        return CdcSource(node_id, params)
    if src_type == "http":
        return HttpSource(node_id, params)
    if src_type == "file":
        return FileSource(node_id, params)
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

    def open(self, offset: Optional[dict]) -> None:
        if not self.url:
            raise SourceError("HTTP URL 未配置")
        self._cursor = (offset or {}).get("cursor")
        self._next_poll = 0.0
        logger.info("HTTP 源打开: %s url=%s interval=%ss cursor=%r",
                    self.source_key, self.url, self.interval, self._cursor)

    def poll(self, max_rows: int) -> list:
        if time.time() < self._next_poll:
            return []
        self._next_poll = time.time() + self.interval
        import requests

        try:
            params = {self.cursor_param: self._cursor} if (self.cursor_param and self._cursor is not None) else None
            resp = requests.request(self.method, self.url, headers=self.headers or None, params=params, timeout=10)
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
