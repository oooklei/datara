import urllib.request, json, sys, time

API = "http://192.168.1.9:8000/api/v1"
TOKEN = sys.argv[1]

# Get code first
req = urllib.request.Request(API + '/workflow-definitions/wf_8182a5d0',
    headers={'Authorization': f'Bearer {TOKEN}'})
with urllib.request.urlopen(req, timeout=10) as resp:
    d = json.loads(resp.read())
    wf_code = d['data']['code']
    print(f"code={wf_code}")

# Run
req2 = urllib.request.Request(API + f'/workflow-definitions/{wf_code}/run',
    data=json.dumps({"priority": 3}).encode(),
    headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'},
    method='POST')
with urllib.request.urlopen(req2, timeout=15) as resp:
    r = json.loads(resp.read())
    print(f"run: {json.dumps(r, ensure_ascii=False)[:500]}")
    instance_id = r.get('data', {}).get('instance_id')
    print(f"instance_id={instance_id}")
