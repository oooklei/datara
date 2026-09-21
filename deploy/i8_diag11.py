#!/usr/bin/env python
"""复刻 job5 KafkaSource 消费逻辑（独立进程，30s 取证）。"""
import json
import sys
import time

sys.path.insert(0, "/app")
from worker.stream.sources import KafkaSource  # noqa: E402

params = {"srcType": "kafka", "brokers": "datara-kafka:9092", "topic": "datara-demo-orders",
          "group": "probe-replica", "startFrom": "earliest", "format": "json"}
src = KafkaSource("replica", params)
print(f"brokers={src.brokers} topic={src.topic} group={src.group}")
src.open(None)
print("open OK, assignment:", [f"{tp.topic}:{tp.partition}" for tp in src.consumer.assignment()])
t0 = time.time()
total = 0
while time.time() - t0 < 30:
    rows = src.poll(200)
    total += len(rows)
    if rows:
        print(f"t+{time.time()-t0:.1f}s rows={len(rows)} first={json.dumps(rows[0]['data'], ensure_ascii=False)[:80]}")
        break
    print(f"t+{time.time()-t0:.1f}s idle={src._idle} assignment={len(src.consumer.assignment())}")
    time.sleep(0.2)
src.close()
print(f"--- 复刻结束: 共消费 {total} 行 ---")
