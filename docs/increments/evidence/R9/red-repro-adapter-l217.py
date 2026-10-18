"""RED 复现：adapter.py:217 缺 self 缺陷（P1-6' TDD RED 阶段）

修复前代码（10069ac^）：
    OpenAI_Chat.__init__(client=client, config={"model": settings.model})
                              ^^^^ 缺 self -> TypeError

本脚本用修复前的调用模式复现 TypeError，作为 TDD RED 证据。
GREEN 证据见 test_adapter_default_factory.py（当前代码 2/2 PASS）。
"""

import sys
import tempfile
from pathlib import Path

from vanna.legacy.chromadb.chromadb_vector import ChromaDB_VectorStore
from vanna.legacy.openai.openai_chat import OpenAI_Chat
from openai import OpenAI


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="red-repro-"))
    client = OpenAI(api_key="red-repro-only", base_url="https://api.siliconflow.cn/v1")

    class BrokenTenantVanna(ChromaDB_VectorStore, OpenAI_Chat):
        def __init__(self) -> None:
            ChromaDB_VectorStore.__init__(self, config={"path": str(tmp)})
            # RED: 修复前缺 self 的调用（10069ac^ 模式）
            OpenAI_Chat.__init__(client=client, config={"model": "red-repro"})

    try:
        BrokenTenantVanna()
    except TypeError as exc:
        print(f"RED REPRODUCED: TypeError: {exc}")
        return 0
    print("UNEXPECTED: no TypeError raised")
    return 1


if __name__ == "__main__":
    sys.exit(main())
