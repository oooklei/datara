"""11A gate: keep the SQL IDE 24 backend routes aligned with frontend entry points."""

from pathlib import Path
import re

from rebuild.sql_ide.routes import _ROUTE_SPECS


ROOT = Path(__file__).resolve().parents[3]
CLIENT = ROOT / "datara-newweb/src/services/rebuild/sqlIdeApi.ts"


EXPECTED = {
    "listDatabases": "listDatabases",
    "listSchemas": "listSchemas",
    "listRelations": "listRelations",
    "listColumns": "listColumns",
    "listRoutines": "listRoutines",
    "listIndexes": "listIndexes",
    "searchObjects": "searchObjects",
    "getDefinition": "getDefinition",
    "lintSql": "lintSql",
    "executeSql": "executeSql",
    "cancelExecution": "cancelExecution",
    "openEventStream": "openEventStream",
    "getExecutionStatus": "getSqlIdeExecutionStatus",
    "fetchResultPage": "fetchResultPage",
    "listHistory": "listHistory",
    "deleteHistory": "deleteHistory",
    "listScripts": "listScripts",
    "saveScript": "saveScript",
    "deleteScript": "deleteScript",
    "exportResult": "exportResult",
    "exportTable": "exportTable",
    "getExport": "getExport",
    "downloadExport": "getExportDownloadUrl",
    "cancelExport": "cancelExport",
}


def test_all_24_backend_routes_have_one_frontend_entry_point() -> None:
    operations = [spec[2] for spec in _ROUTE_SPECS]
    assert len(operations) == 24
    assert len(set(operations)) == 24
    assert set(operations) == set(EXPECTED)

    source = CLIENT.read_text(encoding="utf-8")
    for frontend_entry in EXPECTED.values():
        assert re.search(rf"\b{re.escape(frontend_entry)}\b", source), frontend_entry


def test_contract_constant_has_23_unique_object_methods() -> None:
    source = CLIENT.read_text(encoding="utf-8")
    block = re.search(
        r"export const R5A_CONTRACT_METHODS = \[(.*?)\] as const",
        source,
        re.DOTALL,
    )
    assert block is not None
    methods = re.findall(r"'([A-Za-z][A-Za-z0-9]+)'", block.group(1))
    assert len(methods) == 23
    assert len(set(methods)) == 23
    assert set(methods) == set(EXPECTED.values()) - {"getSqlIdeExecutionStatus"}


def test_ddl_write_client_stays_out_of_readonly_contract() -> None:
    source = CLIENT.read_text(encoding="utf-8")
    assert not re.search(r"^\s*import .*sqlIdeDdlApi", source, re.MULTILINE)
    assert not ({"validatePolicy", "previewImpact", "submitConfirm", "executeDdl"} & set(EXPECTED.values()))
