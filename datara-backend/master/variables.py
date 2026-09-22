"""变量解析链与内置时间变量（F48/F49，设计文档 §10）。

四级优先：节点参数(node.data.params) > 工作流变量(t_wf_variable) > 环境组(t_env_group)
> 全局参数(t_global_param)；运行时变量 run.instanceId/run.loopIter 引擎注入最高不可覆盖。

I7 C21 运行时注入层（设计 §3.1）：变量组件节点执行时将变量表写入实例运行时变量存储
（Redis Hash run_vars:{instance_id}），解析链在节点参数之后、定义级工作流变量之前读取
（覆盖开关在注入时落地：开=覆盖定义级同名变量，关=仅当未定义时生效）。

- 占位语法 ${var}（四级引用）；$[yyyyMMdd...]（内置时间变量，基准=实例 schedule_time 或启动时刻）
- ${tmp.<name>}：t_tmp_data 临时工作数据引用（I4 §5.3，仅查同实例；无父子实例机制）
- 条件/分支表达式先做占位替换，再经 simpleeval 安全求值（禁 import/属性访问）
- 变量快照 var_snapshot：{名: {value, source, resolved}}，明文不脱敏（09-18 裁定）
- 替换发生在 master 激活节点时（param_resolved 随消息下发，worker 零解析）
"""

import re
from datetime import datetime
from typing import Optional

from simpleeval import simple_eval

from common import queue as redis_queue
from common.db import new_session
from common.log import get_logger
from common.models import EnvGroup, GlobalParam, TmpData, WfVariable
from common.vars_render import MAX_DEPTH, TIME_RE, VAR_RE, time_var  # 渲染核心下沉共用（I10）

logger = get_logger("master.variables")

# 运行时变量（最高优先，不可覆盖）
RUNTIME_SOURCE = "运行时"

# I7 C21 运行时注入层（Redis Hash；实例收口清除 + 7 天 TTL 兜底防泄漏）
RUN_VARS_SOURCE = "变量组件(C21)"
RUN_VARS_TTL_SEC = 7 * 86400


def run_vars_key(instance_id: str) -> str:
    return "run_vars:%s" % instance_id


def set_run_vars(instance_id: str, items: dict) -> int:
    """C21 变量组件注入：批量写实例运行时变量（Redis Hash）。返回写入字段数。"""
    if not items:
        return 0
    client = redis_queue.get_client()
    mapping = {str(k): str(v) for k, v in items.items()}
    client.hset(run_vars_key(instance_id), mapping=mapping)
    client.expire(run_vars_key(instance_id), RUN_VARS_TTL_SEC)
    logger.info("运行时变量注入: instance=%s names=%s", instance_id, sorted(mapping))
    return len(mapping)


