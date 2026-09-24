"""C7 收口验证：探测 1.9 后端 schemas 端点（运行时契约）。"""
import json
import sys
import urllib.request

BASE = "http://192.168.1.9:8000/api/v1"


def req(path, method="GET", body=None, token=""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["token"] = token
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main():
    code, body = req("/login", "POST", {"user_name": "admin", "user_pwd": "Admin@123"})
    if not isinstance(body, dict) or body.get("code") != 0:
        print("LOGIN_FAIL", code, body)
        return 1
    token = (body.get("data") or {}).get("token") or ""
    print("LOGIN_OK token_len=", len(token))

    # 列出数据源，找一个 mysql/greatdb（连接型）
    code, body = req("/datasources", "GET", token=token)
    print("DATASOURCES code=", code)
    if code == 0:
        code = body.get("code")
    rows = body.get("data") if isinstance(body, dict) else None
    if isinstance(rows, list):
        print("datasource count=", len(rows))
        conn = [r for r in rows if r.get("type") in ("mysql", "greatdb")]
        print("conn-type=", [(r.get("id"), r.get("name"), r.get("type")) for r in conn[:5]])
        if conn:
            ds_id = conn[0]["id"]
            code, body = req(f"/datasources/{ds_id}/schemas", "GET", token=token)
            print("SCHEMAS http_code=", code)
            if isinstance(body, dict):
                print("SCHEMAS code=", body.get("code"), "msg=", body.get("msg"))
                schemas = body.get("data")
                if isinstance(schemas, list):
                    print("schemas dbs=", [s.get("db") for s in schemas[:5]])
                    first = schemas[0] if schemas else None
                    if first:
                        print("first db tables=", [t.get("name") for t in first.get("tables", [])[:3]])
                        t0 = (first.get("tables") or [{}])[0]
                        print("first table cols=", [c.get("name") for c in t0.get("columns", [])[:5]])
                else:
                    print("SCHEMAS data is not list:", type(schemas))
            else:
                print("SCHEMAS body=", body)
            return 0
    print("NO_CONN_DS")
    return 0


sys.exit(main())