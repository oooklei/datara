"""Idempotent schema bootstrap for the API-key domain."""

from sqlalchemy import inspect

from rebuild.apikey.models import ApiKeyRecord


def apply_apikey_migrations(engine):
    if "rebuild_api_key" not in inspect(engine).get_table_names():
        ApiKeyRecord.__table__.create(bind=engine)
    return {"created": True, "revision": "i15_0002_api_key"}