def get_run_vars(instance_id: str) -> dict:
    """读实例运行时注入变量（Redis 不可达时降级空 dict，不阻断解析链）。"""
    try:
        client = redis_queue.get_client()
        return dict(client.hgetall(run_vars_key(instance_id)) or {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("运行时变量读取失败（降级跳过注入层）: instance=%s %r", instance_id, exc)
        return {}


def clear_run_vars(instance_id: str) -> None:
    """实例收口清除运行时注入层（防 Redis 残留泄漏）。"""
    try:
        redis_queue.get_client().delete(run_vars_key(instance_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("运行时变量清除失败: instance=%s %r", instance_id, exc)


def load_levels(session, wf_code: int, env_group_id: Optional[int] = None) -> dict:
    """加载三级静态变量层：{"workflow": {...}, "env": {...}, "global": {...}}（实例级一次加载）。"""
    workflow = {
        v.name: (v.value or "")
        for v in session.query(WfVariable).filter(WfVariable.wf_code == wf_code).all()
    }
    env = {}
    if env_group_id:
        group = session.get(EnvGroup, int(env_group_id))
        if group is not None and isinstance(group.config, dict):
            # I12-m1（评审）：None 值渲染空串（与全链 None→空串口径统一；workflow/global 层由 `or ""` 兜底）
            env = {k: ("" if v is None else str(v)) for k, v in group.config.items() if isinstance(k, str)}
    glob = {
        g.name: (g.value or "")
        for g in session.query(GlobalParam).all()
    }
    return {"workflow": workflow, "env": env, "global": glob}


def eval_expr(expr: str, scope: dict, resolver: Optional["VarResolver"] = None,
              loop_iter: int = 0) -> object:
    """表达式安全求值：先占位替换再 simpleeval；空表达式恒真；异常视为 False 并留日志。

    resolver 传入时 ${var}/$[时间] 先做占位替换（如 `${cnt} > 0` → `3 > 0`）；
    scope 额外提供下划线别名（run_loopIter / wf_period 等），兼容表达式中直接写变量名。
    """
    if expr is None:
        return True
    text = str(expr).strip()
    if not text:
        return True
    if resolver is not None:
        text = resolver.resolve_text(text, {}, loop_iter, {})
    aliases = {k.replace(".", "_"): v for k, v in scope.items() if isinstance(k, str)}
    try:
        return simple_eval(text, names={**scope, **aliases})
    except Exception as exc:  # noqa: BLE001 求值失败按 False（不阻断引擎）
        logger.warning("表达式求值失败（按 False 处理）: %r → %s", expr, exc)
        return False


class VarResolver:
    """实例级变量解析器（Runnable 持有，激活节点时调用）。"""

    def __init__(self, instance_id: str, wf_code: int, levels: dict, base_time: datetime):
        self.instance_id = instance_id
        self.wf_code = wf_code
        self.levels = levels  # {"workflow": {}, "env": {}, "global": {}}
        self.base_time = base_time
        self._run_cache: Optional[dict] = None  # C21 注入层缓存（激活节点前刷新）

    # ---- C21 运行时注入层 ----

    def refresh_run_vars(self) -> None:
        """激活节点前刷新注入层缓存（variable 节点运行中写入，下游激活需读到最新）。"""
        self._run_cache = get_run_vars(self.instance_id)

    def run_vars_snapshot(self) -> dict:
        """当前注入层快照（表达式作用域并入；未刷新时惰性读取一次）。"""
        if self._run_cache is None:
            self.refresh_run_vars()
        return dict(self._run_cache or {})

    # ---- 快照 ----

    def _snap(self, snapshot: dict, name: str, value: object, source: str, resolved: bool) -> None:
        snapshot.setdefault(name, {"value": value, "source": source, "resolved": resolved})

    def runtime_scope(self, loop_iter: int = 0) -> dict:
        """运行时变量作用域（表达式求值用；${run.*} 替换同样取此值）。"""
        return {"run.instanceId": self.instance_id, "run.loopIter": loop_iter}

    def _resolve_tmp(self, name: str, match: "re.Match", snapshot: dict) -> str:
        """${tmp.<name>} → t_tmp_data 同实例查找（I4 设计文档 §5.3）。

        - kind=table → 临时表名（同库可 FROM/JOIN）；kind=file → 共享卷文件绝对路径
        - kind=resultset → 有 ref 用 ref，否则空串+告警（仅预览无实体，SQL 语境不可用）
        - 未注册/已过期 → 保留原样 + 告警（对齐变量链容错口径）
        - 无父子实例机制，仅查同实例；每次短会话即查即关（节点激活低频，不做缓存）
        """
        raw = match.group(0)
        session = new_session()
        try:
            row = (
                session.query(TmpData)
                .filter(TmpData.instance_id == self.instance_id, TmpData.name == name)
                .first()
            )
        finally:
            session.close()
        if row is None:
            logger.warning("${%s} 临时数据未注册（实例 %s），保留原样", name, self.instance_id)
            self._snap(snapshot, raw, raw, "临时数据", False)
            return raw
        if row.expire_at is not None and row.expire_at < datetime.now():
            logger.warning("${%s} 临时数据已过期（实例 %s），保留原样", name, self.instance_id)
            self._snap(snapshot, raw, raw, "临时数据", False)
            return raw
        ref = row.ref or ""
        if row.kind == "resultset" and not ref:
            logger.warning("${%s} 结果集引用无实体（仅预览），替换为空串", name)
        if ref and row.kind in ("table", "resultset"):
            # 临时表名含 instance_id 前缀（数字开头/连字符），SQL 裸标识符不合法 → 反引号包裹
            ref = "`%s`" % ref
        self._snap(snapshot, raw, ref, "临时数据(%s)" % row.kind, True)
        return ref

    # ---- 单值解析 ----

    def resolve_text(self, text: str, node_params: dict, loop_iter: int, snapshot: dict, depth: int = 0) -> str:
        """解析单值：$[] 时间变量 + ${} 四级占位；未解析占位保留原样并记快照。"""
        if not isinstance(text, str) or depth >= MAX_DEPTH:
            return text if isinstance(text, str) else str(text)

        def _time(match: re.Match) -> str:
            inner = match.group(1)
            # C21 兜底（门 1 实测修复）：$[wf.*] 属混用占位语法（非日期模板），
            # 转按四级变量链解析（节点参数→注入层→工作流/环境/全局），unresolved 保留原样
            if inner.strip().startswith("wf."):
                rewrapped = re.match(r"\$\[([^\]]+)\]", match.group(0))
                if rewrapped is not None:
                    return _var(rewrapped)
            resolved = time_var(inner, self.base_time)
            self._snap(snapshot, "$[%s]" % inner, resolved, "时间变量", True)
            return resolved

        def _var(match: re.Match) -> str:
            name = match.group(1).strip()
            # I12-D5：空值（None）统一渲染为空串（str(None)="None" 会把字面量 None 拼进 SQL/参数）
            def _to_text(v) -> str:
                return "" if v is None else str(v)
            if name.startswith("run."):
                value = self.runtime_scope(loop_iter).get(name)
                self._snap(snapshot, name, value, RUNTIME_SOURCE, True)
                return _to_text(value)
            if name.startswith("tmp."):
                return self._resolve_tmp(name[4:].strip(), match, snapshot)
            if name in node_params:
                value = node_params[name]
                self._snap(snapshot, name, value, "节点参数", True)
                return _to_text(value)
            # I7 C21 注入层：节点参数之后、定义级工作流变量之前（覆盖开关语义在注入时落地）
            run_cache = self._run_cache if self._run_cache is not None else {}
            if name in run_cache:
                value = run_cache[name]
                self._snap(snapshot, name, value, RUN_VARS_SOURCE, True)
                return _to_text(value)
            for level, source in (("workflow", "工作流变量"), ("env", "环境组"), ("global", "全局")):
                if name in self.levels[level]:
                    value = self.levels[level][name]
                    self._snap(snapshot, name, value, source, True)
                    # 低层值可能仍含占位/时间变量，递归解析
                    # I12-D5 补漏：此处原为 str(value)，None 值经 workflow/env/global 层仍渲染字面量
                    # "None"，与 run./节点参数/注入层路径（_to_text → 空串）口径不一致
                    return self.resolve_text(_to_text(value), node_params, loop_iter, snapshot, depth + 1)
            self._snap(snapshot, match.group(0), match.group(0), "unresolved", False)
            return match.group(0)  # 未解析保留原样

        return TIME_RE.sub(_time, VAR_RE.sub(_var, text))

    # ---- 参数树解析 ----

    def resolve_tree(self, obj: object, loop_iter: int, snapshot: dict,
                     skip_keys: tuple = (), depth: int = 0, node_params: Optional[dict] = None) -> object:
        """深遍历 dict/list/str 做占位替换（业务字段 + params 全量下发 param_resolved）。

        node_params 传入时业务字段中的 ${} 按四级链解析（节点参数优先，09-18 实测修复）。
        """
        if depth >= MAX_DEPTH:
            return obj
        if isinstance(obj, dict):
            return {
                k: (v if k in skip_keys
                    else self.resolve_tree(v, loop_iter, snapshot, skip_keys, depth + 1, node_params))
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [self.resolve_tree(v, loop_iter, snapshot, skip_keys, depth + 1, node_params)
                    for v in obj]
        if isinstance(obj, str):
            return self.resolve_text(obj, node_params or {}, loop_iter, snapshot)
        return obj

    def resolve_node(self, data: dict, loop_iter: int = 0) -> tuple:
        """节点参数解析入口：返回 (param_resolved, var_snapshot)。

        - data.params（ParamRow[] {key,value,source}）→ dict 后参与四级链并下发
        - 业务平铺字段（sql/script/...）同步替换（branches 等结构字段跳过）
        """
        snapshot: dict = {}
        rows = data.get("params")
        node_params: dict = {}
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("key"):
                    node_params[str(row["key"])] = str(row.get("value") or "")
        resolved = self.resolve_tree(data, loop_iter, snapshot, skip_keys=("branches",),
                                     node_params=node_params)
        if isinstance(resolved, dict):
            resolved = dict(resolved)
            resolved["params"] = {
                k: self.resolve_text(v, node_params, loop_iter, snapshot) for k, v in node_params.items()
            } if node_params else {}
        return resolved, snapshot
