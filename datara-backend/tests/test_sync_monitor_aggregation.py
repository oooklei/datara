"""Sync monitor aggregation covers table and file sync executor output contracts."""

from types import SimpleNamespace

from api import sync as sync_api


class _Attr:
    def __init__(self, name):
        self.name = name

    def __eq__(self, value):
        return lambda row: getattr(row, self.name) == value

    def in_(self, values):
        return lambda row: getattr(row, self.name) in values


class _Task:
    instance_id = _Attr("instance_id")
    node_type = _Attr("node_type")


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *predicates):
        self.rows = [row for row in self.rows if all(predicate(row) for predicate in predicates)]
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _model):
        return _Query(self.rows)


def test_sync_monitor_aggregates_file_sync_aliases(monkeypatch):
    monkeypatch.setattr(sync_api, "TaskInstance", _Task)
    db = _Db(
        [
            SimpleNamespace(
                instance_id="i-1", node_type="sync", outputs={"read_rows": 4, "write_rows": 3, "bad_rows": 1}
            ),
            SimpleNamespace(
                instance_id="i-1",
                node_type="file_sync",
                outputs={"rows_read": 7, "rows_written": 6, "rows_skipped": 1},
            ),
            SimpleNamespace(instance_id="i-1", node_type="sql", outputs={"read_rows": 99, "write_rows": 99}),
        ]
    )
    assert sync_api._sync_outputs(db, "i-1") == {
        "readRows": 11,
        "writeRows": 9,
        "badRows": 1,
        "batchId": "i-1",
        "schemas": [],
    }
