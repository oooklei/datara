"""Context-bound, explicit-user confirmation gate for R5-B DDL."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Callable, Mapping

from rebuild.rb.errors.rb_errors import RbErrorCode
from rebuild.rb.models.rb_models import ObjectRef


@dataclass(frozen=True)
class Confirmation:
    """Validated confirmation metadata; the phrase itself is never retained."""

    project_id: int
    actor_id: int
    context_digest: str


class ConfirmGate:
    """Validate a user-entered HMAC phrase against the complete DDL context."""

    def __init__(self, actor_secret: Callable[[int], str]) -> None:
        self._actor_secret = actor_secret

    def _compute_phrase(self, context: Mapping[str, object]) -> str:
        """Return the context-bound HMAC without retaining the phrase or secret."""
        actor_id = context.get("actor_id")
        if not isinstance(actor_id, int) or isinstance(actor_id, bool) or actor_id <= 0:
            raise ValueError(RbErrorCode.CONFIRM_PHRASE_INVALID)
        secret = self._actor_secret(actor_id)
        if not isinstance(secret, str) or not secret:
            raise RuntimeError("confirmation secret is unavailable")
        canonical = json.dumps(
            context,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hmac.new(
            secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def validate_confirmation(
        self,
        *,
        project_id: int,
        actor_id: int,
        object_ref: ObjectRef,
        source_version: str,
        next_ddl_text: str,
        policy_snapshot_id: str,
        impact_snapshot_id: str,
        confirm_phrase: str,
    ) -> Confirmation:
        if not isinstance(confirm_phrase, str) or not confirm_phrase.strip():
            raise ValueError(RbErrorCode.CONFIRM_PHRASE_INVALID)
        if not isinstance(project_id, int) or isinstance(project_id, bool) or project_id <= 0:
            raise ValueError(RbErrorCode.CONFIRM_PHRASE_INVALID)
        if not isinstance(actor_id, int) or isinstance(actor_id, bool) or actor_id <= 0:
            raise ValueError(RbErrorCode.CONFIRM_PHRASE_INVALID)
        if not isinstance(next_ddl_text, str) or not next_ddl_text.strip():
            raise ValueError(RbErrorCode.CONFIRM_PHRASE_INVALID)
        if not all(
            isinstance(value, str) and value.strip()
            for value in (source_version, policy_snapshot_id, impact_snapshot_id)
        ):
            raise ValueError(RbErrorCode.CONFIRM_PHRASE_INVALID)
        if (
            not isinstance(object_ref, ObjectRef)
            or object_ref.datasource_id <= 0
            or not all(
                isinstance(value, str) and value.strip()
                for value in (object_ref.database, object_ref.kind, object_ref.name)
            )
        ):
            raise ValueError(RbErrorCode.CONFIRM_PHRASE_INVALID)
        context = {
            "project_id": project_id,
            "datasource_id": object_ref.datasource_id,
            "object_ref": {
                "database": object_ref.database,
                "catalog": object_ref.catalog,
                "schema": object_ref.schema,
                "kind": object_ref.kind,
                "name": object_ref.name,
                "parent": object_ref.parent,
            },
            "source_version": source_version,
            "next_ddl_digest": hashlib.sha256(next_ddl_text.encode("utf-8")).hexdigest(),
            "policy_snapshot_id": policy_snapshot_id,
            "impact_snapshot_id": impact_snapshot_id,
            "actor_id": actor_id,
        }
        canonical = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected = self._compute_phrase(context)
        if not hmac.compare_digest(confirm_phrase, expected):
            raise ValueError(RbErrorCode.CONFIRM_PHRASE_MISMATCH)
        return Confirmation(
            project_id=project_id,
            actor_id=actor_id,
            context_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )
