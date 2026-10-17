import copy,json
from unittest.mock import patch
import pytest
from test_stock_assistant import accounts
from test_planning import dataset
from stock_accounts.planning_assistant import knowledge,run_tool,reply

def source(store,admin):
 d=dataset();d['tables'].append({'name':'Planning Quantity','headers':['Material Code','Material Name','Material Type','Unit'],'rows':[['A','FG A','ZFGS','EA'],['B','FG B','ZFGS','EA']]})
 store.save_dataset(admin,'master.xlsx',d);return store.get_dataset(admin)

def test_ps_tool_matches_dashboard_and_is_read_only(accounts):
 from stock_accounts.planning import calculate
 store,admin,viewer=accounts;current=source(store,admin);before=copy.deepcopy(current)
 evidence,scenario=run_tool(store,viewer,{'operation':'ps_plan','entries':[{'code':'a','quantity':10}]},current)
 assert evidence[0]['_table']['rows']==calculate(current['data'],[{'code':'A','quantity':10}])['rows']
 assert scenario['entries']==[{'code':'A','quantity':10}]
 assert store.get_dataset(admin)==before
 for plan in [{'operation':'save'},{'operation':'ps_plan','entries':[{'code':'A','quantity':-1}]}]:
  with pytest.raises(ValueError):run_tool(store,viewer,plan,current)
 store.update_permissions(admin,'viewer_user',{'menu_6':False});viewer=store.login('viewer_user','Test-viewer-password!123')
 with pytest.raises(PermissionError):run_tool(store,viewer,{'operation':'ps_plan','entries':[{'code':'A','quantity':10}]},current)

def test_followup_receives_validated_prior_scenario_and_current_knowledge(accounts):
 store,admin,viewer=accounts;source(store,admin)
 first={'operation':'ps_plan','entries':[{'code':'A','quantity':10}]}
 second={'operation':'ps_plan','entries':[{'code':'A','quantity':20}]}
 with patch('stock_accounts.planning_assistant.settings',return_value=('key','model')),patch('stock_accounts.planning_assistant.generate',side_effect=[first,'First result',second,'Follow-up result']) as provider:
  one=reply(store,viewer,[{'name':'BOM','headers':[],'rows':[]}],'PS for A quantity10',[],None)
  two=reply(store,viewer,[{'name':'BOM','headers':[],'rows':[]}],'Now quantity20',[{'role':'user','text':'PS for A quantity10'}],None,one['scenario'])
 assert provider.call_args_list[2].args[3]['prior_scenario']['entries'][0]['quantity']==10
 assert two['scenario']['entries'][0]['quantity']==20
 assert one['knowledge_revision']==knowledge()['revision']
 assert 'inward' in provider.call_args_list[0].args[3]['knowledge']['rules']

def test_current_repository_knowledge_refreshes_when_deployed_source_changes(tmp_path):
 import stock_accounts.planning_assistant as module
 (tmp_path/'stock_accounts').mkdir();(tmp_path/'PLANNING_RULES.md').write_text('Stock includes QC')
 path=tmp_path/'stock_accounts/planning.py';path.write_text('def calculate():\n return 1\n')
 with patch.object(module,'ROOT',tmp_path):
  before=knowledge();path.write_text('def calculate():\n return 2\n');after=knowledge()
 assert before['revision']!=after['revision']
 assert 'return 2' in str(after['deployed_features'])
 assert 'ADMIN_PASSWORD' not in str(after)

def test_planning_result_excel_is_scoped_and_followup_state_clears(accounts):
 import base64,io
 from openpyxl import load_workbook
 from stock_accounts.workspace_insights import handle_request
 store,admin,viewer=accounts;current=source(store,admin)
 with patch('stock_accounts.planning_assistant.settings',return_value=('key','model')),patch('stock_accounts.planning_assistant.generate',side_effect=[{'operation':'ps_plan','entries':[{'code':'A','quantity':10}]},'Result']):
  answer=handle_request(store,admin,{'action':'ask_ai','version':current['version'],'question':'PS for A10','consent':True})
 e=answer['evidence'][0];assert '_table' not in e
 download=handle_request(store,admin,{'action':'ai_export','version':current['version'],'export_id':e['export_id']})
 assert list(load_workbook(io.BytesIO(base64.b64decode(download['content']))).active.values)[1][0]=='X'
 import streamlit as st
 assert st.session_state['_planning_scenarios']
 handle_request(store,admin,{'action':'ai_clear'})
 assert not st.session_state['_planning_scenarios']

def test_production_chat_does_not_archive_or_edit_shared_plans(accounts):
 from test_production import fixture
 from stock_accounts.production import schema
 store,admin,viewer=accounts;store.save_dataset(admin,'master.xlsx',fixture());current=store.get_dataset(admin)
 payload={'product':'A','materialCode':'A','description':'Size A','batch':'OPEN','quantity':10,'startDate':'2026-10-01','endDate':'2026-10-25'}
 with store.transaction() as db:
  schema(store,db);store.run(db,'INSERT INTO production_shared VALUES (?,?,?,?,?,?)',('upcoming','a'*32,json.dumps(payload),1,admin.username,1))
 evidence,_=run_tool(store,viewer,{'operation':'production'},current)
 assert evidence
 with store.transaction() as db:
  row=store.run(db,'SELECT kind,revision FROM production_shared WHERE id=?',('a'*32,)).fetchone()
 assert row['kind']=='upcoming' and row['revision']==1
