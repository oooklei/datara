"""One-off fixups for datara-integration.patch (JDK 8 + missing TS imports).

Applied on 192.168.1.9 after the main patch. Regenerate the authoritative
patch with regen-patch.sh afterwards.
"""
import io
import sys

BASE = "/lei/dolphinscheduler/dolphinscheduler-3.4.3"

# --- 1. use-queue.ts: missing vue imports -----------------------------------
p1 = f"{BASE}/dolphinscheduler-ui/src/views/projects/task/components/node/fields/use-queue.ts"
with io.open(p1, encoding="utf-8") as fh:
    src = fh.read()
needle = "import { dataraEmbed, dataraOptions } from '@/utils/datara-bridge'\n"
assert needle in src, "use-queue import anchor missing"
src = src.replace(
    needle,
    needle + "import { ref, onMounted } from 'vue'\n",
    1,
)
with io.open(p1, "w", encoding="utf-8") as fh:
    fh.write(src)
print("use-queue.ts: vue imports added")

# --- 2. TaskExecutionContextFactory: JDK 8 HTTP client ----------------------
p2 = f"{BASE}/dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/runner/TaskExecutionContextFactory.java"
with io.open(p2, encoding="utf-8") as fh:
    src = fh.read()

old_imports = """import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
"""
new_imports = """import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.UnsupportedEncodingException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
"""
assert old_imports in src, "http imports anchor missing"
src = src.replace(old_imports, new_imports, 1)

old_body = """        String encoded = URLEncoder.encode(connectionId, StandardCharsets.UTF_8);
        URI uri = URI.create(baseUrl.replaceAll("/+$", "") + "/internal/dbx/connections/" + encoded
                + "/params?project_id=" + projectId);
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .header("X-Datara-Internal-Token", token)
                .GET().build();
        try {
            HttpResponse<String> response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) {
                throw new IllegalStateException("Datara datasource resolution failed: HTTP " + response.statusCode());
            }
            Map<?, ?> envelope = JSONUtils.parseObject(response.body(), Map.class);
            if (envelope == null || !Integer.valueOf(0).equals(envelope.get("code"))
                    || !(envelope.get("data") instanceof Map)) {
                throw new IllegalStateException("Datara datasource response is invalid");
            }
            Map<?, ?> data = (Map<?, ?>) envelope.get("data");
            DataSourceParameters parameters = new DataSourceParameters();
            parameters.setType(DbType.valueOf(String.valueOf(data.get("type"))));
            parameters.setConnectionParams(String.valueOf(data.get("connectionParams")));
            return parameters;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Datara datasource resolution interrupted", exception);
        } catch (java.io.IOException exception) {
            throw new IllegalStateException("Datara datasource resolution unavailable", exception);
        }
    }
"""
new_body = """        HttpURLConnection connection = null;
        try {
            String encoded = URLEncoder.encode(connectionId, "UTF-8");
            URL url = new URL(baseUrl.replaceAll("/+$", "") + "/internal/dbx/connections/" + encoded
                    + "/params?project_id=" + projectId);
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(10000);
            connection.setRequestProperty("X-Datara-Internal-Token", token);
            int status = connection.getResponseCode();
            if (status != HttpURLConnection.HTTP_OK) {
                throw new IllegalStateException("Datara datasource resolution failed: HTTP " + status);
            }
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[4096];
            try (InputStream stream = connection.getInputStream()) {
                int read;
                while ((read = stream.read(chunk)) != -1) {
                    buffer.write(chunk, 0, read);
                }
            }
            Map<?, ?> envelope = JSONUtils.parseObject(
                    new String(buffer.toByteArray(), StandardCharsets.UTF_8), Map.class);
            if (envelope == null || !Integer.valueOf(0).equals(envelope.get("code"))
                    || !(envelope.get("data") instanceof Map)) {
                throw new IllegalStateException("Datara datasource response is invalid");
            }
            Map<?, ?> data = (Map<?, ?>) envelope.get("data");
            DataSourceParameters parameters = new DataSourceParameters();
            parameters.setType(DbType.valueOf(String.valueOf(data.get("type"))));
            parameters.setConnectionParams(String.valueOf(data.get("connectionParams")));
            return parameters;
        } catch (UnsupportedEncodingException exception) {
            throw new IllegalStateException("Datara datasource resolution encoding is unavailable", exception);
        } catch (IOException exception) {
            throw new IllegalStateException("Datara datasource resolution unavailable", exception);
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }
"""
assert old_body in src, "http body anchor missing"
src = src.replace(old_body, new_body, 1)
with io.open(p2, "w", encoding="utf-8") as fh:
    fh.write(src)
print("TaskExecutionContextFactory.java: HttpURLConnection applied")
