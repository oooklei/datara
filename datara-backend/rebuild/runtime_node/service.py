"""Application service for the frozen B6 read-only operations."""

from __future__ import annotations

import stat
from typing import Callable

from sqlalchemy.orm import Session

from rebuild.runtime_node.models import RuntimeNodeRecord

LS_MAX_ENTRIES = 500  # 目录浏览单次返回上限（防止大目录拖垮响应）


class RuntimeNodeDomainError(RuntimeError):
    def __init__(self, code: int, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class RuntimeNodeService:
    def __init__(self, session: Session, sftp_func: Callable[[RuntimeNodeRecord, str], list]) -> None:
        self.session = session
        self.sftp_func = sftp_func

    def list(self) -> list[RuntimeNodeRecord]:
        return (
            self.session.query(RuntimeNodeRecord)
            .order_by(RuntimeNodeRecord.id)
            .all()
        )

    def ls(self, node_id: int, path: str = "") -> dict[str, object]:
        node = self._required(node_id)
        if not str(node.host or "").strip():
            raise RuntimeNodeDomainError(4002, "节点未配置主机地址", 400)
        explicit = str(path or "").strip()
        if explicit and not explicit.startswith("/"):
            raise RuntimeNodeDomainError(4002, "路径必须为绝对路径", 400)
        # 缺省值按 SFTP 家目录语义由远端解析、不做绝对路径校验；显式传入的 path 必须以 / 开头。
        base = explicit or str(node.runtime_dir or "").strip() or "/"
        base = base.rstrip("/") or "/"

        try:
            attrs = self.sftp_func(node, base)
        except FileNotFoundError as exc:
            # R2: 4101/4002/5002 are frozen domain-local literals, never resp.py imports.
            raise RuntimeNodeDomainError(4002, "路径不存在: %s（%s）" % (base, exc), 400) from None
        except Exception as exc:  # noqa: BLE001 连接/认证/列目录失败统一 502
            raise RuntimeNodeDomainError(5002, "SSH 目录浏览失败: %s" % exc, 502) from None

        entries = sorted(
            attrs,
            key=lambda e: (0 if stat.S_ISDIR(e.st_mode or 0) else 1, e.filename),
        )[:LS_MAX_ENTRIES]
        return {
            "path": base,
            "entries": [
                {
                    "name": e.filename,
                    "dir": stat.S_ISDIR(e.st_mode or 0),
                    "size": e.st_size,
                    "mtime": int(e.st_mtime or 0),
                }
                for e in entries
            ],
        }

    def _required(self, node_id: int) -> RuntimeNodeRecord:
        record = self.session.get(RuntimeNodeRecord, node_id)
        if record is None:
            raise RuntimeNodeDomainError(4101, "运行时节点不存在", 404)
        return record
