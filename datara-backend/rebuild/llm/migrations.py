"""Versioned migration entry point for the LLM domain."""

from rebuild.governance.migrations import GovernanceMigration, MigrationApplyError, MigrationResult, MigrationRunner
from rebuild.llm.revisions import v0001_llm_model

LLM_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_llm_model.revision,
        checksum=v0001_llm_model.checksum,
        upgrade=v0001_llm_model.upgrade,
        tables=v0001_llm_model.LLM_TABLES,
    ),
)


def apply_llm_migrations(engine) -> MigrationResult:
    result = MigrationRunner(engine, LLM_MIGRATIONS).apply()
    try:
        v0001_llm_model.validate_schema(engine)
    except Exception as exc:
        raise MigrationApplyError(f"LLM schema validation failed ({type(exc).__name__})") from None
    return result
