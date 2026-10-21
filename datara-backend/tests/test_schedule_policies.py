from datetime import datetime

from common.models import WfSchedule
from master import schedule


def _plan(db_session, **kwargs):
    values = {
        "wf_code": 701,
        "name": "test",
        "crontab": "* * * * * *",
        "state": "online",
        "priority": 3,
        "misfire_policy": "FIRE_ONCE",
        "concurrency_policy": "ALLOW",
        "max_running_instances": 100,
        "timezone": "Asia/Shanghai",
        "update_time": datetime(2026, 10, 19, 8, 0, 0),
    }
    values.update(kwargs)
    plan = WfSchedule(**values)
    db_session.add(plan)
    db_session.commit()
    return plan


def _entry(plan, next_fire):
    return {
        plan.id: {
            "crontab": plan.crontab,
            "update_time": plan.update_time,
            "timezone": plan.timezone,
            "next": next_fire,
        }
    }


def test_misfire_policies_fire_once_skip_or_catch_up(monkeypatch, db_session):
    fired = []
    monkeypatch.setattr(schedule, "new_session", lambda: db_session)
    current = datetime(2026, 10, 19, 8, 0, 5, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(schedule, "_schedule_now", lambda _plan: current)
    monkeypatch.setattr(schedule, "_active_for_schedule", lambda *_: 0)
    monkeypatch.setattr(schedule, "_fire", lambda _session, plan, planned: fired.append((plan.id, planned)))

    plans = [
        _plan(db_session, misfire_policy="FIRE_ONCE"),
        _plan(db_session, misfire_policy="SKIP"),
        _plan(db_session, misfire_policy="FIRE_ALL_LIMITED"),
    ]
    cache = {
        plan.id: {
            "crontab": plan.crontab,
            "update_time": plan.update_time,
            "timezone": plan.timezone,
            "next": datetime(2026, 10, 19, 8, 0, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai")),
        }
        for plan in plans
    }

    schedule._tick(cache)

    by_plan = {plan.id: [when for plan_id, when in fired if plan_id == plan.id] for plan in plans}
    assert len(by_plan[plans[0].id]) == 1
    assert by_plan[plans[1].id] == [current]
    assert len(by_plan[plans[2].id]) == 6


def test_skip_policy_skips_a_single_overdue_occurrence(monkeypatch, db_session):
    fired = []
    monkeypatch.setattr(schedule, "new_session", lambda: db_session)
    current = datetime(2026, 10, 19, 8, 0, 30, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(schedule, "_schedule_now", lambda _plan: current)
    monkeypatch.setattr(schedule, "_active_for_schedule", lambda *_: 0)
    monkeypatch.setattr(schedule, "_fire", lambda _session, plan, planned: fired.append((plan.id, planned)))
    plan = _plan(db_session, crontab="* * * * * 0", misfire_policy="SKIP")
    first = datetime(2026, 10, 19, 8, 0, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    cache = _entry(plan, first)

    schedule._tick(cache)

    assert fired == []
    assert cache[plan.id]["next"] == datetime(
        2026, 10, 19, 8, 1, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai")
    )


def test_skip_normal_due_fires_at_exact_second(monkeypatch, db_session):
    fired = []
    monkeypatch.setattr(schedule, "new_session", lambda: db_session)
    current = datetime(2026, 10, 19, 8, 0, 1, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(schedule, "_schedule_now", lambda _plan: current)
    monkeypatch.setattr(schedule, "_active_for_schedule", lambda *_: 0)
    monkeypatch.setattr(schedule, "_fire", lambda _session, plan, planned: fired.append((plan.id, planned)))
    plan = _plan(db_session, misfire_policy="SKIP")
    cache = _entry(plan, current)

    schedule._tick(cache)

    assert fired == [(plan.id, current)]
    assert cache[plan.id]["next"] == datetime(
        2026, 10, 19, 8, 0, 2, tzinfo=schedule.ZoneInfo("Asia/Shanghai")
    )


def test_skip_current_equals_first_fires_at_minute_boundary(monkeypatch, db_session):
    fired = []
    monkeypatch.setattr(schedule, "new_session", lambda: db_session)
    current = datetime(2026, 10, 19, 8, 0, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(schedule, "_schedule_now", lambda _plan: current)
    monkeypatch.setattr(schedule, "_active_for_schedule", lambda *_: 0)
    monkeypatch.setattr(schedule, "_fire", lambda _session, plan, planned: fired.append((plan.id, planned)))
    plan = _plan(db_session, crontab="* * * * * 0", misfire_policy="SKIP")
    cache = _entry(plan, current)

    schedule._tick(cache)

    assert fired == [(plan.id, current)]
    assert cache[plan.id]["next"] == datetime(
        2026, 10, 19, 8, 1, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai")
    )


def test_skip_fires_when_latest_due_is_inside_scan_window(monkeypatch, db_session):
    fired = []
    monkeypatch.setattr(schedule, "new_session", lambda: db_session)
    current = datetime(2026, 10, 19, 8, 0, 9, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(schedule, "_schedule_now", lambda _plan: current)
    monkeypatch.setattr(schedule, "_active_for_schedule", lambda *_: 0)
    monkeypatch.setattr(schedule, "_fire", lambda _session, plan, planned: fired.append((plan.id, planned)))
    plan = _plan(db_session, crontab="* * * * * 0", misfire_policy="SKIP")
    first = datetime(2026, 10, 19, 8, 0, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    cache = _entry(plan, first)

    schedule._tick(cache)

    assert fired == [(plan.id, first)]


def test_skip_drops_occurrence_at_scan_window_boundary(monkeypatch, db_session):
    fired = []
    monkeypatch.setattr(schedule, "new_session", lambda: db_session)
    current = datetime(2026, 10, 19, 8, 0, 10, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(schedule, "_schedule_now", lambda _plan: current)
    monkeypatch.setattr(schedule, "_active_for_schedule", lambda *_: 0)
    monkeypatch.setattr(schedule, "_fire", lambda _session, plan, planned: fired.append((plan.id, planned)))
    plan = _plan(db_session, crontab="* * * * * 0", misfire_policy="SKIP")
    first = datetime(2026, 10, 19, 8, 0, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    cache = _entry(plan, first)

    schedule._tick(cache)

    assert fired == []
    assert cache[plan.id]["next"] == datetime(
        2026, 10, 19, 8, 1, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai")
    )


def test_queue_skip_advances_after_capacity_is_released(monkeypatch, db_session):
    fired = []
    occupied = {"value": 1}
    monkeypatch.setattr(schedule, "new_session", lambda: db_session)
    current = datetime(2026, 10, 19, 8, 0, 30, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(schedule, "_schedule_now", lambda _plan: current)
    monkeypatch.setattr(schedule, "_active_for_schedule", lambda *_: occupied["value"])
    monkeypatch.setattr(schedule, "_fire", lambda _session, plan, planned: fired.append((plan.id, planned)))
    plan = _plan(
        db_session,
        crontab="* * * * * 0",
        misfire_policy="SKIP",
        concurrency_policy="QUEUE",
    )
    first = datetime(2026, 10, 19, 8, 0, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    cache = _entry(plan, first)

    schedule._tick(cache)
    assert cache[plan.id]["next"] == first

    occupied["value"] = 0
    schedule._tick(cache)

    assert fired == []
    assert cache[plan.id]["next"] == datetime(
        2026, 10, 19, 8, 1, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai")
    )


def test_concurrency_forbid_skips_but_queue_retains_due_time(monkeypatch, db_session):
    fired = []
    monkeypatch.setattr(schedule, "new_session", lambda: db_session)
    current = datetime(2026, 10, 19, 8, 0, 5, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(schedule, "_schedule_now", lambda _plan: current)
    monkeypatch.setattr(schedule, "_active_for_schedule", lambda *_: 1)
    monkeypatch.setattr(schedule, "_fire", lambda _session, plan, planned: fired.append((plan.id, planned)))
    plans = [
        _plan(db_session, concurrency_policy="FORBID"),
        _plan(db_session, concurrency_policy="QUEUE"),
    ]
    first = datetime(2026, 10, 19, 8, 0, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    cache = {plan.id: _entry(plan, first)[plan.id] for plan in plans}

    schedule._tick(cache)

    assert fired == []
    assert cache[plans[0].id]["next"] > first
    assert cache[plans[1].id]["next"] == first


def test_max_running_instances_caps_allow_and_catch_up_dispatches(monkeypatch, db_session):
    fired = []
    monkeypatch.setattr(schedule, "new_session", lambda: db_session)
    current = datetime(2026, 10, 19, 8, 0, 5, tzinfo=schedule.ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(schedule, "_schedule_now", lambda _plan: current)
    monkeypatch.setattr(schedule, "_active_for_schedule", lambda *_: 0)
    monkeypatch.setattr(schedule, "_fire", lambda _session, plan, planned: fired.append((plan.id, planned)))
    plan = _plan(
        db_session,
        misfire_policy="FIRE_ALL_LIMITED",
        max_running_instances=1,
    )
    cache = _entry(
        plan,
        datetime(2026, 10, 19, 8, 0, 0, tzinfo=schedule.ZoneInfo("Asia/Shanghai")),
    )

    schedule._tick(cache)

    assert len(fired) == 1


def test_schedule_timezone_is_applied_to_cron_clock(monkeypatch):
    plan = type("Plan", (), {"timezone": "America/Los_Angeles"})()

    current = schedule._schedule_now(plan)

    assert current.tzinfo.key == "America/Los_Angeles"
