"""项目级告警规则与触发记录（§10.10 R6 告警桥接）。

海豚告警组 / 告警实例 / 告警插件一律不接入（``alert/`` 模块整体不用）。
datara 侧只保留两件事：

- **规则**：按项目 / 工作流 / 触发条件（``failure``、``timeout``）+ 通道
  （``system``、``email``、``webhook``）配置，见 ``OrchestrationAlarmRuleRecord``。
- **触发记录**：命中规则后写 ``OrchestrationAlarmRecord``（审计 D2），海豚侧
  不出现告警页。

**失败感知**：``dispatch_alarm_scan`` 轮询海豚 ``WorkflowInstanceController``
状态，识别 ``FAILURE`` 与运行超时；命中规则即走既有 ``alert/channels.py``
通道发送。短信未接供应商接口，通道枚举不含短信（``alert/channels.py``
对未知通道直接抛 ``DeliveryError``）。

失败重试耗尽在海豚侧最终表现为实例 ``FAILURE``，归入 ``failure`` 触发条件，
不再单列。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Iterable

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from alert.channels import DeliveryError, deliver
from common.config import Settings, get_settings
from common.models import now
from rebuild.common.db import Base
from rebuild.project.models import ProjectRecord

TRIGGER_FAILURE = "failure"
TRIGGER_TIMEOUT = "timeout"
TRIGGERS = (TRIGGER_FAILURE, TRIGGER_TIMEOUT)

CHANNEL_SYSTEM = "system"
CHANNEL_EMAIL = "email"
CHANNEL_WEBHOOK = "webhook"
CHANNELS = (CHANNEL_SYSTEM, CHANNEL_EMAIL, CHANNEL_WEBHOOK)

# 海豚 WorkflowInstance.state 枚举（实测全集见权威 §10.11 状态映射）。
DS_STATE_FAILURE = "FAILURE"

SCAN_PAGE_SIZE = 100


class OrchestrationAlarmRuleRecord(Base):
    __tablename__ = "rebuild_orchestration_alarm_rule"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "workflow_definition_code", "trigger", name="uq_orch_alarm_rule"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    # 0 = 项目下全部工作流；非 0 为海豚 workflowDefinitionCode。
    workflow_definition_code: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    # trigger=timeout 时必填；failure 规则忽略该字段。
    timeout_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel: Mapped[str] = mapped_column(String(16), default=CHANNEL_SYSTEM, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("rebuild_user.id"), nullable=False, index=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class OrchestrationAlarmRecord(Base):
    __tablename__ = "rebuild_orchestration_alarm_record"
    __table_args__ = (
        UniqueConstraint("rule_id", "instance_id", "trigger", name="uq_orch_alarm_record"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_orchestration_alarm_rule.id"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    instance_id: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_definition_code: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    channel: Mapped[str] = mapped_column(String(16), default=CHANNEL_SYSTEM, nullable=False)
    # wait/sent/fail：只有通道确认成功才进 sent（见 alert/channels.py 语义）。
    state: Mapped[str] = mapped_column(String(16), default="wait", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


def _ds_datetime(value: Any) -> datetime | None:
    """解析海豚 ``startTime`` 字符串；无法解析返回 None。"""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not isinstance(value, str) or not value.strip():
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


class OrchestrationAlarmRepository:
    """告警规则与触发记录的持久化入口。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_rules(self, project_id: int, *, include_disabled: bool = True) -> list[OrchestrationAlarmRuleRecord]:
        stmt = select(OrchestrationAlarmRuleRecord).where(
            OrchestrationAlarmRuleRecord.project_id == project_id
        )
        if not include_disabled:
            stmt = stmt.where(OrchestrationAlarmRuleRecord.enabled.is_(True))
        stmt = stmt.order_by(OrchestrationAlarmRuleRecord.id)
        return list(self.session.scalars(stmt))

    def get_rule(self, rule_id: int) -> OrchestrationAlarmRuleRecord | None:
        return self.session.get(OrchestrationAlarmRuleRecord, rule_id)

    def find_rule(
        self, project_id: int, workflow_definition_code: int, trigger: str
    ) -> OrchestrationAlarmRuleRecord | None:
        """按唯一键 (project_id, workflow_definition_code, trigger) 定位规则。"""
        stmt = select(OrchestrationAlarmRuleRecord).where(
            OrchestrationAlarmRuleRecord.project_id == project_id,
            OrchestrationAlarmRuleRecord.workflow_definition_code == workflow_definition_code,
            OrchestrationAlarmRuleRecord.trigger == trigger,
        )
        return self.session.scalars(stmt).first()

    def create_rule(
        self,
        *,
        project_id: int,
        workflow_definition_code: int,
        trigger: str,
        channel: str,
        timeout_minutes: int | None,
        owner_id: int,
    ) -> OrchestrationAlarmRuleRecord:
        record = OrchestrationAlarmRuleRecord(
            project_id=project_id,
            workflow_definition_code=workflow_definition_code,
            trigger=trigger,
            timeout_minutes=timeout_minutes,
            channel=channel,
            owner_id=owner_id,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def update_rule(
        self,
        record: OrchestrationAlarmRuleRecord,
        *,
        channel: str | None = None,
        enabled: bool | None = None,
        timeout_minutes: int | None = None,
        workflow_definition_code: int | None = None,
    ) -> OrchestrationAlarmRuleRecord:
        if channel is not None:
            record.channel = channel
        if enabled is not None:
            record.enabled = enabled
        if timeout_minutes is not None:
            record.timeout_minutes = timeout_minutes
        if workflow_definition_code is not None:
            record.workflow_definition_code = workflow_definition_code
        self.session.flush()
        return record

    def delete_rule(self, record: OrchestrationAlarmRuleRecord) -> None:
        self.session.delete(record)
        self.session.flush()

    def list_records(self, project_id: int, *, limit: int = 100) -> list[OrchestrationAlarmRecord]:
        stmt = (
            select(OrchestrationAlarmRecord)
            .where(OrchestrationAlarmRecord.project_id == project_id)
            .order_by(OrchestrationAlarmRecord.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def has_triggered(self, rule_id: int, instance_id: int, trigger: str) -> bool:
        """去重：同一规则对同一实例的同一触发条件只发一次。"""
        return (
            self.session.scalar(
                select(OrchestrationAlarmRecord.id).where(
                    OrchestrationAlarmRecord.rule_id == rule_id,
                    OrchestrationAlarmRecord.instance_id == instance_id,
                    OrchestrationAlarmRecord.trigger == trigger,
                )
            )
            is not None
        )

    def add_record(
        self,
        *,
        rule: OrchestrationAlarmRuleRecord,
        instance_id: int,
        trigger: str,
        title: str,
        content: str,
        state: str,
    ) -> OrchestrationAlarmRecord:
        record = OrchestrationAlarmRecord(
            rule_id=rule.id,
            project_id=rule.project_id,
            instance_id=instance_id,
            workflow_definition_code=rule.workflow_definition_code,
            trigger=trigger,
            title=title,
            content=content,
            channel=rule.channel,
            state=state,
        )
        self.session.add(record)
        self.session.flush()
        return record


def rule_matches(rule: OrchestrationAlarmRuleRecord, definition_code: int) -> bool:
    """规则是否覆盖该工作流；``workflow_definition_code == 0`` 表示全部。"""
    return rule.workflow_definition_code == 0 or rule.workflow_definition_code == definition_code


def _ds_project_name(project: ProjectRecord) -> str:
    return f"datara-{project.id}-{project.name}"[:100]


def _send(rule: OrchestrationAlarmRuleRecord, title: str, content: str, settings: Settings) -> str:
    """按规则通道发送；返回最终状态 ``sent`` / ``fail``（``system`` 直接 sent）。"""
    try:
        deliver(rule.channel, title, content, settings)
    except DeliveryError:
        return "fail"
    return "sent"


def dispatch_alarm_scan(
    session_factory: sessionmaker[Session],
    make_ds_client: Callable[[], Any],
    settings: Settings | None = None,
) -> dict[str, int]:
    """扫描全部项目，感知海豚失败/超时并按规则发送。

    返回 ``{"rules": 命中规则数, "sent": 发送成功数, "failed": 发送失败数}``。
    单项目失败只记日志，不中断整体扫描。
    """
    cfg = settings or get_settings()
    counts = {"rules": 0, "sent": 0, "failed": 0}
    now_ts = datetime.now()
    with session_factory() as session:
        projects = list(session.scalars(select(ProjectRecord)))
    for project in projects:
        try:
            with session_factory() as session:
                rules = OrchestrationAlarmRepository(session).list_rules(project.id, include_disabled=False)
            if not rules:
                continue
            try:
                ds_project = make_ds_client().ensure_project(_ds_project_name(project), project.description or "")
            except Exception:  # noqa: BLE001 - 单项目失败不中断扫描
                continue
            project_code = ds_project.get("code") if isinstance(ds_project, dict) else None
            if project_code is None:
                continue
            for trigger in TRIGGERS:
                matched_rules = [rule for rule in rules if rule.trigger == trigger]
                if not matched_rules:
                    continue
                for row in _iter_instances(make_ds_client, project_code, trigger):
                    definition_code = int(row.get("workflowDefinitionCode") or 0)
                    for rule in matched_rules:
                        if not rule_matches(rule, definition_code):
                            continue
                        _dispatch_rule(session_factory, rule, row, now_ts, cfg, counts)
        except Exception as exc:  # noqa: BLE001 - 单项目失败不中断扫描
            continue
    return counts


def _iter_instances(make_ds_client: Callable[[], Any], project_code: Any, trigger: str) -> Iterable[dict[str, Any]]:
    """按触发条件取海豚实例页：failure 取 FAILURE 态，timeout 取运行态。"""
    client = make_ds_client()
    state_type = DS_STATE_FAILURE if trigger == TRIGGER_FAILURE else None
    query: dict[str, Any] = {"pageNo": 1, "pageSize": SCAN_PAGE_SIZE}
    if state_type:
        query["stateType"] = state_type
    payload = client.call("GET", f"/projects/{project_code}/workflow-instances", query=query)
    rows = payload.get("totalList") if isinstance(payload, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _dispatch_rule(
    session_factory: sessionmaker[Session],
    rule: OrchestrationAlarmRuleRecord,
    row: dict[str, Any],
    now_ts: datetime,
    cfg: Settings,
    counts: dict[str, int],
) -> None:
    instance_id = int(row.get("id") or 0)
    if not instance_id:
        return
    name = str(row.get("name") or f"instance-{instance_id}")
    if rule.trigger == TRIGGER_TIMEOUT and rule.timeout_minutes:
        started = _ds_datetime(row.get("startTime"))
        elapsed = (now_ts - started).total_seconds() / 60.0 if started else 0.0
        if elapsed <= rule.timeout_minutes:
            return
    title = f"[Datara 告警] 工作流实例 {name} {rule.trigger}"
    content = (
        f"项目实例 {instance_id}（{name}）命中告警条件 {rule.trigger}，"
        f"通道 {rule.channel}，请在工作流运行监控中查看。"
    )
    with session_factory() as session:
        repository = OrchestrationAlarmRepository(session)
        if repository.has_triggered(rule.id, instance_id, rule.trigger):
            return
        state = _send(rule, title, content, cfg)
        repository.add_record(
            rule=rule,
            instance_id=instance_id,
            trigger=rule.trigger,
            title=title,
            content=content,
            state=state,
        )
        session.commit()
    counts["rules"] += 1
    if state == "sent":
        counts["sent"] += 1
    else:
        counts["failed"] += 1
