"""I18 建模域错误码（R-32 / R2 注记：域内显式定义，禁从 `common/resp.py` 导入）。

R-32 裁定「旧 4xxx/8xxx 原样保留」；R2 注记指出旧侧 4xxx/8xxx 为**硬编码字面量**
（实锚 `common/resp.py:32,56-65` 的常量定义与 `api/main.py:48` 的 `ApiError` 处理器），
故 rebuild 侧不得 `from common.resp import ...`，须在域内逐项复述数值与语义映射。

- `PARAM_INVALID = 4002`  参数错误（旧侧 `resp.py:32`）
- `MODEL_CODE_DUP = 8002`  模型编码已存在（旧侧 `resp.py:57`，HTTP 409）
- `MODEL_CODE_INVALID = 8003`  编码非法，须 `^[a-z][a-z0-9_]*$`（旧侧 `resp.py:58`，HTTP 400）
- `MODEL_NAMING_RULE = 8004`  不符合分层命名规范（旧侧 `resp.py:59`，HTTP 400）

后续票（17.2-06 起）引入 8001/8005/8006/8007/8008/8009/8010 时按同法追加。
"""

from __future__ import annotations

from typing import Any, Optional

# —— 域内显式错误码（数值/语义与旧侧逐项对应，见模块 docstring 实锚）——
PARAM_INVALID = 4002
MODEL_CODE_DUP = 8002
MODEL_CODE_INVALID = 8003
MODEL_NAMING_RULE = 8004

# 旧侧 `common/resp.py:66-109` `_MSGS` 的对应文案（msg 缺省回退用）。
_MSGS: dict[int, str] = {
    PARAM_INVALID: "参数错误",
    MODEL_CODE_DUP: "模型编码已存在",
    MODEL_CODE_INVALID: "编码非法，须以小写字母开头，仅含小写字母/数字/下划线",
    MODEL_NAMING_RULE: "编码不符合分层命名规范",
}


class ModelDomainError(RuntimeError):
    """建模域业务异常：承载旧侧 `ApiError(code, msg, status, data)` 四元组。

    迁移源实锚：`datara-backend/api/auth.py:52-62`（`ApiError`）+
    `api/main.py:48`（`exception_handler` → `fail(code, msg, data)`）。
    """

    def __init__(self, code: int, message: Optional[str] = None, status: int = 400,
                 data: Any = None) -> None:
        super().__init__(message or _MSGS.get(code, "未知错误"))
        self.code = code
        self.message = message or _MSGS.get(code, "未知错误")
        self.status = status
        self.data = data


def fail(code: int, msg: Optional[str] = None, data: Any = None) -> dict[str, Any]:
    """失败响应包（迁移源实锚 `common/resp.py:122-126`，逐字照抄）。

    `code != 0`；`msg` 缺省时取域内内置文案；`data` 供冲突详情等载荷。
    """
    return {"code": code, "msg": msg or _MSGS.get(code, "未知错误"), "data": data}
