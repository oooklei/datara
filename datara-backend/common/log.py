"""结构化日志：本地时区、instance_id 上下文贯穿、控制台 + 文件双写。"""

import logging
import os
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from typing import Optional

# instance_id 上下文（贯穿任务日志与调度日志，回查追溯按 instance_id 定位）
_instance_id: ContextVar[str] = ContextVar("instance_id", default="-")

_FMT = "%(asctime)s [%(levelname)s] [%(name)s] [instance:%(instance_id)s] %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"  # 本地时区（logging 默认 localtime）


class InstanceFilter(logging.Filter):
    """为每条日志附加 instance_id（未设置时为 '-'）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.instance_id = _instance_id.get()
        return True


def set_instance_id(value: Optional[str]) -> None:
    """设置当前上下文的 instance_id（worker 执行任务前调用）。"""
    _instance_id.set(value or "-")


def get_instance_id() -> str:
    return _instance_id.get()


def setup_logging(module: str) -> None:
    """初始化模块级日志：控制台 + {LOG_DIR}/{module}.log 轮转文件（幂等可重复调用）。"""
    from common.config import get_settings

    logger = logging.getLogger(module)
    if getattr(logger, "_datara_configured", False):
        return
    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter(_FMT, datefmt=_DATEFMT)
    inst_filter = InstanceFilter()

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(inst_filter)
    logger.addHandler(console)

    log_dir = get_settings().log_dir
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "%s.log" % module),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        file_handler.addFilter(inst_filter)
        logger.addHandler(file_handler)
    except OSError:
        # 文件日志不可用（如本机只读目录）时降级仅控制台，不阻断启动
        logger.warning("日志文件目录不可用，降级为仅控制台输出: %s", log_dir)

    logger._datara_configured = True  # type: ignore[attr-defined]  幂等标记


def get_logger(module: str) -> logging.Logger:
    """取模块 logger；未初始化时先初始化（确保 handler 就绪）。"""
    setup_logging(module.split(".")[0])
    return logging.getLogger(module)


class InstanceLogAdapter(logging.LoggerAdapter):
    """以固定 instance_id 输出日志的适配器（调度器逐实例打印用）。"""

    def process(self, msg: str, kwargs: dict):
        set_instance_id(self.extra.get("instance_id") if self.extra else None)
        return msg, kwargs
