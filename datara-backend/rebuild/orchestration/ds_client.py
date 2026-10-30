"""DolphinScheduler 编排后端 HTTP 客户端（走内部信任通道，不持有海豚会话）。

海豚侧已改造 ``LoginHandlerInterceptor``：携带 ``X-Datara-Internal-Token`` +
``X-Datara-User`` 时跳过登录态校验，因此本客户端不需要账号密码，也不需要
维护 ``sessionId``。

除项目幂等外，客户端只暴露一个通用 ``call(method, path, query=, form=)``：
编排网关（§10.10 部署运维 / §10.11 监控中心）按海豚 Controller 的路径与参数
形态直传，客户端不内置业务语义。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DS_BASE_URL = "http://192.168.1.9:12345/dolphinscheduler"
DEFAULT_DS_ADMIN_USER = "admin"
DS_TIMEOUT_SECONDS = 10.0

INTERNAL_TOKEN_HEADER = "X-Datara-Internal-Token"
INTERNAL_USER_HEADER = "X-Datara-User"

# (method, url, body_bytes, headers) -> parsed JSON object. 生产用 urllib，测试注入假传输。
Transport = Any


class DsClientError(RuntimeError):
    """海豚调用失败，携带稳定诊断码供上游直接透出。"""

    def __init__(self, code: str, msg: str, status: int = 502) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.status = status

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "msg": self.msg, "data": None}


class DsClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        internal_token: str | None = None,
        admin_user: str | None = None,
        timeout: float = DS_TIMEOUT_SECONDS,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("DATARA_DS_BASE_URL") or DEFAULT_DS_BASE_URL).rstrip("/")
        self.internal_token = (
            internal_token if internal_token is not None else os.getenv("DATARA_INTERNAL_TOKEN", "")
        ).strip()
        self.admin_user = (
            admin_user if admin_user is not None else os.getenv("DATARA_DS_ADMIN_USER", DEFAULT_DS_ADMIN_USER)
        ).strip() or DEFAULT_DS_ADMIN_USER
        self.timeout = timeout
        self._transport = transport

    # -- projects -----------------------------------------------------------

    def list_projects(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/projects/list")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def create_project(self, name: str, description: str = "") -> dict[str, Any]:
        data = self._request("POST", "/projects", query={"projectName": name, "description": description or ""})
        if not isinstance(data, dict):
            raise DsClientError("DS_PROJECT_CREATE_INVALID", "dolphinscheduler returned an unexpected project payload")
        return data

    def ensure_project(self, name: str, description: str = "") -> dict[str, Any]:
        """按名称幂等确保海豚项目存在，返回含 ``code`` 的项目对象。"""
        for project in self.list_projects():
            if str(project.get("name", "")) == name:
                return project
        try:
            return self.create_project(name, description)
        except DsClientError as exc:
            # 并发创建时海豚会回「项目已存在」，重查一次即可。
            if exc.code != "DS_API_ERROR":
                raise
            for project in self.list_projects():
                if str(project.get("name", "")) == name:
                    return project
            raise

    # -- 通用代理（§10.10 部署运维 / §10.11 监控中心） --------------------------
    #
    # 海豚 Controller 多为 ``@RequestParam`` 形式，故入参统一走表单编码；
    # 路径与查询串由调用方（编排网关）显式给出，客户端不做业务语义推断。

    def call(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> Any:
        return self._request(method, path, query=query, form=form, files=files)

    def download(self, path: str, *, query: dict[str, Any] | None = None) -> tuple[bytes, str]:
        """取海豚二进制响应（资源文件下载）；返回 ``(正文字节, Content-Type)``。

        海豚 ``ResourcesController.downloadResource`` 直接写 ``HttpServletResponse``，
        失败时才回 ``Result`` 信封，故此处不做 JSON 解包。
        """
        url = self.base_url + path
        if query:
            url += f"?{urllib.parse.urlencode(query)}"
        headers = {
            "Accept": "*/*",
            INTERNAL_TOKEN_HEADER: self.internal_token,
            INTERNAL_USER_HEADER: self.admin_user,
        }
        if self._transport is not None:
            return self._transport("GET", url, None, headers), "application/octet-stream"
        if not self.internal_token:
            raise DsClientError(
                "DS_INTERNAL_TOKEN_MISSING",
                "DATARA_INTERNAL_TOKEN is not configured; cannot call dolphinscheduler",
                503,
            )
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read(), response.headers.get("Content-Type", "application/octet-stream")
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:512]
            except Exception:  # noqa: BLE001 - 诊断信息尽力而为
                body = ""
            logger.warning(
                "ds_download_http_error path=%s status=%s body=%s", path, exc.code, body
            )
            raise DsClientError(
                "DS_UNREACHABLE", f"dolphinscheduler responded {exc.code} for GET {path}", 502
            ) from exc
        except Exception as exc:  # noqa: BLE001 - 网络失败统一收敛为 502
            logger.warning("ds_download_failed path=%s error=%s", path, type(exc).__name__)
            raise DsClientError(
                "DS_UNREACHABLE", f"cannot reach dolphinscheduler: {type(exc).__name__}", 502
            ) from exc

    # -- transport ----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> Any:
        url = self.base_url + path
        if query:
            url += f"?{urllib.parse.urlencode(query)}"
        headers = {"Accept": "application/json", INTERNAL_TOKEN_HEADER: self.internal_token, INTERNAL_USER_HEADER: self.admin_user}
        data: bytes | None = None
        if files:
            data, content_type = _encode_multipart(form or {}, files)
            headers["Content-Type"] = content_type
        elif form:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = urllib.parse.urlencode(form).encode("utf-8")
        if self._transport is not None:
            payload = self._transport(method, url, data, headers)
        else:
            if not self.internal_token:
                raise DsClientError(
                    "DS_INTERNAL_TOKEN_MISSING",
                    "DATARA_INTERNAL_TOKEN is not configured; cannot call dolphinscheduler",
                    503,
                )
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", "replace")[:512]
                except Exception:  # noqa: BLE001 - 诊断信息尽力而为
                    body = ""
                logger.warning(
                    "ds_request_http_error method=%s path=%s status=%s body=%s",
                    method,
                    path,
                    exc.code,
                    body,
                )
                raise DsClientError(
                    "DS_UNREACHABLE",
                    f"dolphinscheduler responded {exc.code} for {method} {path}",
                    502,
                ) from exc
            except Exception as exc:  # noqa: BLE001 - 网络失败统一收敛为 502
                logger.warning(
                    "ds_request_failed method=%s path=%s error=%s", method, path, type(exc).__name__
                )
                raise DsClientError(
                    "DS_UNREACHABLE", f"cannot reach dolphinscheduler: {type(exc).__name__}", 502
                ) from exc
        return _unwrap(payload, method, path)


def _encode_multipart(
    fields: dict[str, Any], files: dict[str, tuple[str, bytes, str]]
) -> tuple[bytes, str]:
    """手工拼 ``multipart/form-data`` 正文（标准库无 multipart 编码器）。

    ``files`` 形如 ``{字段名: (文件名, 字节内容, Content-Type)}``；海豚资源上传
    的字段名固定为 ``file``。
    """
    boundary = f"----datara{os.urandom(16).hex()}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{key}"'.encode("utf-8"))
        chunks.append(b"")
        chunks.append(str(value).encode("utf-8"))
    for key, (filename, content, content_type) in files.items():
        chunks.append(f"--{boundary}".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{key}"; filename="{filename}"'.encode("utf-8")
        )
        chunks.append(f"Content-Type: {content_type or 'application/octet-stream'}".encode("utf-8"))
        chunks.append(b"")
        chunks.append(content)
    chunks.append(f"--{boundary}--".encode("utf-8"))
    chunks.append(b"")
    return b"\r\n".join(chunks), f"multipart/form-data; boundary={boundary}"


def _unwrap(payload: Any, method: str, path: str) -> Any:
    """拆海豚 ``Result`` 信封；``code != 0`` 视为失败。"""
    if not isinstance(payload, dict):
        raise DsClientError("DS_RESPONSE_INVALID", f"dolphinscheduler returned a non-object payload for {method} {path}")
    try:
        code = int(payload.get("code", -1))
    except (TypeError, ValueError):
        code = -1
    if code != 0:
        msg = str(payload.get("msg", "") or "dolphinscheduler request failed")
        raise DsClientError("DS_API_ERROR", f"{msg} ({method} {path})")
    return payload.get("data")
