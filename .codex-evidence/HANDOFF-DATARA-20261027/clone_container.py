import json
import os
import secrets
import subprocess
import sys


old_name, backup_name, image = sys.argv[1:4]
rotate_app_secrets = "--rotate-app-secrets" in sys.argv[4:]
rotate_llm_key = "--rotate-llm-key" in sys.argv[4:]
inspect = json.loads(subprocess.check_output(["docker", "inspect", old_name]))[0]
config = inspect["Config"]
host = inspect["HostConfig"]
networks = inspect["NetworkSettings"]["Networks"]

args = ["docker", "run", "-d", "--name", old_name]
restart = host.get("RestartPolicy", {}).get("Name")
if restart and restart != "no":
    args += ["--restart", restart]

network_mode = host.get("NetworkMode")
if network_mode and network_mode not in {"default", "bridge"}:
    args += ["--network", network_mode]
    network = networks.get(network_mode, {})
    for alias in network.get("Aliases") or []:
        if alias not in {old_name, inspect["Id"][:12]}:
            args += ["--network-alias", alias]

validation_key = secrets.token_hex(32) if rotate_app_secrets else None
token_secret = secrets.token_hex(64) if rotate_app_secrets else None
llm_key = secrets.token_urlsafe(32) if rotate_llm_key else None
for env in config.get("Env") or []:
    if validation_key is not None and env.startswith("REBUILD_VALIDATION_KEY="):
        env = f"REBUILD_VALIDATION_KEY={validation_key}"
    elif token_secret is not None and env.startswith("REBUILD_TOKEN_SECRET="):
        env = f"REBUILD_TOKEN_SECRET={token_secret}"
    elif llm_key is not None and env.startswith("LLM_ENCRYPTION_KEY="):
        env = f"LLM_ENCRYPTION_KEY={llm_key}"
    args += ["--env", env]

for mount in inspect.get("Mounts") or []:
    # Source-code hot mounts belong to the old image and would mask the new
    # immutable image payload. Preserve data mounts only.
    if mount["Destination"] == "/app/rebuild":
        continue
    source = mount.get("Name") if mount["Type"] == "volume" else mount["Source"]
    spec = f"type={mount['Type']},src={source},dst={mount['Destination']}"
    if not mount.get("RW", True):
        spec += ",readonly"
    args += ["--mount", spec]

for container_port, bindings in (host.get("PortBindings") or {}).items():
    for binding in bindings or []:
        host_ip = binding.get("HostIp") or ""
        host_port = binding.get("HostPort") or ""
        published = f"{host_ip + ':' if host_ip else ''}{host_port}:{container_port}"
        args += ["--publish", published]

if config.get("WorkingDir"):
    args += ["--workdir", config["WorkingDir"]]
if config.get("Entrypoint"):
    args += ["--entrypoint", config["Entrypoint"][0]]

args.append(image)
args.extend(config.get("Cmd") or [])

subprocess.run(["docker", "stop", old_name], check=True, stdout=subprocess.DEVNULL)
subprocess.run(["docker", "rename", old_name, backup_name], check=True)
try:
    container_id = subprocess.check_output(args, text=True).strip()
except Exception:
    subprocess.run(["docker", "rename", backup_name, old_name], check=True)
    subprocess.run(["docker", "start", old_name], check=True, stdout=subprocess.DEVNULL)
    print("container switch failed; previous container restored", file=sys.stderr)
    raise SystemExit(1)

if validation_key is not None:
    key_path = "/lei/datara/deployments/HANDOFF-DATARA-20261027/validation.key"
    with open(key_path, "w", encoding="utf-8") as stream:
        stream.write(validation_key + "\n")
    os.chmod(key_path, 0o600)

print(json.dumps({"container": old_name, "backup": backup_name, "image": image, "id": container_id[:12]}))
