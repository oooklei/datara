"""环境变量配置（pydantic-settings）。

全部字段均有默认值：容器内由 docker-compose 注入真实连接串；
本机直跑时默认指向 compose 服务名，仅编译/静态检查不触发连接。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---- meta 库（MySQL/PyMySQL） ----
    db_host: str = "mysql-meta"
    db_port: int = 3306
    db_user: str = "root"
    db_pwd: str = "datara_2026"
    db_name: str = "datara_meta"
    # ---- Redis（队列 + 会话） ----
    redis_url: str = "redis://redis:6379/0"
    # ---- ZooKeeper（注册中心） ----
    zk_hosts: str = "zookeeper:2181"
    # ---- 日志目录（worker 写 / logger 读，compose 共享卷 datara-logs） ----
    log_dir: str = "/datara/logs"
    # ---- 临时目录（shell/python 运行目录 {tmp_dir}/{instance_id}，清理脚本 F50 清理） ----
    tmp_dir: str = "/datara/tmp"
    # ---- 会话 TTL（秒） ----
    token_ttl: int = 86400
    # ---- 初始四账号密码（install.sh 可用环境变量覆盖） ----
    datara_admin_pwd: str = "Admin@123"
    datara_dev_pwd: str = "Dev@123"
    datara_analyst_pwd: str = "Analyst@123"
    datara_viewer_pwd: str = "Viewer@123"

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    @property
    def db_url(self) -> str:
        """SQLAlchemy 连接串（PyMySQL 驱动，utf8mb4）。"""
        return "mysql+pymysql://%s:%s@%s:%s/%s?charset=utf8mb4" % (
            self.db_user,
            self.db_pwd,
            self.db_host,
            self.db_port,
            self.db_name,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程级单例：避免重复解析环境变量（计算优化）。"""
    return Settings()
