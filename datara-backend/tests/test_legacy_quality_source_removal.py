from pathlib import Path

from common.models import QcAlarmPolicy, QcException, QcReport, QcRule, QcRun, QcTask


BACKEND = Path(__file__).parents[1]


def test_unwired_legacy_quality_implementation_is_removed():
    assert not (BACKEND / "api" / "qc.py").exists()
    assert not (BACKEND / "common" / "qc_engine.py").exists()
    app_source = (BACKEND / "api" / "main.py").read_text(encoding="utf-8")
    assert "qc.router" not in app_source
    assert "        qc," not in app_source


def test_quality_orm_tables_are_preserved():
    expected = {
        QcRule: "t_qc_rule",
        QcTask: "t_qc_task",
        QcRun: "t_qc_run",
        QcException: "t_qc_exception",
        QcReport: "t_qc_report",
        QcAlarmPolicy: "t_qc_alarm_policy",
    }
    assert {model: model.__tablename__ for model in expected} == expected
