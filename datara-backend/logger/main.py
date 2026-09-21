"""logger 模块入口：python -m logger.main

- FastAPI 内部 18004 端口：GET /health（compose healthcheck）+ GET /api/v1/logs?instance_id=
- 进程内注册 ZK /datara/live/logger/{ip:18004}
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI

from common.log import get_logger, setup_logging
from common.registry import ServiceRegistry
from logger.log_api import router as log_router

logger = get_logger("logger")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动：ZK 注册；停止：注销。"""
    registry = ServiceRegistry("logger", 18004)
    registry.start()
    app.state.registry = registry
    logger.info("logger 模块启动（:18004）")
    yield
    registry.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Datara Logger", version="0.1.0", lifespan=lifespan)
    app.include_router(log_router, prefix="/api/v1")

    @app.get("/health")
    def health():
        return {"status": "UP", "module": "logger"}

    return app


app = create_app()


def main() -> None:
    setup_logging("logger")
    uvicorn.run(app, host="0.0.0.0", port=18004, log_level="warning")


if __name__ == "__main__":
    main()
