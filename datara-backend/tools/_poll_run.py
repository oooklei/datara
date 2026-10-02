import urllib.request, json, time

API = "http://192.168.1.9:8000/api/v1"
r = urllib.request.urlopen(urllib.request.Request(API + '/login',
    data=json.dumps({'user_name':'admin','user_pwd':'Admin@123'}).encode(),
    headers={'Content-Type':'application/json'}), timeout=10)
TOKEN = json.loads(r.read())['data']['token']

# First get command/instance
req = urllib.request.Request(API + '/instances?page=1&size=3&sort=created_at&order=desc',
    headers={'Authorization': f'Bearer {TOKEN}'})
with urllib.request.urlopen(req, timeout=10) as resp:
    d = json.loads(resp.read())
    if d.get('code') == 0:
        items = d['data'].get('items', d['data'].get('list', []))
        if isinstance(d['data'], list):
            items = d['data']
        print(f"Latest instances: {json.dumps(items[:3], ensure_ascii=False)[:600]}")
    else:
        print(json.dumps(d, ensure_ascii=False)[:500])
