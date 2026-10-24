"""Transactional repository for LLM configurations."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from rebuild.llm.models import LlmModelRecord


class LlmModelRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self, *, offset: int = 0, limit: int = 50):
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("offset/limit out of range")
        return tuple(
            self._session.scalars(
                select(LlmModelRecord)
                .order_by(LlmModelRecord.sort_order, LlmModelRecord.id)
                .offset(offset)
                .limit(limit)
            )
        )

    def get(self, model_id: int):
        return self._session.get(LlmModelRecord, model_id)

    def add(self, record: LlmModelRecord):
        if record.is_default and not record.is_active:
            raise ValueError("inactive model cannot be default")
        if record.is_default:
            self._clear_default()
        self._session.add(record)
        self._session.flush()
        return record

    def set_default(self, model_id: int):
        record = self.get(model_id)
        if record is None:
            raise LookupError("LLM model not found")
        if not record.is_active:
            raise ValueError("inactive model cannot be default")
        self._clear_default()
        record.is_default = True
        self._session.flush()
        return record

    def delete(self, model_id: int) -> None:
        record = self.get(model_id)
        if record is None:
            raise LookupError("LLM model not found")
        if record.is_default:
            raise ValueError("default model cannot be deleted")
        self._session.delete(record)
        self._session.flush()

    def _clear_default(self) -> None:
        self._session.execute(update(LlmModelRecord).values(is_default=False))
