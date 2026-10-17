from unittest.mock import patch
import base64,io
from openpyxl import load_workbook
from test_stock_assistant import accounts
from test_production import fixture
from stock_accounts.insight_attention import prepare
from stock_accounts.insights import build_report

def attention_fixture(store,admin):
 d=fixture();d['tables'][0]['rows'][2][7]='2026-10-01'
 store.save_dataset(admin,'master.xlsx',d);current=store.get_dataset(admin)
 table={'id':'T1','name':'Purchasing','headers':['Component','Need to Order Quantity','Suggested order by date','Average Lead Time (Days)'],'rows':[['RM1',10,'2026-10-01',25],['RM2',0,None,None]]}
 return prepare(store,admin,[table],[{'view':5,'title':'Forecast purchasing','table':'Purchasing'}],current,{})

def test_attention_uses_shared_production_rules_and_exact_purchasing_counts(accounts):
 store,admin,viewer=accounts;tables,views,context=attention_fixture(store,admin)
 signals={a['title']:a for a in context['attention']}
 assert signals['Suggested purchasing dates already passed']['count']==1
 assert signals['Ongoing production past expected end']['count']==1
 assert context['referenceDate']=='2026-10-10'
 assert context['knowledge']['revision']
 assert {10,11,12}<={v['view'] for v in views}
 assert 'QC age is not' in ' '.join(context['limitations'])
 with patch('stock_accounts.insights.settings',return_value=('key','model')),patch('stock_accounts.insights.generate',side_effect=[{'sections':[]},{'sections':[]}]) as provider:
  report=build_report(tables,views,context)
 assert provider.call_args_list[0].args[3]['planning_context']['knowledge']['revision']==context['knowledge']['revision']
 production=next(s for s in report['sections'] if s['view']==10)
 assert production['charts'][0]['title']=='Ongoing production past expected end'
 assert production['charts'][0]['finding']
 assert any('past expected end' in f for f in production['review']['findings'])
 assert report['attention']==context['attention']

def test_hidden_production_section_is_not_reintroduced_by_insights(accounts):
 store,admin,viewer=accounts;store.save_dataset(admin,'master.xlsx',fixture())
 store.update_permissions(admin,'viewer_user',{'menu_3':False});viewer=store.login('viewer_user','Test-viewer-password!123')
 with patch('stock_accounts.insight_attention.run_tool') as tool:
  _,views,_=prepare(store,viewer,[],[],store.get_dataset(viewer),{})
 tool.assert_not_called();assert not views

def test_richer_review_and_graph_notes_remain_bound_to_evidence(accounts):
 store,admin,viewer=accounts;tables,views,context=attention_fixture(store,admin)
 narrative={'overview':'Review purchase dates and production coverage.','sections':[{'view':5,'findings':['Supported finding '+str(i) for i in range(10)],'actions':['Check orders'],'chart_notes':[{'title':'Positive material order requirements','finding':'These positive requirements need procurement review.','action':'Check existing orders.'},{'title':'Nonexistent graph','finding':'Must never attach'}]}]}
 with patch('stock_accounts.insights.settings',return_value=('key','model')),patch('stock_accounts.insights.generate',side_effect=[{'sections':[]},narrative]):report=build_report(tables,views,context)
 section=next(s for s in report['sections'] if s['view']==5)
 assert len(section['review']['findings'])==10
 assert section['charts'][0]['finding']=='These positive requirements need procurement review.'
 assert all(c.get('finding')!='Must never attach' for c in section['charts'])

def test_derived_graph_sources_and_excel_use_the_server_owned_snapshot(accounts):
 import streamlit as st
 from stock_accounts.assistant_insights import insight_records,export_evidence
 store,admin,viewer=accounts;current=store.get_dataset(admin);version=current['version']
 table={'id':'INSIGHT10','name':'Ongoing production','headers':['Material','Days overdue'],'rows':[['A',9],['B',0]]}
 entry={'version':version,'query':{'table':'INSIGHT10','filters':[{'column':'Days overdue','op':'gt','value':0}]},'source_table':table}
 st.session_state['_stock_insight_sources']={'source':entry};st.session_state['_stock_ai_exports']={'export':entry}
 result=insight_records(store,viewer,{'source_id':'source','version':version},[],version)
 assert result['total']==1 and result['records'][0]['Material']=='A'
 file=export_evidence(store,admin,{'export_id':'export','version':version},[],version)
 workbook=load_workbook(io.BytesIO(base64.b64decode(file['content'])))
 assert list(workbook['Matching records'].values)[1][1]=='A'
