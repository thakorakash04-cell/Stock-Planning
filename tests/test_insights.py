from unittest.mock import patch
import pytest
from stock_accounts.insights import build_report
from test_stock_assistant import accounts
from stock_accounts.workspace import handle_request

def fixture():
    tables=[{'id':'T1','name':'Stock','headers':['Material','Qty'],'rows':[['A',3],['B',9],['C',2]]}]
    views=[{'view':0,'title':'Stock overview','table':'Stock'}]
    chart={'title':'Highest stock','query':{'table':'T1','columns':['Material','Qty'],'sort_by':'Qty','descending':True,'limit':2},'label':'Material','value':'Qty'}
    return tables,views,{'sections':[{'view':0,'charts':[chart],'limitation':'Units as supplied'}]}

def test_chart_values_are_calculated_from_full_table():
    tables,views,plan=fixture()
    with patch('stock_accounts.insights.settings',return_value=('key','model')),patch('stock_accounts.insights.generate',side_effect=[plan,'Review actions']):
        result=build_report(tables,views)
    e=result['sections'][0]['charts'][0]['evidence']
    assert e['matched_records']==3 and e['shown_rows']==2
    assert [r['Qty'] for r in e['records']]==[9,3]
    assert result['answer']=='Review actions'

@pytest.mark.parametrize('change',['wrong_table','text_metric','missing_view','duplicate_view'])
def test_bad_plans_are_rejected(change):
    tables,views,plan=fixture();chart=plan['sections'][0]['charts'][0]
    if change=='wrong_table':chart['query']['table']='T2'
    if change=='text_metric':chart['value']='Material'
    if change=='missing_view':plan['sections']=[]
    if change=='duplicate_view':views.append({'view':1,'title':'Other','table':'Stock'});plan['sections']*=2
    with patch('stock_accounts.insights.settings',return_value=('key','model')),patch('stock_accounts.insights.generate',return_value=plan):
        with pytest.raises(ValueError):build_report(tables,views)

def test_report_permission_consent_and_version(accounts):
    store,admin,viewer=accounts
    version=handle_request(store,viewer,{'action':'ai_status'})['version']
    event={'action':'generate_insights','version':version}
    with patch('stock_accounts.insights.build_report') as build:
        with pytest.raises(ValueError,match='sharing'):handle_request(store,viewer,event)
        with pytest.raises(ValueError,match='changed'):handle_request(store,viewer,{**event,'consent':True,'version':'old'})
        build.assert_not_called()
    store.update_permissions(admin,'viewer_user',{'use_tools':False});viewer=store.login('viewer_user','Test-viewer-password!123')
    with pytest.raises(Exception,match='[Pp]ermission|[Aa]ccess'):handle_request(store,viewer,{**event,'consent':True})

def test_fresh_dispatch_works_with_stale_modules(accounts):
    import sys,types
    from stock_accounts.workspace_insights import handle_request as fresh_request
    store,admin,viewer=accounts
    old_workspace=types.ModuleType('stock_accounts.workspace')
    old_assistant=types.ModuleType('stock_accounts.assistant')
    def stale(*args):raise ValueError('Unknown operation.')
    old_workspace.handle_request=stale
    old_assistant.handle_ai=stale
    with patch.dict(sys.modules,{'stock_accounts.workspace':old_workspace,'stock_accounts.assistant':old_assistant}):
        status=fresh_request(store,viewer,{'action':'ai_status'})
        result={'sections':[],'answer':'Verified report'}
        with patch('stock_accounts.insights.build_report',return_value=result) as build:
            response=fresh_request(store,viewer,{'action':'generate_insights','consent':True,'version':status['version']})
        assert response['answer']=='Verified report'
        build.assert_called_once()
