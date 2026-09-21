"""统一响应包 / 错误码 / 分页参数（对齐海豚 Status 枚举思路）。

- 响应包：{"code":0,"msg":"success","data":...}，失败 code≠0
- 错误码分段：1xxx 用户/鉴权、2xxx 工作流定义、3xxx 实例/命令、4xxx 数据源/参数、5xxx 系统
- 时间序列化统一 '%Y-%m-%d %H:%M:%S'（本地时区，既有 toISOString 教训）
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

# ---------- 错误码常量（分段） ----------
USER_NOT_FOUND = 1001
USER_PWD_WRONG = 1002
TOKEN_INVALID = 1003
NO_PERM = 1004
USER_DISABLED = 1005

WF_NOT_FOUND = 2001
WF_DUPLICATE = 2002
WF_PARAM_INVALID = 2003
WF_VERSION_NOT_FOUND = 2004

INSTANCE_NOT_FOUND = 3001
COMMAND_FAIL = 3002

DS_NOT_FOUND = 4001
PARAM_INVALID = 4002
HISTORY_NOT_FOUND = 4003
TMP_NOT_FOUND = 4004
SCRIPT_NOT_FOUND = 4005
TASK_NOT_FOUND = 4006  # IDE 异步执行任务不存在（I10）

SYSTEM_ERROR = 5001
DEP_UNAVAILABLE = 5002

_MSGS = {
    USER_NOT_FOUND: "用户不存在",
    USER_PWD_WRONG: "密码错误",
    TOKEN_INVALID: "未登录或会话已过期",
    NO_PERM: "无操作权限",
    USER_DISABLED: "账号已禁用",
    WF_NOT_FOUND: "工作流定义不存在",
    WF_DUPLICATE: "工作流定义已存在",
    WF_PARAM_INVALID: "工作流定义参数错误",
    WF_VERSION_NOT_FOUND: "版本快照不存在",
    INSTANCE_NOT_FOUND: "运行实例不存在",
    COMMAND_FAIL: "命令提交失败",
    DS_NOT_FOUND: "数据源不存在",
    PARAM_INVALID: "参数错误",
    HISTORY_NOT_FOUND: "执行历史不存在",
    TMP_NOT_FOUND: "临时数据不存在",
    SCRIPT_NOT_FOUND: "脚本不存在",
    TASK_NOT_FOUND: "执行任务不存在（已过期或已完成清理）",
    SYSTEM_ERROR: "系统内部错误",
    DEP_UNAVAILABLE: "依赖组件不可用",
}


def fmt_dt(value: Optional[datetime]) -> Optional[str]:
    """datetime → 'YYYY-MM-DD HH:mm:ss'（本地时区写库，原样序列化）。"""
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


def ok(data: Any = None) -> dict:
    """成功响应包。"""
    return {"code": 0, "msg": "success", "data": data}


def fail(code: int, msg: Optional[str] = None) -> dict:
    """失败响应包（code≠0；msg 缺省时取错误码内置文案）。"""
    return {"code": code, "msg": msg or _MSGS.get(code, "未知错误"), "data": None}


class PageQuery(BaseModel):
    """分页参数（默认 1/10，设计文档 §6.3）。"""

    page_no: int = Field(default=1, ge=1, description="页码，从 1 起")
    page_size: int = Field(default=10, ge=1, le=200, description="每页条数")

    @property
    def offset(self) -> int:
        return (self.page_no - 1) * self.page_size


def page_result(total: int, items: list) -> dict:
    """分页响应 data：{total, list}。"""
    return {"total": total, "list": items}
