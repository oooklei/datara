"""Administrative API for LLM model configuration."""

from decimal import Decimal
from typing import Any, Callable

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from rebuild.identity.contracts import Permission, authorize
from rebuild.llm.crypto import mask_api_key
from rebuild.llm.models import LlmModelRecord
from rebuild.llm.provider import LlmProviderError, test_chat
from rebuild.llm.repository import LlmModelRepository


class LlmModelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=64)
    provider: str
    api_base: str
    model_id: str = Field(min_length=1, max_length=128)
    api_key: str = ""
    max_tokens: int = Field(default=10000, ge=1)
    temperature: float = Field(default=0.7, ge=0, le=2)
    is_active: bool = True
    is_default: bool = False
    sort_order: int = 0

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        if value not in {"siliconflow", "volcengine"}:
            raise ValueError("unsupported LLM provider")
        return value

    @field_validator("api_base")
    @classmethod
    def validate_api_base(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("api_base must use HTTPS")
        return value.rstrip("/")


def build_llm_router(
    session_factory,
    token_service: Any,
    active_tokens: Any,
    cipher,
    *,
    probe: Callable[[str, str, str], dict[str, object]] = test_chat,
) -> APIRouter:
    router = APIRouter()

    def guard(token: str, authorization: str):
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw or raw not in active_tokens:
            return _error(401, 1001, "invalid token")
        try:
            claims = token_service.verify(raw)
        except ValueError:
            return _error(401, 1001, "invalid token")
        if claims.get("capability") is not None or not authorize(str(claims["role"]), Permission.MANAGE_USER):
            return _error(403, 1003, "permission denied")
        return None

    @router.get("")
    def list_models(
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if denial := guard(token, authorization):
            return denial
        with session_factory() as session:
            return _ok(
                {
                    "items": [
                        _payload(row, cipher) for row in LlmModelRepository(session).list(offset=offset, limit=limit)
                    ]
                }
            )

    @router.post("", status_code=201)
    def create_model(body: LlmModelRequest, token: str = Header(default=""), authorization: str = Header(default="")):
        if denial := guard(token, authorization):
            return denial
        if not body.api_key:
            return _error(400, 4001, "api_key is required")
        with session_factory() as session:
            try:
                with session.begin():
                    row = LlmModelRepository(session).add(_record(body, cipher))
                return _ok(_payload(row, cipher))
            except IntegrityError:
                return _error(409, 4091, "model name or default conflicts")
            except ValueError as exc:
                return _error(400, 4001, str(exc))

    @router.put("/{item_id}")
    def update_model(
        item_id: int, body: LlmModelRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        if denial := guard(token, authorization):
            return denial
        with session_factory() as session:
            repo = LlmModelRepository(session)
            row = repo.get(item_id)
            if row is None:
                return _error(404, 4041, "LLM model not found")
            try:
                for key in ("name", "display_name", "provider", "api_base", "model_id", "max_tokens", "sort_order"):
                    setattr(row, key, getattr(body, key))
                row.temperature = Decimal(str(body.temperature))
                if body.api_key:
                    row.api_key_cipher = cipher.encrypt(body.api_key)
                if body.is_default:
                    repo.set_default(item_id)
                if row.is_default and not body.is_active:
                    raise ValueError("default model cannot be disabled")
                row.is_active = body.is_active
                session.commit()
                return _ok(_payload(row, cipher))
            except IntegrityError:
                return _error(409, 4091, "model name or default conflicts")
            except ValueError as exc:
                return _error(409, 4092, str(exc))

    @router.delete("/{item_id}")
    def delete_model(item_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        if denial := guard(token, authorization):
            return denial
        with session_factory() as session:
            try:
                LlmModelRepository(session).delete(item_id)
                session.commit()
                return _ok({"deleted": True, "id": item_id})
            except LookupError:
                return _error(404, 4041, "LLM model not found")
            except ValueError as exc:
                return _error(409, 4092, str(exc))

    @router.put("/{item_id}/default")
    def set_default(item_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        if denial := guard(token, authorization):
            return denial
        with session_factory() as session:
            try:
                row = LlmModelRepository(session).set_default(item_id)
                session.commit()
                return _ok(_payload(row, cipher))
            except LookupError:
                return _error(404, 4041, "LLM model not found")
            except ValueError as exc:
                return _error(409, 4092, str(exc))

    @router.post("/{item_id}/test")
    def test_model(item_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        if denial := guard(token, authorization):
            return denial
        with session_factory() as session:
            row = LlmModelRepository(session).get(item_id)
            if row is None:
                return _error(404, 4041, "LLM model not found")
            try:
                return _ok(probe(row.api_base, row.model_id, cipher.decrypt(row.api_key_cipher)))
            except (LlmProviderError, ValueError) as exc:
                return _error(502, 5021, str(exc))

    return router


def _record(body, cipher):
    return LlmModelRecord(
        name=body.name,
        display_name=body.display_name,
        provider=body.provider,
        api_base=body.api_base,
        model_id=body.model_id,
        api_key_cipher=cipher.encrypt(body.api_key),
        max_tokens=body.max_tokens,
        temperature=Decimal(str(body.temperature)),
        is_active=body.is_active,
        is_default=body.is_default,
        sort_order=body.sort_order,
    )


def _payload(row, cipher):
    return {
        "id": row.id,
        "name": row.name,
        "display_name": row.display_name,
        "provider": row.provider,
        "api_base": row.api_base,
        "model_id": row.model_id,
        "api_key": mask_api_key(cipher.decrypt(row.api_key_cipher)),
        "max_tokens": row.max_tokens,
        "temperature": float(row.temperature),
        "is_active": bool(row.is_active),
        "is_default": bool(row.is_default),
        "sort_order": row.sort_order,
    }


def _ok(data):
    return {"code": 0, "msg": "success", "data": data}


def _error(status, code, msg):
    return JSONResponse(status_code=status, content={"code": code, "msg": msg, "data": None})
