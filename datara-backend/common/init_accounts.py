"""初始账号写入：python -m common.init_accounts

幂等写入四账号（install.sh 第 5 步调用；密码可用 DATARA_ADMIN_PWD 等环境变量覆盖）：
- admin/Admin@123、dev/Dev@123、analyst/Analyst@123、viewer/Viewer@123
已存在则同步为环境变量指定的密码与角色（幂等重跑无副作用）。
"""

from common.config import get_settings
from common.db import init_db, new_session
from common.log import setup_logging, get_logger
from common.models import User
from common.security import hash_pwd

# (用户名, 密码配置键, 角色)
ACCOUNTS = [
    ("admin", "datara_admin_pwd", "admin"),
    ("dev", "datara_dev_pwd", "dev"),
    ("analyst", "datara_analyst_pwd", "analyst"),
    ("viewer", "datara_viewer_pwd", "viewer"),
]


def main() -> None:
    setup_logging("init_accounts")
    logger = get_logger("init_accounts")
    init_db()  # 兜底建表（首次直接执行本命令时也能落库）
    settings = get_settings()

    session = new_session()
    try:
        for name, pwd_key, role in ACCOUNTS:
            plain = getattr(settings, pwd_key)
            hashed = hash_pwd(plain)
            user = session.query(User).filter(User.user_name == name).first()
            if user is None:
                session.add(User(user_name=name, user_pwd=hashed, user_role=role, state="enabled"))
                logger.info("初始账号写入: %s（角色 %s）", name, role)
            else:
                # 幂等：同步密码/角色/状态为当前配置
                user.user_pwd = hashed
                user.user_role = role
                user.state = "enabled"
                logger.info("初始账号已存在，同步配置: %s（角色 %s）", name, role)
        session.commit()
        logger.info("初始账号初始化完成（共 %d 个）", len(ACCOUNTS))
    finally:
        session.close()


if __name__ == "__main__":
    main()
