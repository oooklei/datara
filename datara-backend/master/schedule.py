"""Leader-only cron dispatcher with per-schedule policy enforcement."""

from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter

from common.db import new_session
from common.log import get_logger
from common.models import Command, WorkflowInstance, WfDefinition, WfSchedule, now
from master import state

logger = get_logger("master.schedule")
SCAN_SECONDS = 10
MAX_MISFIRE_CATCHUP = 100


def _next_fire(crontab: str, base: datetime) -> datetime:
    """Return next cron instant; base must carry the schedule's timezone."""
    return croniter(crontab.replace("?", "*"), base).get_next(datetime)


def _schedule_now(schedule: WfSchedule) -> datetime:
    local_now = now().astimezone()
    return local_now.astimezone(ZoneInfo(schedule.timezone or "Asia/Shanghai"))


def _active_for_schedule(session, schedule: WfSchedule) -> int:
    active = session.query(WorkflowInstance).filter(
        WorkflowInstance.wf_code == schedule.wf_code,
        WorkflowInstance.run_mode == "schedule",
        WorkflowInstance.state.in_(state.INSTANCE_RUNNING_STATES),
    ).all()
    return sum(
        1 for instance in active
        if not isinstance(instance.variables, dict)
        or instance.variables.get("scheduleId") is None
        or str(instance.variables.get("scheduleId")) == str(schedule.id)
    )


def _pending_for_schedule(session, schedule: WfSchedule) -> int:
    """Count durable queued START_PROCESS commands before they become instances."""
    commands = session.query(Command).filter(
        Command.command_type == "START_PROCESS",
        Command.state.in_(("wait", "execute")),
    ).all()
    return sum(
        1 for command in commands
        if isinstance(command.command_param, dict)
        and command.command_param.get("runMode") == "schedule"
        and str(command.command_param.get("wfCode")) == str(schedule.wf_code)
        and (
            command.command_param.get("scheduleId") is None
            or str(command.command_param.get("scheduleId")) == str(schedule.id)
        )
    )


def _fire(session, schedule: WfSchedule, planned: datetime) -> None:
    """Persist one START_PROCESS command with enough identity for concurrency accounting."""
    definition = session.query(WfDefinition).filter(WfDefinition.code == schedule.wf_code).first()
    session.add(
        Command(
            command_type="START_PROCESS",
            command_param={
                "wfCode": schedule.wf_code,
                "wfVersion": definition.version if definition is not None else 0,
                "runMode": "schedule",
                "scheduleId": schedule.id,
                "scheduleTime": planned.strftime("%Y-%m-%d %H:%M:%S"),
                "priority": schedule.priority,
                "failRetryTimes": schedule.fail_retry_times,
                "failRetryInterval": schedule.fail_retry_interval,
            },
            priority=schedule.priority,
        )
    )
    logger.info("定时触发: schedule=%s wf=%s planned=%s", schedule.id, schedule.wf_code, planned)


def _due_times(schedule: WfSchedule, first: datetime, current: datetime) -> tuple[list[datetime], datetime, bool]:
    due: list[datetime] = []
    cursor = first
    while cursor <= current and len(due) <= MAX_MISFIRE_CATCHUP:
        due.append(cursor)
        cursor = _next_fire(schedule.crontab, cursor)
    return due, cursor, len(due) > MAX_MISFIRE_CATCHUP


def _tick(cache: dict) -> None:
    """Scan plans, apply misfire/concurrency rules, then commit command batch."""
    session = new_session()
    try:
        schedules = session.query(WfSchedule).filter(WfSchedule.state == "online").all()
        for schedule in schedules:
            current = _schedule_now(schedule)
            zone = current.tzinfo
            if schedule.start_time is not None and current < schedule.start_time.replace(tzinfo=zone):
                continue
            if schedule.end_time is not None and current > schedule.end_time.replace(tzinfo=zone):
                continue
            entry = cache.get(schedule.id)
            if (
                entry is None
                or entry["crontab"] != schedule.crontab
                or entry["update_time"] != schedule.update_time
                or entry["timezone"] != schedule.timezone
            ):
                entry = {
                    "crontab": schedule.crontab,
                    "update_time": schedule.update_time,
                    "timezone": schedule.timezone,
                    # update_time advances when a plan is activated or edited, so it
                    # is the durable lower bound for restart-time misfire recovery.
                    "next": _next_fire(
                        schedule.crontab,
                        (schedule.update_time or now()).replace(tzinfo=zone),
                    ),
                }
                cache[schedule.id] = entry
                continue

            if entry["next"] > current:
                continue
            due, following, overflow = _due_times(schedule, entry["next"], current)
            active = _active_for_schedule(session, schedule)
            pending = _pending_for_schedule(session, schedule)
            occupied = active + pending
            limit = max(1, int(schedule.max_running_instances or 1))
            concurrency = schedule.concurrency_policy or "ALLOW"
            misfire = schedule.misfire_policy or "FIRE_ONCE"

            if concurrency == "QUEUE" and occupied > 0:
                # Keep the oldest due instant; it will be dispatched once capacity frees.
                continue
            if concurrency == "FORBID" and occupied > 0:
                entry["next"] = following
                continue
            capacity = max(0, limit - occupied)
            if concurrency in {"FORBID", "QUEUE"}:
                capacity = min(1, capacity)
            if capacity == 0:
                if concurrency == "QUEUE":
                    continue
                entry["next"] = following
                continue

            if misfire == "SKIP":
                fired: list[datetime] = [due[0]] if due and due[0] == current else []
            elif misfire == "FIRE_ONCE":
                fired = [due[-1]] if due else []
            else:  # FIRE_ALL_LIMITED
                fired = due[:MAX_MISFIRE_CATCHUP]
            fired = fired[:capacity]
            for planned in fired:
                _fire(session, schedule, planned)
            # QUEUE retains unserved occurrences; other policies consume the missed window.
            if misfire == "SKIP":
                entry["next"] = following
            elif concurrency == "QUEUE" and len(fired) < len(due):
                entry["next"] = due[len(fired)] if fired else due[0]
            else:
                entry["next"] = following
            if overflow and misfire == "FIRE_ALL_LIMITED":
                logger.warning("misfire 补发达到上限 %s: schedule=%s", MAX_MISFIRE_CATCHUP, schedule.id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def schedule_loop(stop, gate) -> None:
    """Run timer scans only while this process holds the master gate."""
    logger.info("定时调度线程启动（%ss/轮）", SCAN_SECONDS)
    cache: dict = {}
    while not stop.is_set():
        if gate.check():
            try:
                _tick(cache)
            except Exception as exc:  # noqa: BLE001 service loop must survive an invalid plan
                logger.error("定时调度异常: %s", exc)
        stop.wait(SCAN_SECONDS)
    logger.info("定时调度线程退出")
