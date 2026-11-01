"""Check the Datara release gate and capture the exact main worktree source."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE_POLICY = ROOT / "deploy" / "image-policy.json"
IMAGE_PROBE_TIMEOUT_SECONDS = 25


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if check and result.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def load_image_policy() -> dict:
    """Read the DBX / dolphinscheduler image allow-list (single source of truth)."""
    try:
        policy = json.loads(IMAGE_POLICY.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"缺少镜像策略文件：{IMAGE_POLICY}") from None
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"镜像策略不是合法 JSON：{IMAGE_POLICY}：{exc}") from None
    for key in ("host", "containers", "compose_files", "forbid_tag_patterns"):
        if key not in policy:
            raise RuntimeError(f"镜像策略缺少字段 {key}：{IMAGE_POLICY}")
    if not isinstance(policy["containers"], dict) or not policy["containers"]:
        raise RuntimeError(f"镜像策略 containers 必须是非空对象：{IMAGE_POLICY}")
    if not re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+", str(policy["host"])):
        raise RuntimeError(f"镜像策略 host 非法：{policy['host']!r}")
    for name in policy["containers"]:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            raise RuntimeError(f"镜像策略容器名非法：{name!r}")
    for path in policy["compose_files"]:
        if not re.fullmatch(r"/[A-Za-z0-9._/-]+", path):
            raise RuntimeError(f"镜像策略 compose 路径非法：{path!r}")
    return policy


def image_tag(image: str) -> str:
    """Return the tag of an image reference (empty string when untagged)."""
    ref = image.rsplit("/", 1)[-1]
    return ref.rsplit(":", 1)[-1] if ":" in ref else ""


def compose_services(text: str) -> dict[str, dict[str, str]]:
    """Minimal 2-space-indent compose reader: service -> {image, pull_policy}."""
    services: dict[str, dict[str, str]] = {}
    section: str | None = None
    current: str | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            section = stripped.rstrip(":")
            current = None
            continue
        if section != "services":
            continue
        if indent == 2:
            current = stripped.rstrip(":")
            services[current] = {}
        elif indent >= 4 and current is not None:
            key, _, value = stripped.partition(":")
            if key in ("image", "pull_policy"):
                services[current][key] = value.strip().strip("'\"")
    return services


def probe_image_state(policy: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Ask the deploy host for live container images and the controlled compose files."""
    script = ["set -u", "echo '@@CONTAINERS@@'"]
    for name in sorted(policy["containers"]):
        script.append(
            f'echo "{name}=$(docker inspect -f \'{{{{.Config.Image}}}}\' {name} 2>/dev/null || true)"'
        )
    for path in policy["compose_files"]:
        script.append(f"echo '@@COMPOSE {path}@@'")
        script.append(f"cat {path} 2>/dev/null || echo '@@MISSING@@'")
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", policy["host"], "bash -s"],
        input="\n".join(script) + "\n",
        capture_output=True, text=True, timeout=IMAGE_PROBE_TIMEOUT_SECONDS, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"ssh 退出码 {result.returncode}")
    live: dict[str, str] = {}
    compose_text: dict[str, str] = {}
    mode: str | None = None
    current: str | None = None
    buffer: list[str] = []
    for line in result.stdout.splitlines():
        if line == "@@CONTAINERS@@":
            mode = "containers"
            continue
        if line.startswith("@@COMPOSE ") and line.endswith("@@"):
            if current is not None:
                compose_text[current] = "\n".join(buffer)
            current = line[len("@@COMPOSE "):-2]
            buffer = []
            mode = "compose"
            continue
        if mode == "containers":
            name, _, image = line.partition("=")
            live[name.strip()] = image.strip()
        elif mode == "compose":
            buffer.append(line)
    if current is not None:
        compose_text[current] = "\n".join(buffer)
    return live, compose_text


