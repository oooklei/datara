"""流输出汇（I8 F41，C20 四通道，设计 §3.3）。

- API 通道：写 Redis List datara:flink:buf:{job}（Last-N 保留窗口，schema 声明补缺列）；
- 库表通道：按数据源批量 INSERT / upsert（uniqueKey），条数或 1s 定时触发；
- Kafka 通道：KafkaProducer JSON 投递；文件通道：JSONL 追加 + 大小/时间滚动。
- 依赖包缺失/连通失败抛 SinkError，由引擎统一重连。
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import redis

from common.config import get_settings
from common.dsconn import open_connection, resolve_file_path
from common.log import get_logger
from worker.stream.sources import lookup_datasource

logger = get_logger("worker.stream.sinks")

BUF_PREFIX = "datara:flink:buf:"


class SinkError(RuntimeError):
    """汇级可恢复错误（引擎按 reconnecting 处理）。"""


def build_sink(job_id: int, node_id: str, params: dict) -> "SinkBase":
    """分型工厂（C20 四通道）。"""
    params = params or {}
    out_type = str(params.get("outType") or "api")
    if out_type == "api":
        return ApiSink(job_id, params)
    if out_type == "table":
        return TableSink(node_id, params)
    if out_type == "kafka":
        return KafkaSink(params)
    if out_type == "file":
        return FileSink(node_id, params)
    raise SinkError(f"未知流输出通道: {out_type}")


def _kv_rows(params: dict, key: str) -> list:
    rows = params.get(key) or []
    return [(str(r["key"]).strip(), str(r.get("value") or "").strip())
            for r in rows if isinstance(r, dict) and str(r.get("key") or "").strip()]


class SinkBase:
    """流输出汇基类：write(batch) 批量投递；flush/close 生命周期由引擎管。"""

    schema_fields: list = []

    def write(self, rows: list) -> int:  # noqa: ANN001
        raise NotImplementedError

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.flush()


def _apply_schema(data: dict, fields: list) -> dict:
    """schema 声明：按声明列序产出（缺失补 None）；未声明时原样。"""
    if not fields:
        return data
    return {f: data.get(f) for f in fields}


class ApiSink(SinkBase):
    """API 订阅通道（实测门主验）：Redis List Last-N + schema 列。"""

    def __init__(self, job_id: int, params: dict):
        self.job_id = job_id
        self.keep = max(1, int(params.get("keepLast") or 100))
        raw = str(params.get("schemaText") or "")
        self.schema_fields = [f.strip() for f in raw.split(",") if f.strip()]
        self.client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)

    def write(self, rows: list) -> int:
        n = 0
        for row in rows:
            payload = _apply_schema(row.get("data") or {}, self.schema_fields)
            self.client.lpush(BUF_PREFIX + str(self.job_id), json.dumps(payload, ensure_ascii=False, default=str))
            n += 1
        self.client.ltrim(BUF_PREFIX + str(self.job_id), 0, self.keep - 1)
        return n


class TableSink(SinkBase):
    """库表通道：批量 INSERT / upsert（uniqueKey 列命中 ON DUPLICATE KEY UPDATE）。"""

    def __init__(self, node_id: str, params: dict):
        p = params or {}
        self.ds_ref = p.get("outDs")
        self.table = str(p.get("outTable") or "")
        self.field_map = _kv_rows(p, "outFieldMap")   # (目标列, 流字段)
        self.unique_key = str(p.get("uniqueKey") or "").strip()
        self.batch = max(1, int(p.get("outBatchSize") or 500))
        self._buf: list = []
        self._conn = None
        self._last_flush = time.time()
        self._created = False

    def _ensure_conn(self):
        if self._conn is None:
            ds = lookup_datasource(self.ds_ref)
            if ds is None:
                raise SinkError(f"输出数据源不存在: {self.ds_ref}")
            self._conn = open_connection(ds, read_timeout=30)

    def _ensure_table(self, cols: list) -> None:
        if self._created:
            return
        col_sql = ", ".join(f"`{c}` TEXT" for c in cols)
        with self._conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE %s", (self.table,))
            if cur.fetchone() is None:
                cur.execute(f"CREATE TABLE `{self.table}` (id BIGINT AUTO_INCREMENT PRIMARY KEY, {col_sql})")
                self._conn.commit()
                logger.info("流输出建表: %s（cols=%s）", self.table, cols)
        self._created = True

    def write(self, rows: list) -> int:
        self._buf.extend(rows)
        if len(self._buf) >= self.batch or time.time() - self._last_flush >= 1.0:
            self.flush()
        return len(rows)

    def flush(self) -> None:
        if not self._buf:
            return
        rows, self._buf = self._buf, []
        self._ensure_conn()
        data_cols = [d for _, d in self.field_map] if self.field_map else None
        cols = [t for t, _ in self.field_map] if self.field_map else \
            sorted({k for row in rows for k in (row.get("data") or {})})
        self._ensure_table(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        sql = f"INSERT INTO `{self.table}` ({', '.join('`' + c + '`' for c in cols)}) VALUES ({placeholders})"
        if self.unique_key and self.unique_key in cols:
            updates = ", ".join(f"`{c}`=VALUES(`{c}`)" for c in cols if c != self.unique_key)
            if updates:
                sql += f" ON DUPLICATE KEY UPDATE {updates}"
        try:
            with self._conn.cursor() as cur:
                for row in rows:
                    data = row.get("data") or {}
                    cur.execute(sql, [data.get(d) for d in data_cols] if data_cols else
                                [data.get(c) for c in cols])
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self) -> None:
        self.flush()
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class KafkaSink(SinkBase):
    """Kafka topic 通道：kafka-python 生产者 JSON 投递。"""

    def __init__(self, params: dict):
        p = params or {}
        self.brokers = [b.strip() for b in str(p.get("kafkaBrokers") or "").split(",") if b.strip()]
        self.topic = str(p.get("kafkaTopic") or "")
        self.producer = None

    def _ensure_producer(self):
        if self.producer is None:
            try:
                from kafka import KafkaProducer
            except ImportError as exc:
                raise SinkError("kafka-python 未安装（重建镜像后可用）") from exc
            if not self.brokers or not self.topic:
                raise SinkError("Kafka 输出 brokers/topic 未配置")
            self.producer = KafkaProducer(
                bootstrap_servers=self.brokers,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False, default=str).encode("utf-8"),
            )

    def write(self, rows: list) -> int:
        self._ensure_producer()
        for row in rows:
            self.producer.send(self.topic, row.get("data") or {})
        self.producer.flush(timeout=5)
        return len(rows)

    def close(self) -> None:
        if self.producer is not None:
            try:
                self.producer.flush(timeout=5)
                self.producer.close()
            except Exception:  # noqa: BLE001 关闭容错
                pass
            self.producer = None


class FileSink(SinkBase):
    """文件滚动通道：JSONL 追加 + 按大小/时间切分（out.20260919150000.jsonl）。"""

    def __init__(self, node_id: str, params: dict):
        p = params or {}
        self.raw_path = str(p.get("outPath") or "")
        self.roll_by = str(p.get("rollBy") or "size")
        self.size_mb = max(1, int(p.get("rollSizeMb") or 10))
        self.roll_minutes = max(1, int(p.get("rollMinutes") or 60))
        self.path: Optional[Path] = None
        self._fh = None
        self._opened_at = 0.0
        self._written = 0

    def _ensure_open(self) -> None:
        if not self.raw_path:
            raise SinkError("文件输出路径未配置")
        if self._fh is None:
            self.path = resolve_file_path(self.raw_path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.path, "a", encoding="utf-8")  # noqa: SIM115 close 统一管
            self._opened_at = time.time()
            self._written = self.path.stat().st_size if self.path.exists() else 0
            logger.info("文件输出打开: %s → %s", self.raw_path, self.path)
        need_roll = (self.roll_by == "size" and self._written >= self.size_mb * 1024 * 1024) or \
                    (self.roll_by == "time" and time.time() - self._opened_at >= self.roll_minutes * 60)
        if need_roll:
            self._fh.close()
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            rotated = self.path.with_name(f"{self.path.stem}.{stamp}{self.path.suffix}")
            os.replace(self.path, rotated)
            self._fh = open(self.path, "a", encoding="utf-8")
            self._opened_at = time.time()
            self._written = 0
            logger.info("文件滚动切分: → %s", rotated.name)

    def write(self, rows: list) -> int:
        self._ensure_open()
        for row in rows:
            line = json.dumps(row.get("data") or row, ensure_ascii=False, default=str)
            self._fh.write(line + "\n")
            self._written += len(line) + 1
        self._fh.flush()
        return len(rows)

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            except Exception:  # noqa: BLE001 关闭容错
                pass
            self._fh = None
