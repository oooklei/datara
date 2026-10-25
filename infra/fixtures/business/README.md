# INFRA-DATA-01 repeatable business fixture

This package prepares a small, deterministic source dataset without deleting unrelated rows. It must be executed only on the isolated validation host `192.168.1.9`.

## Data and idempotency

- Source: 2 users, 3 goods, 3 orders, 4 order items, and 2 payments in the existing `ec_retail` tables. Supporting category/supplier rows keep references complete.
- Source projection: `ec_retail.fixture_order_detail_source` (4 rows) is the sync input.
- Target: `datara_dw.fixture_order_detail_actual` is the product workflow destination; `fixture_order_detail_expected` is the 4-row assertion baseline.
- File sync: `files/orders_file_sync.csv` is UTF-8, headered, and includes paid/done/unpaid cases.
- Source rows use reserved IDs (`910...`) and full-field upserts. Prepare only deletes rows carrying `fixture_key='INFRA-DATA-01'` from the dedicated target tables, so reruns converge without clearing other data.

On host `192.168.1.9`, from the repository root:

```bash
bash infra/fixtures/business/check.sh container
bash infra/fixtures/business/prepare.sh
bash infra/fixtures/business/verify.sh prepared
# Create/run the sync through the product API/UI, writing the source view to fixture_order_detail_actual.
bash infra/fixtures/business/verify.sh synced
```

`bash infra/fixtures/business/check.sh static` is safe on a development machine; `check.sh container`, `prepare.sh`, and `verify.sh` enforce the `192.168.1.9` host guard before touching Docker.

The scripts read the MySQL password only from each MySQL container's `MYSQL_ROOT_PASSWORD` environment variable. They never accept or persist a password/token. `COMPOSE_FILE`, `DATARA_FIXTURE_SRC_SERVICE`, and `DATARA_FIXTURE_DW_SERVICE` may select the isolated compose stack.

## Product API fixture entry points

Platform objects are deliberately not inserted into meta tables. Create them through the rebuild API after obtaining a short-lived token outside this package. Keep `DATARA_ACCESS_TOKEN`, `DATARA_PROJECT_ID`, and returned IDs in process environment only; do not put them in JSON, URLs, browser storage, or evidence.

| Fixture | API entry point | Minimum request intent |
|---|---|---|
| workflow | `POST /api/v1/rebuild/workflows` | JSON `{project_id, name, description, workflow_type}`; then add nodes/edges and publish through that workflow's API |
| variable | `POST /api/v1/rebuild/variables?project_id=...` | JSON scope/name/value; set `workflow_id` for workflow scope |
| resource | `POST /api/v1/rebuild/resources/uploads` | multipart `project_id`, `kind`, and `file=@infra/fixtures/business/files/orders_file_sync.csv` |
| resource binding | `POST /api/v1/rebuild/resources/bindings` | JSON project/workflow/workflow_version/task/resource/resource_version IDs |
| stream | `POST /api/v1/rebuild/stream/jobs` | JSON `{name, workflow_id, mq_topic, runtime_config}` |

Send the token in the `token` header (or `Authorization: Bearer ...`). The API base on the validation host is supplied by the caller, normally via `DATARA_API_BASE`; no executable API seeding script is included until the workflow graph contract is frozen.
