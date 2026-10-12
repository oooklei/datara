from common.models import MetaTag, MetaTagging


def test_i19_tag_crud_and_diff_set(client, db_session):
    r = client.post('/api/v1/meta/tags', json={'name': '核心', 'cat': '重要性'})
    assert r.status_code == 200
    tid = r.json()['data']['id']
    assert client.post('/api/v1/meta/tags', json={'name': '核心'}).status_code == 409
    r = client.post('/api/v1/meta/taggings', json={'tagIds': [tid], 'targetType': 'model', 'targetKey': 'model/1'})
    assert r.status_code == 200
    assert r.json()['data']['tagIds'] == [tid]
    assert client.get('/api/v1/meta/tags').json()['data'][0]['cnt'] == 1
    assert db_session.query(MetaTagging).count() == 1
    assert client.delete(f'/api/v1/meta/tags/{tid}').status_code == 200
    assert db_session.query(MetaTag).count() == 0 and db_session.query(MetaTagging).count() == 0


def test_i19_catalog_models_and_ext(client, db_session):
    from tests.test_model_api import _seed_dicts, _mk_model
    _seed_dicts(db_session)
    mid = _mk_model(client, code='dwd_meta_catalog')
    rows = client.get('/api/v1/meta/catalog/tables?layer=DWD').json()['data']
    assert rows['total'] == 1 and rows['list'][0]['key'] == f'model/{mid}'
    r = client.put('/api/v1/meta/catalog/table/1/demo/orders/ext', json={'bizDomain': '交易域', 'owner': 'tester'})
    assert r.status_code == 200 and r.json()['data']['bizDomain'] == '交易域'


def test_i19_map_projection_exposes_model_nodes_and_declared_edges(client, db_session):
    from tests.test_model_api import _seed_dicts, _mk_model
    from common.models import DwModelRelation
    _seed_dicts(db_session)
    a = _mk_model(client, code='dwd_map_a')
    b = _mk_model(client, code='dwd_map_b')
    db_session.add(DwModelRelation(src_model_id=a, tgt_model_id=b, rel_type='1:N'))
    db_session.commit()
    d = client.get('/api/v1/meta/map?view=domain').json()['data']
    assert d['stats']['models'] == 2
    assert {e['source'] for e in d['edges']} == {f'model/{a}'}


def test_i19_catalog_introspection_cache_and_layer_inference(client, db_session, monkeypatch):
    from common.models import DataSource
    from api import meta
    ds = DataSource(name='测试库', type='mysql', db_name='biz')
    db_session.add(ds); db_session.commit()

    class Cursor:
        def execute(self, *_args): pass
        def fetchall(self): return [('ods_order', '订单原始表', 12), ('dwd_order', '订单明细', 8)]
        def __enter__(self): return self
        def __exit__(self, *_args): pass
    class Conn:
        def cursor(self): return Cursor()
        def close(self): pass
    calls = {'n': 0}
    def fake_open(*_args, **_kwargs):
        calls['n'] += 1; return Conn()
    monkeypatch.setattr(meta, 'open_connection', fake_open)
    first = client.get(f'/api/v1/meta/catalog/tables?ds={ds.id}&db=biz').json()['data']
    second = client.get(f'/api/v1/meta/catalog/tables?ds={ds.id}&db=biz').json()['data']
    assert first['total'] == 2 and first['list'][0]['layer'] == 'ODS'
    assert second['total'] == 2 and calls['n'] == 1
