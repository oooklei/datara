# Datara DolphinScheduler 3.4.3 integration patch

Apply `datara-integration.patch` to the exact Apache DolphinScheduler 3.4.3 source tree (`a190201`) with `git apply --check` and `git apply`. Build the API, master, worker, task plugins, and UI from that tree; the stock 3.4.3 images do not contain this integration.

The patch accepts a short lived HMAC embed token from the Datara gateway, connects node options to Datara owner filtered endpoints, routes the DAG variable button to Datara, and stores DBX connection IDs as strings through task parameters and runtime resolution. Configure the same `DATARA_DS_EMBED_SECRET` on the gateway and DolphinScheduler API, and configure `DATARA_ORCHESTRATION_INTERNAL_URL` plus `DATARA_INTERNAL_TOKEN` on the master. Keep these values in the deployment environment, outside static assets.

The gateway must expose its internal datasource endpoint only to the master and must resolve connection credentials through the DBX internal route. Rebuild and deploy all patched DolphinScheduler services together; mixed stock and patched images cannot execute nodes with string DBX IDs.

Verification gate: compile the patched Java modules and UI, then on 192.168.1.9 confirm options, save and run SQL/DataX nodes with a DBX string ID, cross project visibility, variables, schedules, and existing workflow execution. Do not claim the integration complete until this gate passes.