def image_gate() -> None:
    """Fail when DBX / dolphinscheduler images drift from the approved allow-list."""
    policy = load_image_policy()
    expected: dict[str, str] = dict(policy["containers"])
    forbidden = [str(tag) for tag in policy["forbid_tag_patterns"]]
    problems: list[str] = []

    for name, image in sorted(expected.items()):
        if image_tag(image) in forbidden:
            problems.append(f"镜像策略自身违规：{name} 指向 {image}（禁用 tag）")

    try:
        live, compose_text = probe_image_state(policy)
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"WARN 镜像闸门跳过：无法从 {policy['host']} 取证（{exc}）")
        if problems:
            raise RuntimeError("镜像闸门未通过：\n- " + "\n- ".join(problems))
        return

    for name, image in sorted(expected.items()):
        actual = live.get(name, "")
        if not actual:
            problems.append(f"{name} 未运行或不可见，白名单镜像 {image}")
        elif actual != image:
            problems.append(f"{name} 镜像漂移：运行中 {actual}，白名单 {image}")

    declared: set[str] = set()
    for path in policy["compose_files"]:
        text = compose_text.get(path, "")
        if not text or text.strip() == "@@MISSING@@":
            problems.append(f"受控 compose 不可读：{path}")
            continue
        for service, spec in compose_services(text).items():
            image = spec.get("image", "")
            if image in expected.values():
                declared.add(image)
                if spec.get("pull_policy") != "never":
                    problems.append(f"{path} 服务 {service} 使用锁定镜像 {image} 但未声明 pull_policy: never")
            elif image_tag(image) in forbidden:
                problems.append(f"{path} 服务 {service} 使用禁用 tag：{image}")

    for name, image in sorted(expected.items()):
        if image not in declared:
            problems.append(f"白名单镜像 {image}（{name}）未在受控 compose 中声明")

    if problems:
        raise RuntimeError("镜像闸门未通过：\n- " + "\n- ".join(problems))
    print("PASS image-gate " + " ".join(f"{name}={expected[name]}" for name in sorted(expected)))


def preflight() -> None:
    git("fetch", "origin", "main")
    problems: list[str] = []
    if git("branch", "--show-current") != "main":
        problems.append("当前工作区不是 main")
    if git("ls-files", "-u"):
        problems.append("Git 索引存在未解决冲突")
    if git("status", "--porcelain"):
        problems.append("工作树有未提交修改，先合并并提交待发布代码")
    if git("branch", "--no-merged", "main", "--format=%(refname:short)"):
        problems.append("存在未合并到 main 的本地分支，先确认待发布内容并合并")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", "origin/main", "main"],
        cwd=ROOT, check=False,
    ).returncode:
        problems.append("origin/main 有未合并提交")
    if problems:
        raise RuntimeError("发布前检查未通过：\n- " + "\n- ".join(problems))
    image_gate()
    print(f"PASS main={git('rev-parse', 'HEAD')} origin/main={git('rev-parse', 'origin/main')}")


def snapshot(release_id: str, record_existing_release: bool) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,79}", release_id):
        raise ValueError("release-id 只能包含字母、数字、点、下划线和连字符")
    policy = load_image_policy()
    if not record_existing_release:
        preflight()
    dest = ROOT / ".source-mirrors" / release_id
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / "datara-source.tar.gz"
    manifest = dest / "datara-source.json"
    if archive.exists() or manifest.exists():
        raise FileExistsError(f"快照已存在，禁止覆盖：{dest}")
    selected = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout
    names = sorted(set(p.decode("utf-8") for p in selected.split(b"\0") if p))
    files: dict[str, str] = {}
    with tarfile.open(archive, "w:gz") as output:
        for name in names:
            path = ROOT / name
            if not path.is_file() or path.is_symlink():
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(ROOT):
                raise RuntimeError(f"文件越出工作区：{name}")
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            output.add(path, arcname=name, recursive=False)
    data = {
        "release_id": release_id,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "branch": git("branch", "--show-current"),
        "head": git("rev-parse", "HEAD"),
        "origin_main": git("rev-parse", "origin/main"),
        "worktree_status": git("status", "--porcelain"),
        "gate": "record_existing_release_only" if record_existing_release else "preflight_passed",
        "image_policy_sha256": hashlib.sha256(IMAGE_POLICY.read_bytes()).hexdigest(),
        "image_tags": dict(policy["containers"]),
        "image_compose_files": list(policy["compose_files"]),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": files,
    }
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{archive}\n{manifest}\nsha256={data['archive_sha256']} files={len(files)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("preflight")
    command.add_parser("image-gate")
    capture = command.add_parser("snapshot")
    capture.add_argument("--release-id", required=True)
    capture.add_argument("--record-existing-release", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            preflight()
        elif args.command == "image-gate":
            image_gate()
        else:
            snapshot(args.release_id, args.record_existing_release)
    except (RuntimeError, ValueError, FileExistsError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
