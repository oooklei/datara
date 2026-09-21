"""I8 门4-③：WebSocket 通道实测客户端（worker 容器内运行）。"""
import json
import sys

import requests
import websocket

API = "http://datara-api:8000/api/v1"
job = sys.argv[1]
tok = requests.post(API + "/login", json={"user_name": "admin", "user_pwd": "Admin@123"}, timeout=10).json()["data"]["token"]
ws = websocket.create_connection(f"ws://datara-api:8000/api/v1/stream-jobs/{job}/data/ws?token={tok}", timeout=10)
try:
    for i in range(3):
        frame = json.loads(ws.recv())
        m = frame.get("metrics") or {}
        print(f"[ws] frame={i + 1} fields={frame['fields']} rows={len(frame['rows'])} "
              f"status={m.get('status')} totalOut={m.get('totalOut')}")
finally:
    ws.close()
print("[ws] PASS：3 帧快照接收正常")
