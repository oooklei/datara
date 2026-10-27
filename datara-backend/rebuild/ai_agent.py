"""Server-owned LLM conversation contract for the Datara R8-B assistant."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
        },
    }


_PROJECT = {"project_id": {"type": "integer", "minimum": 1}}
AI_TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    _tool("search_schema", "检索项目元数据表和字段", {**_PROJECT, "keyword": {"type": "string"}, "include_columns": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["project_id"]),
    _tool("validate_sql", "校验 SQL 并返回问题", {**_PROJECT, "datasource_id": {"type": "integer"}, "sql": {"type": "string"}, "dialect": {"type": "string"}}, ["project_id", "datasource_id", "sql"]),
    _tool("run_sql", "通过 Datara 统一执行链执行 SQL", {**_PROJECT, "datasource_id": {"type": "integer"}, "sql": {"type": "string"}, "row_limit": {"type": "integer", "maximum": 1000}, "timeout_ms": {"type": "integer", "maximum": 30000}}, ["project_id", "datasource_id", "sql"]),
    _tool("get_workflow", "读取工作流定义", {**_PROJECT, "workflow_id": {"type": "integer"}, "name": {"type": "string"}, "version": {"type": "integer"}}, ["project_id"]),
    _tool("validate_workflow", "校验工作流定义", {**_PROJECT, "workflow_id": {"type": "integer"}, "version": {"type": "integer"}, "definition": {"type": "object"}}, ["project_id"]),
    _tool("inspect_workflow_run", "诊断工作流运行实例", {**_PROJECT, "run_id": {"type": "string"}, "attempt": {"type": "integer"}, "include_tasks": {"type": "boolean"}}, ["project_id", "run_id"]),
    _tool("get_task_metrics", "查询真实任务统计", {**_PROJECT, "run_id": {"type": "string"}, "time_window": {"type": "object"}, "group_by": {"type": "string", "enum": ["task_type", "status", "day"]}}, ["project_id"]),
    _tool("get_lineage", "查询表或字段血缘", {**_PROJECT, "entity_type": {"type": "string", "enum": ["TABLE", "COLUMN"]}, "entity": {"type": "string"}, "direction": {"type": "string", "enum": ["UPSTREAM", "DOWNSTREAM", "BOTH"]}, "depth": {"type": "integer", "maximum": 5}}, ["project_id", "entity_type", "entity"]),
)


class AgentRequestError(ValueError):
    pass


def complete_agent_turn(
    *,
    config: Mapping[str, Any],
    project_id: int,
    messages: Sequence[Mapping[str, Any]],
    transport: Callable[[Mapping[str, Any], list[dict[str, Any]], Sequence[Mapping[str, Any]]], Mapping[str, Any]],
) -> dict[str, Any]:
    if not messages or len(messages) > 30:
        raise AgentRequestError("messages must contain 1..30 items")
    safe_messages: list[dict[str, Any]] = [{
        "role": "system",
        "content": (
            "你是 Datara 数据治理助手。只能使用服务端提供的八个工具处理真实系统数据；"
            f"当前项目 project_id={project_id}，每次工具调用必须使用该 project_id；"
            "不得声称执行未发生的动作，工具错误须如实说明。"
        ),
    }]
    for item in messages:
        role = item.get("role")
        if role not in {"user", "assistant", "tool"}:
            raise AgentRequestError("unsupported message role")
        message = dict(item)
        content = message.get("content")
        if content is not None and (not isinstance(content, str) or len(content) > 20_000):
            raise AgentRequestError("message content must be a string with at most 20000 characters")
        safe_messages.append(message)
    response = dict(transport(config, safe_messages, AI_TOOL_DEFINITIONS))
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        raise RuntimeError("LLM provider returned no choice")
    message = choices[0].get("message")
    if not isinstance(message, Mapping) or message.get("role") != "assistant":
        raise RuntimeError("LLM provider returned an invalid assistant message")
    return {"message": dict(message), "model": response.get("model") or config.get("model"), "usage": response.get("usage") or {}}
