"""流任务模块（I8）：引擎宿主 + 源/算子/汇三段管道。

get_engine() 返回 worker 进程级单例（worker/main.py 启动时 start、退出时 stop）；
API 进程不持有引擎（仅写库 + Redis 广播，裁定② master 只注册/透传）。
"""

from worker.stream.engine import JobRuntime, StreamEngine

_engine: StreamEngine | None = None


def get_engine() -> StreamEngine:
    global _engine
    if _engine is None:
        _engine = StreamEngine()
    return _engine


__all__ = ["JobRuntime", "StreamEngine", "get_engine"]
