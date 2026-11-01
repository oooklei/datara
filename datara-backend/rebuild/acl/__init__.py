"""统一资源 ACL、策略判定与业务审计。

设计依据：docs/designs/2026-11-01-identity-resource-governance-design.md §7。
"""

from .api import build_acl_router
from .backfill import apply_acl_backfill
from .models import ACL_TABLES
from .policy import PolicyService, Subject
from .service import AclService, AuditWriter

__all__ = [
    "ACL_TABLES",
    "AclService",
    "AuditWriter",
    "PolicyService",
    "Subject",
    "apply_acl_backfill",
    "build_acl_router",
]
