"""登录鉴权：POST /login（bcrypt 校验 + token 存 Redis）、DELETE /login（登出）。

- 会话：SETEX datara:token:{token} {TTL} user_json，请求 header token: xxx
- 权限：ROLE_PERMS 静态映射（既有裁定：无权限配置 UI），依赖注入校验
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db import get_db
from common.log import get_logger
from common.models import User
from common import queue
from common.resp import (
    NO_PERM,
    TOKEN_INVALID,
    USER_DISABLED,
    USER_NOT_FOUND,
    USER_PWD_WRONG,
    fail,
    ok,
)
from common.security import new_token, verify_pwd

logger = get_logger("api.auth")

router = APIRouter(tags=["auth"])

# 角色权限点静态映射（设计文档 §6.1）
ROLE_PERMS = {
    "admin": ["manage_user", "edit_definition", "run_instance", "view_all"],
    "dev": ["edit_definition", "run_instance", "view_all"],
    "analyst": ["run_instance", "view_all"],
    "viewer": ["view_all"],
}

# 角色中文名（登录返回 roleName）
ROLE_NAMES = {"admin": "管理员", "dev": "开发者", "analyst": "分析师", "viewer": "观察者"}


class ApiError(Exception):
    """业务异常：转统一响应包（main.py 注册 exception_handler）。"""

    def __init__(self, code: int, msg: Optional[str] = None, status: int = 400):
        self.code = code
        self.msg = msg
        self.status = status
        super().__init__(msg or code)


class LoginBody(BaseModel):
    user_name: str
    user_pwd: str


def user_payload(user: User) -> dict:
    """登录/会话用户信息形状：{name, role, roleName, perms}。"""
    return {
        "name": user.user_name,
        "role": user.user_role,
        "roleName": ROLE_NAMES.get(user.user_role, user.user_role),
        "perms": ROLE_PERMS.get(user.user_role, []),
    }


def _request_token(request: Request) -> Optional[str]:
    """取 token：优先 header token，兼容 Authorization: Bearer xxx；
    query 参数 ?token= 兜底（SSE EventSource 无法携带 header，I10）。"""
    token = request.headers.get("token")
    if token:
        return token
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return request.query_params.get("token")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """会话校验依赖：无 token / 过期 → 401 + code 1003。"""
    token = _request_token(request)
    if not token:
        raise ApiError(TOKEN_INVALID, status=401)
    user_json = queue.get_token(token)
    if not user_json:
        raise ApiError(TOKEN_INVALID, status=401)
    info = json.loads(user_json)
    user = db.get(User, info.get("id"))
    if user is None:
        raise ApiError(USER_NOT_FOUND, status=401)
    if user.state != "enabled":
        raise ApiError(USER_DISABLED, status=403)
    return user


def require_perm(perm: str):
    """权限点校验依赖工厂（写操作注入使用）。"""

    def checker(user: User = Depends(get_current_user)) -> User:
        if perm not in ROLE_PERMS.get(user.user_role, []):
            raise ApiError(NO_PERM, status=403)
        return user

    return checker


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    """登录：bcrypt 校验 → token 存 Redis SETEX → 返回 {token, user}。"""
    user = db.query(User).filter(User.user_name == body.user_name).first()
    if user is None:
        return fail(USER_NOT_FOUND)
    if not verify_pwd(body.user_pwd, user.user_pwd):
        return fail(USER_PWD_WRONG)
    if user.state != "enabled":
        return fail(USER_DISABLED)

    token = new_token()
    settings = get_settings()
    session_info = json.dumps(
        {"id": user.id, "user_name": user.user_name, "role": user.user_role},
        ensure_ascii=False,
    )
    queue.save_token(token, session_info, settings.token_ttl)
    logger.info("用户登录成功: %s（角色 %s）", user.user_name, user.user_role)
    return ok({"token": token, "user": user_payload(user)})


@router.delete("/login")
def logout(request: Request):
    """登出：删除 Redis 会话。"""
    token = _request_token(request)
    if token:
        queue.delete_token(token)
    return ok(True)
