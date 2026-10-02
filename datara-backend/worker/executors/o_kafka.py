"""o_kafka 执行器：Kafka 输出（Stream 输出）。

- Topic：param.topic
- 输出：written_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("o_kafka")
def execute(ctx) -> ExecResult:
    """执行 Kafka 写入，返回写入行数。"""
    param = ctx.param or {}
    topic = param.get("topic")

    if not topic:
        return ExecResult(FAILURE, {}, ["[o_kafka] 未指定 Topic（topic）"])

    ctx.log("[o_kafka] Topic: %s" % topic)

    # TODO: 实现 Kafka 写入
    outputs = {"written_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
