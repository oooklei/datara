"""物理化连接工厂（A6-17 随票下沉）。

迁移源实锚：`datara-backend/common/dsconn.py:23-24,38-62`
（`CONNECT_TIMEOUT` / `DEFAULT_READ_TIMEOUT` / `open_connection`）。

**只下沉物理化所需的最小面**。`common/dsconn.py` 的文件源解析（`FileSpec` /
`normalize_file_params` / `resolve_file_path` / `iter_rows` / `infer_schema`）与标识符
校验（`quote_ident`，已由 17.2-16 下沉至 `rebuild/model/ddlgen.py`）**均不在本票范围**——
旧侧 `physicalize` 只用到连接面（`api/model.py:520-523`）。

**照抄不重构的两条理由**：
① 旧侧 `open_connection` 返回 **pymysql 原生短连接**（`pymysql.connections.Connection`），
   物理化执行循环用 `conn.cursor()` / `cur.execute()` / `conn.commit()` / `conn.close()`。
   rebuild 侧虽有 SQLAlchemy 池化口径（`rebuild/datasource/pool.py`），但改走
   `engine.raw_connection()` 会引入「连接来源不同」的语义漂移；旧侧注记明确
   「不进常驻池，防长查询占满 api 进程连接」——照抄原生连接即忠实保留该裁定。
② `common/dsconn.py` 模块级 `import pymysql` + `from common.models import DataSource`
   会拖入全量旧 ORM 元数据（与 17.2-16 `ddlgen` 下沉同因），故只搬连接函数，
   `DataSource` 由 `rebuild.model.models.DataSourceRecord` 提供（同列名，duck-typed）。

第⑤步下线旧侧后本模块即退役（连同 `DataSourceRecord`）。
"""

from typing import Optional

from pymysql.connections import Connection

from rebuild.model.models import DataSourceRecord

CONNECT_TIMEOUT = 5  # 连接建立超时（秒）
DEFAULT_READ_TIMEOUT = 60  # 单语句读超时（秒，IDE 口径）


def open_connection(
    ds: DataSourceRecord,
    *,
    db: Optional[str] = None,
    read_timeout: Optional[int] = DEFAULT_READ_TIMEOUT,  # None = 不限（导出重放链路）
) -> Connection:
    """按数据源行打开 pymysql 短连接（不进常驻池，防长查询占满 api 进程连接）。

    - db 可覆盖 ds.db_name（IDE 切库场景）
    - greatdb 缺省端口 3316（仅数据源行未填 port 时兜底，前端表单已带缺省）
    """
    if ds.type not in ("mysql", "greatdb"):
        raise ValueError(f"不支持的连接型数据源类型: {ds.type}")
    default_port = 3316 if ds.type == "greatdb" else 3306
    return Connection(
        host=ds.host or "127.0.0.1",
        port=int(ds.port) if ds.port else default_port,
        user=ds.user or "root",
        password=ds.pwd or "",
        database=db or ds.db_name or None,
        charset="utf8mb4",
        connect_timeout=CONNECT_TIMEOUT,
        read_timeout=read_timeout,
        write_timeout=read_timeout,
    )
