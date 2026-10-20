"""I22 standard domain check engines: naming, type precision, value domain, code table reference."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.governance.models import (
    StandardCodeSetRecord,
    StandardCodeValueRecord,
    StandardElementRecord,
    StandardMappingRecord,
    StandardNamingRuleRecord,
)


@dataclass(frozen=True)
class CheckIssue:
    engine: str
    scope: str
    severity: str
    message: str
    source_id: str = ""


@dataclass(frozen=True)
class CheckReport:
    scope: str
    issues: tuple[CheckIssue, ...] = field(default_factory=tuple)

    @property
    def summary(self) -> dict[str, object]:
        return {
            "total_issues": len(self.issues),
            "by_engine": {engine: sum(1 for i in self.issues if i.engine == engine) for engine in {i.engine for i in self.issues}},
            "by_severity": {sev: sum(1 for i in self.issues if i.severity == sev) for sev in {i.severity for i in self.issues}},
        }


def run_naming_check(session: Session, project_id: int) -> CheckReport:
    """Check element and code set names against naming rules."""
    issues: list[CheckIssue] = []
    rules = session.scalars(
        select(StandardNamingRuleRecord).where(
            StandardNamingRuleRecord.project_id == project_id,
            StandardNamingRuleRecord.enabled.is_(True),
        )
    ).all()
    elements = session.scalars(
        select(StandardElementRecord).where(StandardElementRecord.project_id == project_id)
    ).all()
    for element in elements:
        for rule in rules:
            if rule.target_type and rule.target_type != "field":
                continue
            if rule.pattern and not re.match(rule.pattern, element.code):
                issues.append(CheckIssue(
                    engine="naming",
                    scope="element",
                    severity="warning",
                    message=f"Element '{element.code}' does not match naming pattern '{rule.pattern}'",
                    source_id=str(element.id),
                ))
    return CheckReport(scope="naming", issues=tuple(issues))


def run_type_precision_check(session: Session, project_id: int) -> CheckReport:
    """Check that element data types have valid precision/length."""
    issues: list[CheckIssue] = []
    elements = session.scalars(
        select(StandardElementRecord).where(StandardElementRecord.project_id == project_id)
    ).all()
    for element in elements:
        if element.data_type.upper() in ("VARCHAR", "CHAR", "DECIMAL", "NUMERIC"):
            if element.length is None or element.length <= 0:
                issues.append(CheckIssue(
                    engine="type_precision",
                    scope="element",
                    severity="error",
                    message=f"Element '{element.code}' has data type '{element.data_type}' but no valid length",
                    source_id=str(element.id),
                ))
    return CheckReport(scope="type_precision", issues=tuple(issues))


def run_value_domain_check(session: Session, project_id: int) -> CheckReport:
    """Check that code set values are unique and non-empty."""
    issues: list[CheckIssue] = []
    code_sets = session.scalars(
        select(StandardCodeSetRecord).where(StandardCodeSetRecord.project_id == project_id)
    ).all()
    for cs in code_sets:
        values = session.scalars(
            select(StandardCodeValueRecord).where(StandardCodeValueRecord.code_set_id == cs.id)
        ).all()
        seen: set[str] = set()
        for val in values:
            if not val.code_value:
                issues.append(CheckIssue(
                    engine="value_domain",
                    scope="code_value",
                    severity="error",
                    message=f"Code set '{cs.code}' has empty code value",
                    source_id=str(val.id),
                ))
            elif val.code_value in seen:
                issues.append(CheckIssue(
                    engine="value_domain",
                    scope="code_value",
                    severity="error",
                    message=f"Code set '{cs.code}' has duplicate code value '{val.code_value}'",
                    source_id=str(val.id),
                ))
            seen.add(val.code_value)
    return CheckReport(scope="value_domain", issues=tuple(issues))


def run_code_table_reference_check(session: Session, project_id: int) -> CheckReport:
    """Check that mappings reference valid elements and code sets."""
    issues: list[CheckIssue] = []
    mappings = session.scalars(
        select(StandardMappingRecord).where(StandardMappingRecord.project_id == project_id)
    ).all()
    for mapping in mappings:
        if mapping.element_id is not None:
            element = session.get(StandardElementRecord, mapping.element_id)
            if element is None:
                issues.append(CheckIssue(
                    engine="code_table_reference",
                    scope="mapping",
                    severity="error",
                    message=f"Mapping '{mapping.name}' references non-existent element {mapping.element_id}",
                    source_id=str(mapping.id),
                ))
        if mapping.code_set_id is not None:
            code_set = session.get(StandardCodeSetRecord, mapping.code_set_id)
            if code_set is None:
                issues.append(CheckIssue(
                    engine="code_table_reference",
                    scope="mapping",
                    severity="error",
                    message=f"Mapping '{mapping.name}' references non-existent code set {mapping.code_set_id}",
                    source_id=str(mapping.id),
                ))
    return CheckReport(scope="code_table_reference", issues=tuple(issues))


def run_all_checks(session: Session, project_id: int) -> tuple[CheckReport, ...]:
    """Run all four check engines and return reports."""
    return (
        run_naming_check(session, project_id),
        run_type_precision_check(session, project_id),
        run_value_domain_check(session, project_id),
        run_code_table_reference_check(session, project_id),
    )
