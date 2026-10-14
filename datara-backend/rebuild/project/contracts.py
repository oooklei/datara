"""项目成员权限，不依赖旧 Backend。"""

from dataclasses import dataclass

from rebuild.identity.contracts import Role


@dataclass(frozen=True)
class Member:
    user_id: int
    role: Role
    is_owner: bool = False


def can_manage_project(member: Member) -> bool:
    return member.is_owner or member.role is Role.ADMIN

