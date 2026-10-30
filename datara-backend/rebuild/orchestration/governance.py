"""海豚运行资源（worker 分组 / 环境 / 队列 / 集群）的归属与共享（设计 §10.10）。

海豚侧没有「按 datara 用户隔离」的概念，故归属关系记在 datara 侧，键为
``(kind, resource_key)``：

- ``resource_key`` 取海豚侧的业务标识而非自增主键——worker 分组用分组名
  （配置文件来源的分组没有 id，且节点表单回写的就是分组名），环境/队列/集群
  用 ``code``/``id`` 的字符串形式。
- 未登记归属的既有资源（如海豚自带 ``default`` 分组与队列）对所有登录用户
  只读可见：它们是节点表单的必备下拉项，隐藏会导致「未建分组时下拉为空」。
- 用户新建的资源自动归属创建者；``admin`` 全见，其他角色仅自己 + 显式共享。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from rebuild.common.db import Base
from rebuild.identity.models import UserRecord

KIND_WORKER_GROUP = "worker_group"
KIND_ENVIRONMENT = "environment"
KIND_QUEUE = "queue"
KIND_CLUSTER = "cluster"
KIND_TASK_GROUP = "task_group"
KIND_RESOURCE_FILE = "resource_file"

KINDS = (
    KIND_WORKER_GROUP,
    KIND_ENVIRONMENT,
    KIND_QUEUE,
    KIND_CLUSTER,
    KIND_TASK_GROUP,
    KIND_RESOURCE_FILE,
)


class OrchestrationResourceOwnershipRecord(Base):
    __tablename__ = "rebuild_orchestration_resource_ownership"
    __table_args__ = (UniqueConstraint("kind", "resource_key", name="uq_orch_resource_ownership"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    resource_key: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("rebuild_user.id"), nullable=False, index=True)


class OrchestrationResourceShareRecord(Base):
    __tablename__ = "rebuild_orchestration_resource_share"
    __table_args__ = (UniqueConstraint("kind", "resource_key", "user_id", name="uq_orch_resource_share"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    resource_key: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("rebuild_user.id"), nullable=False, index=True)


class OrchestrationResourceAccess:
    def __init__(self, session: Session) -> None:
        self.session = session

    def owner_of(self, kind: str, resource_key: str) -> int | None:
        return self.session.scalar(
            select(OrchestrationResourceOwnershipRecord.owner_id).where(
                OrchestrationResourceOwnershipRecord.kind == kind,
                OrchestrationResourceOwnershipRecord.resource_key == resource_key,
            )
        )

    def claim(self, kind: str, resource_key: str, owner_id: int) -> None:
        existing = self.owner_of(kind, resource_key)
        if existing is not None:
            if existing != owner_id:
                raise PermissionError("resource already owned by another user")
            return
        if self.session.get(UserRecord, owner_id) is None:
            raise PermissionError("resource owner does not exist")
        self.session.add(
            OrchestrationResourceOwnershipRecord(kind=kind, resource_key=resource_key, owner_id=owner_id)
        )

    def share(self, kind: str, resource_key: str, user_id: int) -> None:
        exists = self.session.scalar(
            select(OrchestrationResourceShareRecord.id).where(
                OrchestrationResourceShareRecord.kind == kind,
                OrchestrationResourceShareRecord.resource_key == resource_key,
                OrchestrationResourceShareRecord.user_id == user_id,
            )
        )
        if exists is None:
            self.session.add(
                OrchestrationResourceShareRecord(kind=kind, resource_key=resource_key, user_id=user_id)
            )

    def unshare(self, kind: str, resource_key: str, user_id: int) -> None:
        self.session.execute(
            delete(OrchestrationResourceShareRecord).where(
                OrchestrationResourceShareRecord.kind == kind,
                OrchestrationResourceShareRecord.resource_key == resource_key,
                OrchestrationResourceShareRecord.user_id == user_id,
            )
        )

    def release(self, kind: str, resource_key: str) -> None:
        """资源在海豚侧删除后清掉归属与共享，避免 key 复用串权。"""
        self.session.execute(
            delete(OrchestrationResourceOwnershipRecord).where(
                OrchestrationResourceOwnershipRecord.kind == kind,
                OrchestrationResourceOwnershipRecord.resource_key == resource_key,
            )
        )
        self.session.execute(
            delete(OrchestrationResourceShareRecord).where(
                OrchestrationResourceShareRecord.kind == kind,
                OrchestrationResourceShareRecord.resource_key == resource_key,
            )
        )

    def release_prefix(self, kind: str, prefix: str) -> None:
        """删除目录时连带释放其下所有子资源归属（海豚目录删除是递归的）。"""
        self.release(kind, prefix)
        pattern = f"{prefix}/%"
        for model in (OrchestrationResourceOwnershipRecord, OrchestrationResourceShareRecord):
            self.session.execute(
                delete(model).where(model.kind == kind, model.resource_key.like(pattern))
            )

    def can_view(self, kind: str, resource_key: str, user_id: int, *, is_admin: bool = False) -> bool:
        return resource_key in self.visible_keys(kind, [resource_key], user_id, is_admin=is_admin)

    def can_manage(self, kind: str, resource_key: str, user_id: int, *, is_admin: bool = False) -> bool:
        return is_admin or self.owner_of(kind, resource_key) == user_id

    def owners_of(self, kind: str, resource_keys: list[str]) -> dict[str, int]:
        """批量取归属，避免列表接口逐条查询。"""
        key_set = {str(key) for key in resource_keys}
        if not key_set:
            return {}
        return dict(
            self.session.execute(
                select(
                    OrchestrationResourceOwnershipRecord.resource_key,
                    OrchestrationResourceOwnershipRecord.owner_id,
                ).where(
                    OrchestrationResourceOwnershipRecord.kind == kind,
                    OrchestrationResourceOwnershipRecord.resource_key.in_(key_set),
                )
            ).all()
        )

    def visible_keys(
        self, kind: str, resource_keys: list[str], user_id: int, *, is_admin: bool = False
    ) -> set[str]:
        """批量可见性判定，避免逐条查询。"""
        key_set = {str(key) for key in resource_keys}
        if is_admin:
            return key_set
        if not key_set:
            return set()
        owners = self.owners_of(kind, list(key_set))
        shared = set(
            self.session.scalars(
                select(OrchestrationResourceShareRecord.resource_key).where(
                    OrchestrationResourceShareRecord.kind == kind,
                    OrchestrationResourceShareRecord.resource_key.in_(key_set),
                    OrchestrationResourceShareRecord.user_id == user_id,
                )
            ).all()
        )
        return {
            key
            for key in key_set
            if owners.get(key) in (None, user_id) or key in shared
        }
