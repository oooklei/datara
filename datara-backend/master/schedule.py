"""定时调度线程（F46 §9.1）：10s 扫描 t_wf_schedule(online) → croniter 到期 → 写 START_PROCESS 命令。

自创差异（设计 §2）：不用 Quartz，master 内 croniter 计算下次触发（表达式 6 段含秒，
`?` 自动替换为 `*`）；next_fire_time 进程内缓存，crontab/更新时间变化即重算。
"""

from datetime import datetime, timedelta

from croniter import croniter

from common.db import new_session
from common.log import get_logger
from common.models import Command, WfDefinition, WfSchedule, now

logger = get_logger("master.schedule")


def _next_fire(crontab: str, base: datetime) -> datetime:
    """croniter 计算下次触发（`?` → `*`；6 段含秒）。"""
    return croniter(crontab.replace("?", "*"), base).get_next(datetime)


def _fire(session, schedule: WfSchedule, planned: datetime) -> None:
    """到期触发：写 START_PROCESS 命令（run_mode=schedule，schedule_time=计划时刻）。"""
    definition = (
        session.query(WfDefinition).filter(WfDefinition.code == schedule.wf_code).first()
    )
    session.add(
        Command(
            command_type="START_PROCESS",
            command_param={
                "wfCode": schedule.wf_code,
                "wfVersion": definition.version if definition is not None else 0,
                "runMode": "schedule",
                "scheduleTime": planned.strftime("%Y-%m-%d %H:%M:%S"),
                "priority": schedule.priority,
                "failRetryTimes": schedule.fail_retry_times,
                "failRetryInterval": schedule.fail_retry_interval,
            },
            priority=schedule.priority,
        )
    )
    logger.info("定时触发: schedule=%s wf=%s planned=%s", schedule.id, schedule.wf_code, planned)


def _tick(cache: dict) -> None:
    """单轮扫描：有效期过滤 → 缓存 next_fire_time → 到期触发并前推。"""
    session = new_session()
    try:
        schedules = session.query(WfSchedule).filter(WfSchedule.state == "online").all()
        current = now()
        for schedule in schedules:
            if schedule.start_time is not None and current < schedule.start_time:
                continue
            if schedule.end_time is not None and current > schedule.end_time:
                continue
            entry = cache.get(schedule.id)
            if entry is None or entry["crontab"] != schedule.crontab \
                    or entry["update_time"] != schedule.update_time:
                entry = {"crontab": schedule.crontab,
                         "update_time": schedule.update_time,
                         "next": _next_fire(schedule.crontab, current)}
                cache[schedule.id] = entry
                logger.info("定时计划装载: schedule=%s crontab=%s next=%s",
                            schedule.id, schedule.crontab, entry["next"])
            if current >= entry["next"]:
                planned = entry["next"]
                _fire(session, schedule, planned)
                entry["next"] = _next_fire(schedule.crontab, current + timedelta(seconds=1))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def schedule_loop(stop, gate) -> None:
    """定时调度线程主循环（仅 leader 执行）。"""
    logger.info("定时调度线程启动（10s/轮）")
    cache: dict = {}
    while not stop.is_set():
        if gate.check():
            try:
                _tick(cache)
            except Exception as exc:  # noqa: BLE001 服务循环防崩
                logger.error("定时调度异常: %s", exc)
        stop.wait(10)
    logger.info("定时调度线程退出")
