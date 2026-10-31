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


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if check and result.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


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
    print(f"PASS main={git('rev-parse', 'HEAD')} origin/main={git('rev-parse', 'origin/main')}")


def snapshot(release_id: str, record_existing_release: bool) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,79}", release_id):
        raise ValueError("release-id 只能包含字母、数字、点、下划线和连字符")
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
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": files,
    }
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{archive}\n{manifest}\nsha256={data['archive_sha256']} files={len(files)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("preflight")
    capture = command.add_parser("snapshot")
    capture.add_argument("--release-id", required=True)
    capture.add_argument("--record-existing-release", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            preflight()
        else:
            snapshot(args.release_id, args.record_existing_release)
    except (RuntimeError, ValueError, FileExistsError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
