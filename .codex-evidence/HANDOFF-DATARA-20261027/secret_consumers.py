import json
import subprocess


names = subprocess.check_output(["docker", "ps", "-a", "--format", "{{.Names}}"], text=True).splitlines()
keys = ("REBUILD_DB_URL", "REBUILD_MYSQL_SRC_URL", "REBUILD_LEGACY_META_URL", "LLM_ENCRYPTION_KEY")
consumers = {key: [] for key in keys}
for name in names:
    env = json.loads(subprocess.check_output(["docker", "inspect", "-f", "{{json .Config.Env}}", name], text=True))
    present = {item.split("=", 1)[0] for item in env if "=" in item}
    for key in keys:
        if key in present:
            consumers[key].append(name)
print(json.dumps(consumers, sort_keys=True))
