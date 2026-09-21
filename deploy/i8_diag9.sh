#!/bin/bash
echo "--- job5 spec 的 kafka 参数 ---"
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e \
  "SELECT SUBSTRING(spec_json, 1, 400) FROM datara_meta.t_stream_job WHERE id=5\G" 2>/dev/null
cat > /tmp/probe3.py <<'EOF'
import socket, threading, time

def probe(tag):
    for i in range(6):
        t0 = time.time()
        try:
            infos = socket.getaddrinfo("datara-kafka", 9092, proto=socket.IPPROTO_TCP)
            ips = {f"{ai[4][0]}:{ai[4][1]}" for ai in infos}
            s = socket.create_connection(("datara-kafka", 9092), timeout=3)
            s.close()
            print(f"[{tag}#{i+1}] OK {time.time()-t0:.2f}s ips={ips}")
        except OSError as e:
            print(f"[{tag}#{i+1}] FAIL {time.time()-t0:.2f}s {type(e).__name__}: {e}")
        time.sleep(0.5)

probe("main")
t = threading.Thread(target=probe, args=("daemon",), daemon=True)
t.start()
t.join()
EOF
docker cp /tmp/probe3.py datara-worker:/tmp/probe3.py
docker exec datara-worker python /tmp/probe3.py
