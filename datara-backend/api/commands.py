"""命令提交公共助手（I3 设计 §3.1）：api 侧只写 t_command(wait)，master 2s 轮询消费。"""

from sqlalchemy.orm import Session

from common.models import Command


def submit_command(db: Session, command_type: str, param: dict, priority: int = 0) -> Command:
    """写一条 wait 命令并提交事务，返回命令行（供响应 commandId）。"""
    command = Command(command_type=command_type, command_param=param, priority=priority, state="wait")
    db.add(command)
    db.commit()
    return command
