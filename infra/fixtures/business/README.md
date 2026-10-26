# INFRA-DATA-01 repeatable business fixture

This package prepares a small, deterministic source dataset without deleting unrelated rows. It must be executed only on the isolated validation host `192.168.1.9`.

## Data and idempotency

- Source: 2 users, 3 goods, 3 orders, 4 order items, and 2 payments in the existing `ec_retail` tables. Supporting category/supplier rows keep references complete.
- Source projection: `ec_retail.fixture_order_detail_source` (4 rows) is the sync input.
- Target: `datara_dw.fixture_order_detail_actual` is the product workflow destination; `fixture_order_detail_expected` is the 4-row assertion baseline.
- File sync: `prepare.sh` copies `files/orders_file_sync.csv` to `/datara/files/fixtures/orders_file_sync.csv` on the validation host; the CSV is UTF-8, headered, and includes paid/done/unpaid cases.
- Source rows use reserved IDs (`910...`) and full-field upserts. Prepare only deletes rows carrying `fixture_key='INFRA-DATA-01'` from the dedicated target tables, so reruns converge without clearing other data.

On host `192.168.1.9`, from the repository root:

```bash
bash infra/fixtures/business/check.sh container
bash infra/fixtures/business/prepare.sh
DATARA_FIXTURE_MYSQL_PASSWORD='<runtime-only password>' \
  python3 infra/fixtures/business/seed_product_fixture.py
bash infra/fixtures/business/verify.sh prepared
# Create/run the sync through the product API/UI, writing the source view to fixture_order_detail_actual.
bash infra/fixtures/business/verify.sh synced
```

`bash infra/fixtures/business/check.sh static` is safe on a development machine; `check.sh container`, `prepare.sh`, and `verify.sh` enforce the `192.168.1.9` host guard before touching Docker.

The SQL preparation scripts read the MySQL password only from each MySQL container's `MYSQL_ROOT_PASSWORD` environment variable. The API seeder accepts `DATARA_FIXTURE_MYSQL_PASSWORD` (or the source/DW-specific variants) only in process memory and never prints it. No script persists a password or token. `COMPOSE_FILE`, `DATARA_FIXTURE_SRC_SERVICE`, and `DATARA_FIXTURE_DW_SERVICE` may select the isolated compose stack.

## Product API fixture entry points

Platform objects are deliberately not inserted into meta tables. `seed_product_fixture.py` reads the long-lived validation key from `DATARA_VALIDATION_KEY_FILE` (default `/lei/datara/runtime-secrets/codex-development-api.key`), exchanges it through `POST /api/v1/rebuild/validation-token` with scope `high-priority-e2e`, and keeps both key and short-lived token in process memory only. Neither secret is printed, written to a URL, browser storage, static assets, or result JSON. `DATARA_API_BASE` overrides the default `http://127.0.0.1:18091` API base.

The seeder idempotently creates or reuses project `INFRA-DATA-01 电商闭环验证`, source and DW MySQL datasources, and project variable `fixture_key`. `prepare.sh` installs the CSV in the shared file-sync path separately. Seeder stdout is a machine-readable JSON object containing only non-sensitive object IDs and the non-sensitive file path. A failed API call exits nonzero. To inspect the plan locally without reading the key or making network calls:

```bash
python3 infra/fixtures/business/seed_product_fixture.py --dry-run
```

| Fixture | API entry point | Minimum request intent |
|---|---|---|
| project | `GET/POST /api/v1/rebuild/projects` | Reuse by exact fixture project name or create it |
| datasource | `GET/POST /api/v1/rebuild/projects/{project_id}/datasources` | Reuse by exact source/DW name or create from runtime connection settings |
| variable | `POST /api/v1/rebuild/variables?project_id=...` | JSON scope/name/value; set `workflow_id` for workflow scope |
| file_sync:csv | product sync component (create through the product API/UI) | `baseMode=file_sync` with `filePath=/datara/files/fixtures/orders_file_sync.csv` and `fileType=csv` |

The exchanged token is sent as `Authorization: Bearer ...`. Datasource settings can be overridden with `DATARA_FIXTURE_SRC_*` and `DATARA_FIXTURE_DW_*`; credentials must be supplied at runtime and must not be checked into files.
