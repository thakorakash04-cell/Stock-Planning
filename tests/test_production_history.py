import pytest
from test_stock_assistant import accounts
from test_production import fixture
from stock_accounts.production import read,save,delete
from stock_accounts.production_history import read as history
from stock_accounts.clock import display
from stock_accounts.workspace_insights import handle_request


def created(store,admin):
    store.save_dataset(admin,'master.xlsx',fixture());status=read(store,admin)
    event={'kind':'upcoming','version':status['version'],'revision':0,'value':{'materialCode':'A','product':'A','description':'Size A','batch':'NEXT','quantity':50,'startDate':'2026-11-01','endDate':'2026-11-10'}}
    return event,save(store,admin,event)['upcoming'][0]


def test_shared_viewer_edit_delete_and_immutable_before_after_history(accounts):
    store,admin,viewer=accounts;event,item=created(store,admin)
    deletion={'action':'production_delete','version':event['version'],'plan_id':item['id'],'revision':item['revision']}
    with pytest.raises(PermissionError):handle_request(store,viewer,deletion)
    store.update_permissions(admin,'viewer_user',{'edit_upcoming':True});viewer=store.login('viewer_user','Test-viewer-password!123')
    edited=save(store,viewer,{**event,'plan_id':item['id'],'revision':1,'value':{**event['value'],'quantity':75,'endDate':'2026-11-11'}})['upcoming'][0]
    assert edited['row'][3]==75 and edited['row'][7].endswith('IST')
    with pytest.raises(ValueError,match='changed'):handle_request(store,viewer,deletion)
    result=handle_request(store,viewer,{**deletion,'revision':2})
    assert result['upcoming']==[] and read(store,admin)['upcoming']==[]
    result=history(store,viewer,{'plan_id':item['id']})
    assert result['events']==3
    assert all(row[0].endswith('IST') for row in result['rows'])
    assert any(row[1]=='viewer_user' and row[3]=='Edited' and row[6]=='Quantity' and row[7:9]==[50,75] for row in result['rows'])
    assert any(row[1]=='viewer_user' and row[3]=='Deleted' and row[6]=='Quantity' and row[7:9]==[75,None] for row in result['rows'])
    from stock_accounts.store import Store
    assert history(Store(store.url),admin,{})['events']==3
    store.update_permissions(admin,'viewer_user',{'menu_3':False});viewer=store.login('viewer_user','Test-viewer-password!123')
    with pytest.raises(PermissionError):history(store,viewer,{})


def test_delete_checks_workbook_revision_and_preserves_existing_data(accounts):
    store,admin,viewer=accounts;event,item=created(store,admin)
    with pytest.raises(ValueError,match='changed'):delete(store,admin,{'plan_id':item['id'],'revision':1,'version':'old'})
    assert len(read(store,admin)['upcoming'])==1
    assert history(store,admin,{})['events']==1


def test_ist_conversion_is_explicit():
    assert display(0)=='01 Jan 1970 05:30:00 IST'
    from stock_accounts.auth import format_time
    assert format_time(1)=='01 Jan 1970 05:30:01 IST'
