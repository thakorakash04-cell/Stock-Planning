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
def test_bad_plans_are_isolated_and_valid_coverage_survives(change):
    tables,views,plan=fixture();chart=plan['sections'][0]['charts'][0]
    if change=='wrong_table':chart['query']['table']='T2'
    if change=='text_metric':chart['value']='Material'
    if change=='missing_view':plan['sections']=[]
    if change=='duplicate_view':views.append({'view':1,'title':'Other','table':'Stock'});plan['sections']*=2
    with patch('stock_accounts.insights.settings',return_value=('key','model')),patch('stock_accounts.insights.generate',return_value=plan):
        report=build_report(tables,views)
    assert len(report['sections'])==len(views)
    assert all(s['review']['findings'] and s['review']['actions'] for s in report['sections'])
    assert all(c['evidence']['table_id']=='T1' and c['value']!='Material' for s in report['sections'] for c in s['charts'])

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

def test_broad_coverage_uses_distinct_fields_and_safe_composition():
    tables=[{'id':'T1','name':'Stock','headers':['Material','Stock','Demand','Pending','Segment'],
             'rows':[['A',5,12,7,'Alpha'],['B',-2,4,6,'Beta'],['C',0,2,2,'Alpha']]}]
    views=[{'view':0,'title':'Stock overview','table':'Stock'}]
    plan={'sections':[{'view':0,'charts':[{'title':'Stock','type':'column','label':'Material','value':'Stock','query':{'table':'T1','columns':['Material','Stock'],'limit':10}}]}]}
    narrative={'overview':'Stock needs review.','sections':[{'view':0,'findings':['Negative balance recorded.'],'actions':['Verify stock.'],'data_quality':['Snapshot only.']}]}
    with patch('stock_accounts.insights.settings',return_value=('key','model')),patch('stock_accounts.insights.generate',side_effect=[plan,narrative]):
        result=build_report(tables,views)
    charts=result['sections'][0]['charts']
    assert len(charts)>=4
    assert {'Stock','Demand','Pending','count(*)'}<=set(c['value'] for c in charts)
    assert any(c['type']=='donut' for c in charts)
    assert result['sections'][0]['review']['findings']==['Negative balance recorded.']
    assert result['overview']=='Stock needs review.'


def test_trends_and_donuts_require_suitable_data():
    from stock_accounts.insights import chart_result
    tables,views,plan=fixture();view={'table_id':'T1'};chart=plan['sections'][0]['charts'][0]
    assert chart_result(tables,view,{**chart,'type':'line'})['type']=='column'
    assert chart_result(tables,view,{**chart,'type':'donut'})['type']=='bar'
    dated=[{'id':'T1','name':'Dated','headers':['Date','Qty'],'rows':[['2026-10-02',2],['2026-10-01',4]]}]
    c={'title':'Dated','type':'area','label':'Date','value':'Qty','query':{'table':'T1','columns':['Date','Qty']}}
    result=chart_result(dated,view,c)
    assert result['type']=='area'
    assert [r['Date'] for r in result['evidence']['records']]==['2026-10-01','2026-10-02']


def test_graph_source_rows_are_paginated_and_authorized(accounts):
    from stock_accounts.workspace_insights import handle_request as request
    import streamlit as st
    store,admin,viewer=accounts
    rows=[['A'+str(i),i] for i in range(120)]
    store.save_dataset(admin,'source.xlsx',{'sheets':[{'name':'Stock','headers':['Material','Qty'],'rows':rows}],'tables':[]})
    version=request(store,viewer,{'action':'ai_status'})['version']
    st.session_state['_stock_insight_sources']={'token':{'version':version,'query':{'table':'T1','filters':[{'column':'Qty','op':'gte','value':10}]}}}
    event={'action':'insight_records','version':version,'source_id':'token','page':0}
    result=request(store,viewer,event)
    assert result['total']==110 and len(result['records'])==50
    assert result['records'][0]['Qty']==10
    assert len(request(store,viewer,{**event,'page':2})['records'])==10
    with pytest.raises(ValueError,match='expired'):request(store,viewer,{**event,'source_id':'forged'})
    with pytest.raises(ValueError,match='changed'):request(store,viewer,{**event,'version':'old'})
    store.update_permissions(admin,'viewer_user',{'use_tools':False});viewer=store.login('viewer_user','Test-viewer-password!123')
    with pytest.raises(Exception,match='[Pp]ermission|[Aa]ccess'):request(store,viewer,event)

@pytest.mark.parametrize('review',[
 {'sections':[{'view':'0','findings':['Stock fact'],'actions':['Check stock']}]},
 {'sections':{'0':{'key_findings':['Stock fact'],'suggested_actions':'Check stock'}}},
 {'sections':[{'title':'Stock overview','review':{'observations':['Stock fact'],'recommendations':['Check stock']}}]},
])
def test_review_formats_are_normalized(review):
    tables,views,plan=fixture()
    with patch('stock_accounts.insights.settings',return_value=('key','model')),patch('stock_accounts.insights.generate',side_effect=[plan,review]):result=build_report(tables,views)
    assert result['sections'][0]['review']['findings']==['Stock fact']
    assert result['sections'][0]['review']['actions']==['Check stock']
    assert result['sections'][0]['review_mode']=='ai'


def test_narrative_failure_keeps_calculated_findings_and_actions():
    tables,views,plan=fixture()
    with patch('stock_accounts.insights.settings',return_value=('key','model')),patch('stock_accounts.insights.generate',side_effect=[plan,ValueError('Quota reached')]):result=build_report(tables,views)
    section=result['sections'][0]
    assert section['charts'] and section['review']['findings'] and section['review']['actions']
    assert section['review_mode']=='calculated' and 'Quota reached' in result['warnings'][0]


def test_invalid_chart_does_not_discard_valid_charts_and_styles_vary():
    tables,views,plan=fixture()
    plan['sections'][0]['charts'].insert(0,{'query':{'table':'T1','metrics':[{'column':'Qty','op':'divide'}]}})
    with patch('stock_accounts.insights.settings',return_value=('key','model')),patch('stock_accounts.insights.generate',side_effect=[plan,{}]):result=build_report(tables,views)
    section=result['sections'][0]
    assert section['issues'] and section['charts'][0]['title']=='Highest stock'
    assert len(set(c['type'] for c in section['charts']))>=2
