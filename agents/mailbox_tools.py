"""mailbox 小工具：程序化修改条目状态（不手写 mailbox.jsonl）。

用法：
  python agents/mailbox_tools.py done <msg_id>   # 标记 status=done 并加 ack_ts
"""
import datetime
import json
import os
import sys

MAILBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "handoff", "mailbox.jsonl")


def read_mail(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_mail(path, msgs):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for m in msgs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def main():
    args = sys.argv[1:]
    if len(args) != 2 or args[0] != "done":
        print(__doc__)
        sys.exit(1)
    target = args[1]
    msgs = read_mail(MAILBOX)
    hit = 0
    for m in msgs:
        if m.get("id") == target and m.get("status") != "done":
            m["status"] = "done"
            m["ack_ts"] = datetime.datetime.now().isoformat(timespec="seconds")
            hit += 1
    if not hit:
        print(f"no pending entry matched id={target}")
        sys.exit(2)
    write_mail(MAILBOX, msgs)
    print(f"marked done={hit} id={target}; total lines={len(msgs)}")


if __name__ == "__main__":
    main()
