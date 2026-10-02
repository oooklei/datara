"""s_kafka 执行器：Kafka 源（Stream 输入）。

- Topic：param.topic
- 消费者组：param.consumerGroup
- 输出：consumed_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("s_kafka")
def execute(ctx) -> ExecResult:
    """执行 Kafka 消费，返回消费行数。"""
    param = ctx.param or {}
    topic = param.get("topic")
    consumer_group = param.get("consumerGroup")

    if not topic:
        return ExecResult(FAILURE, {}, ["[s_kafka] 未指定 Topic（topic）"])

    ctx.log("[s_kafka] Topic: %s" % topic)
    ctx.log("[s_kafka] 消费者组: %s" % consumer_group)

    # TODO: 实现 Kafka 消费
    outputs = {"consumed_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
