import copy
import pytest
from stock_accounts.production_materials import catalogue,availability
from stock_accounts.production import read,save,check_availability
from stock_accounts.workspace_insights import handle_request
from test_stock_assistant import accounts
from test_production import fixture


def data():
    d=fixture()
    def table(name,headers,rows):d['tables'].append({'name':name,'headers':headers,'rows':rows})
    table('BOM',['Material','Material(text)','Component','Component(text)','Material Type','Base quantity','Component quantity','Component unit','Bill of material','Alternative BOM','Item Number','Sum of Stock Data.Current Stock','Sum of Order List.Still to be delivered (qty)'],[
        ['A','Size A','RM','Raw','ZRAW',10,3,'EA',1,1,10,10,10000],
        ['A','Size A','RM','Raw','ZRAW',10,3,'EA',1,1,10,10,10000], # Join duplicate.
        ['A','Size A','S','Semi','ZSFG',10,1,'EA',1,1,20,20,0]])
    table('Stock Data',['Material','Unrestricted','In Quality Insp.','Base Unit of Measure'],[['RM',5,5,'EA'],['S',0,20,'EA']])
    return d


def test_catalogue_contains_fg_sfg_but_not_raw_and_check_is_explained():
    d=data();catalog={m['code']:m for m in catalogue(d)}
    assert 'A' in catalog and 'S' in catalog and 'RM' not in catalog
    result=availability(d,'A',100)
    assert result['available'] is False
    assert result['rows'][0]==['RM','Raw','EA',30,10,20,'Shortage']
    assert len(result['calculations'])==2
    assert result['calculations'][0][2:6]==[100,10,3,30]
    assert 'On-order stock is not counted' in result['explanation']
    result=availability(d,'A',10)
    assert result['available'] is True and all(r[5]==0 for r in result['rows'])


def test_missing_bom_unknown_stock_units_and_base_cannot_claim_green():
    d=data()
    with pytest.raises(ValueError,match='No BOM'):availability(d,'S',10)
    d['tables'][-2]['rows'][0][5]=None
    assert not availability(d,'A',10)['available']
    d=data();d['tables'][-1]['rows'][0][3]='KG'
    assert availability(d,'A',10)['rows'][0][-1]=='Cannot verify'
    d=data();d['tables'][-1]['rows'][0][1]=None;d['tables'][-1]['rows'][0][2]=None
    assert availability(d,'A',10)['rows'][0][-1]=='Cannot verify'


def test_saved_selection_is_canonical_and_availability_uses_saved_quantity(accounts):
    store,admin,viewer=accounts;store.save_dataset(admin,'master.xlsx',data());status=read(store,viewer)
    plan=save(store,admin,{'kind':'upcoming','version':status['version'],'revision':0,'value':{'materialCode':'A','product':'forged','description':'forged','batch':'NEXT','quantity':100,'startDate':'2026-11-01','endDate':'2026-11-02'}})['upcoming'][0]
    assert plan['row'][:2]==['A','Size A'] and plan['materialCode']=='A'
    event={'action':'production_availability','version':status['version'],'plan_id':plan['id'],'revision':1,'quantity':1}
    result=handle_request(store,viewer,event)
    assert result['quantity']==100 and result['rows'][0][5]==20
    with pytest.raises(ValueError,match='changed'):handle_request(store,viewer,{**event,'revision':0})
    with pytest.raises(ValueError,match='changed'):handle_request(store,viewer,{**event,'version':'old'})
    store.update_permissions(admin,'viewer_user',{'menu_3':False});viewer=store.login('viewer_user','Test-viewer-password!123')
    with pytest.raises(PermissionError):handle_request(store,viewer,event)


def test_production_value_exports_validate_new_row_selection(accounts):
    store,admin,viewer=accounts;store.save_dataset(admin,'master.xlsx',data());status=read(store,viewer);item=status['ongoing'][0]
    event={'action':'matched_export','version':status['version'],'scope':'related','tab':3,'col':2,
           'selection':{'kind':'ongoing','id':item['id'],'row':item['row']},'table':'Production Order Details','headers':['Material Number'],'rows':[[item['row'][2]]]}
    assert handle_request(store,viewer,event)['filename']=='Matched_records.xlsx'
    with pytest.raises(ValueError):handle_request(store,viewer,{**event,'rows':[['NOT MATCHED']]})
    with pytest.raises(ValueError):handle_request(store,viewer,{**event,'selection':{**event['selection'],'id':'forged'}})
