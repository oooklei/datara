"""I18 建模域错误码（R-32 / R2 注记：域内显式定义，禁从 `common/resp.py` 导入）。

R-32 裁定「旧 4xxx/8xxx 原样保留」；R2 注记指出旧侧 4xxx/8xxx 为**硬编码字面量**
（实锚 `common/resp.py:32,56-65` 的常量定义与 `api/main.py:48` 的 `ApiError` 处理器），
故 rebuild 侧不得 `from common.resp import ...`，须在域内逐项复述数值与语义映射。

- `MODEL_NOT_FOUND = 8001`  模型不存在（旧侧 `resp.py:56`，HTTP 404）
- `PARAM_INVALID = 4002`  参数错误（旧侧 `resp.py:32`）
- `MODEL_CODE_DUP = 8002`  模型编码已存在（旧侧 `resp.py:57`，HTTP 409）
- `MODEL_CODE_INVALID = 8003`  编码非法，须 `^[a-z][a-z0-9_]*$`（旧侧 `resp.py:58`，HTTP 400）
- `MODEL_NAMING_RULE = 8004`  不符合分层命名规范（旧侧 `resp.py:59`，HTTP 400）
- `MODEL_STATE_CONFLICT = 8005`  状态机不允许该操作（旧侧 `resp.py:60`，HTTP 409）
- `MODEL_REV_CONFLICT = 8006`  字段保存乐观锁冲突（旧侧 `resp.py:61`，HTTP 422，data 带 `currentRev`）
- `MODEL_FIELDS_LOCKED = 8007`  非 draft 不可改字段，需开新修订（旧侧 `resp.py:62`，HTTP 409）
- `MODEL_IN_USE = 8008`  模型被下游血缘引用（旧侧 `resp.py:63`，HTTP 409，data 带 `refs`）

后续票（17.2-06 起）引入 8001/8005/8006/8007/8008/8009/8010 时按同法追加。
"""

from __future__ import annotations

from typing import Any, Optional

# —— 域内显式错误码（数值/语义与旧侧逐项对应，见模块 docstring 实锚）——
MODEL_NOT_FOUND = 8001
PARAM_INVALID = 4002
MODEL_CODE_DUP = 8002
MODEL_CODE_INVALID = 8003
MODEL_NAMING_RULE = 8004
MODEL_STATE_CONFLICT = 8005
MODEL_REV_CONFLICT = 8006
MODEL_FIELDS_LOCKED = 8007
MODEL_IN_USE = 8008

# 旧侧 `common/resp.py:66-109` `_MSGS` 的对应文案（msg 缺省回退用）。
_MSGS: dict[int, str] = {
    MODEL_NOT_FOUND: "模型不存在",
    PARAM_INVALID: "参数错误",
    MODEL_CODE_DUP: "模型编码已存在",
    MODEL_CODE_INVALID: "编码非法，须以小写字母开头，仅含小写字母/数字/下划线",
    MODEL_NAMING_RULE: "编码不符合分层命名规范",
    MODEL_STATE_CONFLICT: "当前状态不允许该操作",
    MODEL_REV_CONFLICT: "字段已被他人更新，请刷新后重试",
    MODEL_FIELDS_LOCKED: "已发布模型不可修改字段，请开新修订",
    MODEL_IN_USE: "模型被下游血缘引用，不可删除",
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
