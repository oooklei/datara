def _body(code='pay_amount', name='支付金额', **kw):
    d = {'code': code, 'name': name, 'bizDef': '支付成功订单金额', 'techDef': 'SUM(amount)', 'srcKind': 'table', 'srcRef': '1/biz/dwd_order', 'srcField': 'amount', 'aggFn': 'SUM', 'numField': 'amount', 'timeField': 'dt', 'dimField': 'channel'}
    d.update(kw); return d


def test_i20_indicator_crud_publish_change_and_versions(client):
    r = client.post('/api/v1/indicators', json=_body())
    assert r.status_code == 200
    iid = r.json()['data']['id']
    assert client.post('/api/v1/indicators', json=_body(code='pay_amount_2')).status_code == 409
    assert client.post(f'/api/v1/indicators/{iid}/publish').json()['data']['status'] == 'published'
    assert client.post(f'/api/v1/indicators/{iid}/change', json=_body(bizDef='支付成功订单含税金额', reason='税口径调整')).json()['data']['version'] == 2
    assert client.get(f'/api/v1/indicators/{iid}/versions').json()['data'][0]['version'] == 2


def test_i20_consistency_exact_rules_and_config_validation(client):
    assert client.post('/api/v1/indicators', json=_body(code='m1', name='同名')).status_code == 200
    assert client.post('/api/v1/indicators', json=_body(code='m2', name='另名', techDef='SUM(amount)')).status_code == 200
    d = client.get('/api/v1/indicators/consistency').json()['data']
    assert any(x['result'] == 'warn' for x in d['items'])
    bad = client.post('/api/v1/indicators', json=_body(code='bad_filter', name='过滤注入', filterCond='x=1; DROP TABLE t'))
    assert bad.status_code == 400


def test_i20_unconfigured_trend_is_explainable_400(client):
    r = client.post('/api/v1/indicators', json=_body(code='no_query', name='无取数', aggFn=None, timeField=None))
    iid = r.json()['data']['id']
    out = client.get(f'/api/v1/indicators/{iid}/trend')
    assert out.status_code == 400 and '未配置' in out.json()['msg']


def test_i20_trend_and_breakdown_execute_controlled_sql(client, db_session, monkeypatch):
    from common.models import DataSource
    from api import ind
    ds = DataSource(name='指标源', type='mysql', db_name='biz'); db_session.add(ds); db_session.commit()
    r = client.post('/api/v1/indicators', json=_body(code='m_query', name='可查询指标', srcRef=f'{ds.id}/biz/dwd_order'))
    iid = r.json()['data']['id']
    class Cursor:
        def __init__(self): self.sql = ''
        def execute(self, sql): self.sql = sql
        def fetchall(self):
            if 'GROUP BY DATE' in self.sql: return [('2026-10-11', 12), ('2026-10-10', 10)]
            return [('wx', 7), ('app', 5)]
        def __enter__(self): return self
        def __exit__(self, *_args): pass
    class Conn:
        def __init__(self): self.cur = Cursor()
        def cursor(self): return self.cur
        def close(self): pass
    conns = []
    def fake_open(*_args, **_kwargs):
        c = Conn(); conns.append(c); return c
    monkeypatch.setattr(ind, 'open_connection', fake_open)
    trend = client.get(f'/api/v1/indicators/{iid}/trend?days=2').json()['data']
    breakdown = client.get(f'/api/v1/indicators/{iid}/breakdown').json()['data']
    assert trend['stats']['today'] == 12 and len(trend['series']) == 2
    assert breakdown['items'][0]['name'] == 'wx' and breakdown['total'] == 12
    assert all('SUM(amount)' not in c.cur.sql for c in conns)  # tech_def is never executed
