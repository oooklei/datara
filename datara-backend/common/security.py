"""安全工具：bcrypt 密码散列 + uuid token 生成。"""

import uuid

from passlib.context import CryptContext

# bcrypt 单例（复用 CryptContext，避免重复构建开销）
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_pwd(plain: str) -> str:
    """bcrypt 散列（t_user.user_pwd 存散列，不存明文）。"""
    return _pwd_context.hash(plain)


def verify_pwd(plain: str, hashed: str) -> bool:
    """校验密码与散列是否匹配。"""
    try:
        return _pwd_context.verify(plain, hashed)
    except ValueError:
        return False


def new_token() -> str:
    """生成会话 token（uuid4 hex，32 位）。"""
    return uuid.uuid4().hex
