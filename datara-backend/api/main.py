"""FastAPI 应用入口（api 模块）：CORS 全开（开发期）、路由挂载、启动建表 + ZK 注册。

容器启动：uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.db import init_db
from common.log import get_logger
from common.registry import ServiceRegistry
from common.resp import fail
from api.auth import ApiError

logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动：create_all 兜底建表 + 注册 ZK；停止：注销。"""
    init_db()
    registry = ServiceRegistry("api", 8000)
    registry.start()
    app.state.registry = registry
    logger.info("api 模块启动完成（:8000）")
    yield
    registry.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Datara API", version="0.1.0", lifespan=lifespan)

    # CORS 全开（开发期）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # 业务异常 → 统一响应包
    @app.exception_handler(ApiError)
    async def api_error_handler(request, exc: ApiError):  # noqa: ANN001 FastAPI 回调签名
        return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.msg))

    # 路由前缀统一 /api/v1
    from api import (
        auth,
        datasource,
        health,
        ide,
        instance,
        lineage,
        meta_ops,
        monitor,
        params,
        runtime_node,
        smoke,
        sshnode,
        streamdata,
        streamjob,
        sync,
        wf_definition,
        wf_schedule,
        wf_variable,
    )

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(datasource.router, prefix="/api/v1")
    app.include_router(ide.router, prefix="/api/v1")
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(instance.router, prefix="/api/v1")
    app.include_router(lineage.router, prefix="/api/v1")
    app.include_router(meta_ops.router, prefix="/api/v1")
    app.include_router(monitor.router, prefix="/api/v1")
    app.include_router(params.router, prefix="/api/v1")
    app.include_router(runtime_node.router, prefix="/api/v1")
    app.include_router(smoke.router, prefix="/api/v1")
    app.include_router(sshnode.router, prefix="/api/v1")
    app.include_router(streamjob.router, prefix="/api/v1")
    app.include_router(streamdata.router, prefix="/api/v1")
    app.include_router(sync.router, prefix="/api/v1")
    app.include_router(wf_definition.router, prefix="/api/v1")
    app.include_router(wf_schedule.router, prefix="/api/v1")
    app.include_router(wf_variable.router, prefix="/api/v1")

    # 日志查询（I3 §11.1：api 网关挂载 logger 路由，共享卷读文件；logger 容器保留健康职责）
    from logger.log_api import router as log_router

    app.include_router(log_router, prefix="/api/v1")
    return app


app = create_app()
