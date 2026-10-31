"""
守卫测试：固化 Doc A（dbx 统一后端迁移）收敛方向。

设计约束（docs/designs/2026-10-29-phase-1-dbx-unified-backend-design.md）：
  datara 后端除薄身份服务外，不得直连用户库（pymysql / psycopg / MySQLdb）。
  rebuild/dbx（代理层）与 rebuild/identity（薄身份服务自身库）是设计上的「干净层」，
  绝不允许出现直连用户库的原始驱动；二者以 SQLAlchemy ORM 操作「自身元数据」属允许例外。

本测试断言这两个目录不出现原始用户库驱动符号；若有人在 proxy/identity 层新增
pymysql.connect / psycopg.connect / MySQLdb 等直连，本测试立即失败，防止回归。
"""
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
GUARDED = ["rebuild/dbx", "rebuild/identity"]
RAW_DRIVERS = ("pymysql", "psycopg", "psycopg2", "MySQLdb")


@pytest.mark.parametrize("rel", GUARDED)
def test_no_raw_user_db_drivers(rel: str) -> None:
    root = BACKEND / rel
    if not root.exists():
        pytest.skip(f"{rel} not present")
    hits = []
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for drv in RAW_DRIVERS:
            if drv in text:
                hits.append(f"{path.relative_to(BACKEND)}:{drv}")
    assert not hits, f"在 {rel} 发现直连用户库原始驱动: {hits}"
