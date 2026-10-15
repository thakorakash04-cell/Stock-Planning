import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[3]
os.environ['REPOS_ROOT'] = str(ROOT)
spec = importlib.util.spec_from_file_location('unified_bot', Path(__file__).resolve().parents[1] / 'service.py')
s = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = s
spec.loader.exec_module(s)

@pytest.fixture
def configured(monkeypatch, tmp_path):
    monkeypatch.setenv('CLIQ_GATEWAY_KEY', 'x'*40)
    monkeypatch.setenv('CLIQ_ORGANIZATION_ID', 'org1')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///'+str(tmp_path/'accounts.db'))
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    s.store.cache_clear()
    s.COUNTS.clear()
    actors = {}
    for workspace in s.SOURCES:
        storage = s.store(workspace)
        storage.bootstrap_admin('admin_user', 'Test-only-long-password!')
        admin = storage.login('admin_user', 'Test-only-long-password!')
        storage.create_viewer(admin, 'viewer_user', 'Viewer-only-password!')
        viewer = storage.login('viewer_user', 'Viewer-only-password!')
        actors[workspace] = (storage, admin, viewer)
    monkeypatch.setenv('CLIQ_USERS_JSON', json.dumps({'user1': {w:{'username':'viewer_user','version':a[2].version} for w,a in actors.items()}}))
    return TestClient(s.app), actors


def ask(client, text, **overrides):
    return client.post('/chat', headers={'X-API-Key':'x'*40}, json={'message':text,'user_id':'user1','organization_id':'org1','chat_type':'bot',**overrides})


def test_no_credentials(configured):
    c,_ = configured
    assert c.post('/chat',json={}).status_code == 401


def test_tenant_and_group_blocked(configured):
    c,_ = configured
    assert ask(c,'/help',organization_id='other').status_code == 403
    assert ask(c,'/stock tables',chat_type='channel').status_code == 403


def test_unknown_user_not_sent_to_ai(configured):
    c,_ = configured
    with patch.object(s,'route',side_effect=AssertionError):
        assert ask(c,'find stock',user_id='unknown').status_code == 403


def test_stock_reads_shared_saved_data(configured):
    c, actors = configured
    store,admin,_ = actors['stock']
    store.save_dataset(admin,'test.xlsx',{'sheets':[{'name':'Summary','headers':['Material','Quantity'],'rows':[['catheter',12],['foam',5]]}],'tables':[]})
    response = ask(c,'/stock Summary | catheter')
    assert response.status_code == 200
    assert 'Quantity: 12' in response.json()['text']
    assert 'foam' not in response.json()['text']
    assert any(r['action']=='tool_use' for r in store.access_log(admin))


def test_each_workspace_can_be_disabled(configured):
    c,actors = configured
    for w,(store,admin,viewer) in actors.items():
        store.update_viewer(admin,'viewer_user',active=False)
        assert ask(c,'/'+w+' latest').status_code == 403


def test_permission_and_password_revoke(configured):
    c,actors = configured
    store,admin,viewer = actors['boe']
    store.change_password(viewer,'Viewer-only-password!','Updated-viewer-password!')
    assert ask(c,'/boe latest').status_code == 403
    store,admin,viewer = actors['research']
    store.update_permissions(admin,'viewer_user',{'use_tools':False})
    assert ask(c,'/research fda laser').status_code == 403


def test_boe_real_engine(configured):
    c,_ = configured
    body={'header':{'exchange_rate':80,'invoice_value_fc':100,'freight_inr':0},'items':[{'material_name':'test','quantity':10,'unit_price_fc':10,'bcd_rate_percent':10}]}
    r=ask(c,'/boe calculate '+json.dumps(body))
    assert r.status_code == 200
    assert '"total_bcd": 800.0' in r.json()['text']
    assert '"total_igst": 1598.4' in r.json()['text']
    body['items'][0]['quantity']=-1
    assert 'Invalid command data' in ask(c,'/boe calculate '+json.dumps(body)).json()['text']


def test_fda_mocked(configured):
    c,_ = configured
    class Response:
        status_code=200
        def raise_for_status(self):pass
        def json(self):return {'results':[{'k_number':'K123456','device_name':'laser'}],'meta':{'results':{'total':1}}}
    with patch.object(s.requests,'get',return_value=Response()) as get:
        r=ask(c,'/research fda laser')
        assert 'K123456' in r.json()['text']
        assert get.call_args.kwargs['params']['limit']==20


def test_awc_catalogue_and_safety(configured):
    c,_ = configured
    r=ask(c,'/awc catalogue foam')
    assert r.status_code==200
    assert 'AWC catalogue' in r.json()['text']
    assert 'Invalid command data' in ask(c,'/awc assess {}').json()['text']
    s.awc_modules()
    from core.models import WoundAssessment
    data=WoundAssessment(etiology='diabetic_foot_ulcer',exudate_level='heavy',depth_type='exposed_bone_tendon').model_dump(mode='json')
    data['clinician_confirmed']=True
    r=ask(c,'/awc assess '+json.dumps(data))
    assert r.status_code==200
    assert '"allow_product_browsing":false' in r.json()['text']


def test_row_cap(configured):
    text=s.rows_reply('test',['n'],[[i] for i in range(100)],100)
    assert 'n: 19' in text and 'n: 20' not in text


def test_rate_limit(configured):
    c,_=configured
    for _ in range(15):assert ask(c,'/help').status_code==200
    assert ask(c,'/help').status_code==429
