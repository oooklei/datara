"""Stable error mapping for R5-A SQL IDE driver boundaries."""

from __future__ import annotations

from rebuild.run_sql import (
    SqlDependencyUnavailable,
    SqlExecutionFailed,
    SqlExecutionTimeout,
)


def map_connection_error(error: Exception) -> SqlDependencyUnavailable:
    """Hide connection and driver details behind a stable domain error."""
    del error
    return SqlDependencyUnavailable(
        "Datasource connection unavailable",
        details={"errorCode": "DATASOURCE_UNAVAILABLE"},
    )


def map_driver_error(error: Exception) -> SqlExecutionFailed | SqlExecutionTimeout:
    """Map driver failures without exposing raw messages, SQL, or credentials."""
    if isinstance(error, TimeoutError):
        return SqlExecutionTimeout(
            "SQL execution timed out",
            details={"errorCode": "EXECUTION_TIMEOUT"},
        )
    return SqlExecutionFailed(
        "SQL execution failed",
        details={"errorCode": "DRIVER_ERROR"},
    )
