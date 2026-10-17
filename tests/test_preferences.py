import pytest
from test_stock_assistant import accounts
from stock_accounts.preferences import read
from stock_accounts.workspace_insights import handle_request


def test_preferences_are_private_persistent_and_scoped_to_each_table(accounts):
    store,admin,viewer=accounts
    value={'filters':{'Material':{'text':'A'}},'hidden':['Qty'],'sums':['Total'],'sort':{'column':'Material','dir':1}}
    handle_request(store,viewer,{'action':'preferences_save','scope':'grid:main:Summary','value':value,'username':admin.username})
    handle_request(store,viewer,{'action':'preferences_save','scope':'grid:production:ongoing','value':{'hidden':['Batch']}})
    assert read(store,viewer)['grid:main:Summary']==value
    assert read(store,viewer)['grid:production:ongoing']=={'hidden':['Batch']}
    assert read(store,admin)=={}
    from stock_accounts.store import Store
    other=Store(store.url);viewer2=other.login('viewer_user','Test-viewer-password!123')
    assert read(other,viewer2)['grid:main:Summary']==value
    handle_request(other,viewer2,{'action':'preferences_save','scope':'grid:main:Summary','value':{'filters':{},'hidden':[]}})
    assert read(store,viewer)['grid:main:Summary']=={'filters':{},'hidden':[]}
    assert read(store,viewer)['grid:production:ongoing']=={'hidden':['Batch']}


@pytest.mark.parametrize('scope,value',[('',{}),('x'*241,{}),('grid:main',[]),('grid:main',{'bad':float('nan')}),('grid:main',{'text':'x'*100001})])
def test_invalid_preferences_are_rejected(accounts,scope,value):
    store,admin,viewer=accounts
    with pytest.raises(ValueError):handle_request(store,viewer,{'action':'preferences_save','scope':scope,'value':value})


def test_disabled_viewers_cannot_save_or_read_preferences(accounts):
    store,admin,viewer=accounts;store.update_viewer(admin,viewer.username,active=False)
    with pytest.raises(PermissionError):read(store,viewer)
    with pytest.raises(PermissionError):handle_request(store,viewer,{'action':'preferences_save','scope':'grid:main','value':{}})
