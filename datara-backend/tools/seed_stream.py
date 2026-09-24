"""流任务灌数工具（I11 验证用，schema 与 worker.stream.sources.SimulateSource 三数据集一致）。

用法（容器内）：
  python tools/seed_stream.py --target kafka --brokers datara-kafka:9092 --duration 1800
  python tools/seed_stream.py --target mqtt  --host datara-emqx --port 1883 --duration 1800
  python tools/seed_stream.py --target redis --url redis://redis:6379/0 --duration 1800

- kafka: order_pay / user_click / cart_event 三 topic（电商大盘 case1）
- mqtt:  iot/sensor/temp|press|vib/<dev> + iot/alert/<dev>（工业 IoT case2）
- redis: XADD order_stream / user_stream（访问统计 case3）
速率 --eps（每秒事件数，默认 5），Ctrl-C 或 duration 到期退出。
"""

import argparse
import json
import random
import signal
import time

GOODS = ["SKU_1001", "SKU_1002", "SKU_1003", "SKU_1004", "SKU_1005"]
USERS = [f"u_{i:04d}" for i in range(200)]
DEVICES = [f"dev_{i:03d}" for i in range(10)]
PAGES = ["/home", "/list", "/detail", "/cart", "/pay", "/order"]

_running = True


def _stop(_sig, _frm):
    global _running
    _running = False


def gen_ecommerce(now):
    r = random.random()
    if r < 0.2:
        return "order_pay", {"order_id": f"ord_{random.randrange(10**8):08d}", "user_id": random.choice(USERS),
                             "goods_id": random.choice(GOODS), "amount": round(random.uniform(9.9, 999.0), 2), "ts": now}
    if r < 0.8:
        return "user_click", {"user_id": random.choice(USERS), "goods_id": random.choice(GOODS), "ts": now}
    return "cart_event", {"user_id": random.choice(USERS), "goods_id": random.choice(GOODS),
                          "action": random.choice(["add", "add", "remove"]), "ts": now}


def gen_iot(now):
    dev = random.choice(DEVICES)
    r = random.random()
    if r < 0.32:
        return f"iot/sensor/temp/{dev}", {"device": dev, "value": round(random.gauss(45, 5), 2), "ts": now}
    if r < 0.64:
        return f"iot/sensor/press/{dev}", {"device": dev, "value": round(random.gauss(3.5, 0.5), 3), "ts": now}
    if r < 0.98:
        return f"iot/sensor/vib/{dev}", {"device": dev, "value": round(abs(random.gauss(0, 2)), 3), "ts": now}
    return f"iot/alert/{dev}", {"device": dev, "ts": now,
                                "type": random.choice(["OVERHEAT", "PRESSURE_HIGH", "VIBRATION_HIGH"])}


def gen_visit(now):
    if random.random() < 0.2:
        return "order_stream", {"order_id": f"o_{random.randrange(10**8):08d}", "user_id": random.choice(USERS),
                                "amount": round(random.uniform(20, 800), 2), "ts": now}
    return "user_stream", {"user_id": random.choice(USERS), "page": random.choice(PAGES), "ts": now}


def seed_kafka(brokers, eps, duration):
    from kafka import KafkaProducer
    p = KafkaProducer(bootstrap_servers=brokers,
                      value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"))
    print(f"[seed-kafka] brokers={brokers} eps={eps}", flush=True)
    n = 0
    deadline = time.time() + duration
    while _running and time.time() < deadline:
        topic, data = gen_ecommerce(time.time())
        p.send(topic, data)
        p.poll(0)
        n += 1
        time.sleep(1.0 / eps)
        if n % 100 == 0:
            print(f"[seed-kafka] sent={n}", flush=True)
    p.flush(5)


def seed_mqtt(host, port, eps, duration):
    import paho.mqtt.client as mqtt
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.connect(host, port, keepalive=60)
    c.loop_start()
    print(f"[seed-mqtt] {host}:{port} eps={eps}", flush=True)
    n = 0
    deadline = time.time() + duration
    while _running and time.time() < deadline:
        topic, data = gen_iot(time.time())
        c.publish(topic, json.dumps(data, ensure_ascii=False))
        n += 1
        time.sleep(1.0 / eps)
        if n % 100 == 0:
            print(f"[seed-mqtt] sent={n}", flush=True)
    c.loop_stop()
    c.disconnect()


def seed_redis(url, eps, duration):
    import redis
    r = redis.from_url(url, decode_responses=True)
    print(f"[seed-redis] url={url} eps={eps}", flush=True)
    n = 0
    deadline = time.time() + duration
    while _running and time.time() < deadline:
        stream, data = gen_visit(time.time())
        r.xadd(stream, {"data": json.dumps(data, ensure_ascii=False)})
        n += 1
        time.sleep(1.0 / eps)
        if n % 100 == 0:
            print(f"[seed-redis] sent={n}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="流任务灌数工具")
    ap.add_argument("--target", required=True, choices=["kafka", "mqtt", "redis"])
    ap.add_argument("--brokers", default="datara-kafka:9092")
    ap.add_argument("--host", default="datara-emqx")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--url", default="redis://redis:6379/0")
    ap.add_argument("--eps", type=float, default=5.0)
    ap.add_argument("--duration", type=int, default=1800, help="运行秒数（默认 30 分钟）")
    args = ap.parse_args()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    if args.target == "kafka":
        seed_kafka(args.brokers, args.eps, args.duration)
    elif args.target == "mqtt":
        seed_mqtt(args.host, args.port, args.eps, args.duration)
    else:
        seed_redis(args.url, args.eps, args.duration)
    print("[seed] done", flush=True)


if __name__ == "__main__":
    main()
