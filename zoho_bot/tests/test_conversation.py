import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
import pytest

spec=importlib.util.spec_from_file_location('conversation_tests',Path(__file__).parents[1]/'conversation.py')
c=importlib.util.module_from_spec(spec);sys.modules[spec.name]=c;spec.loader.exec_module(c)

@pytest.fixture
def backend(monkeypatch):
    c.MEMORY.clear()
    monkeypatch.setenv('GEMINI_API_KEY','test')
    monkeypatch.setenv('GEMINI_MODEL','test-model')
    monkeypatch.setenv('AI_DATA_SHARING_ENABLED','true')
    monkeypatch.setenv('CLIQ_USERS_JSON',json.dumps({'user':{'stock':{}}}))
    storage=Mock()
    storage.get_dataset.return_value={'updated_at':123,'data':{'sheets':[{'name':'Orders','headers':['Product','Source.Name','Need'],'rows':[['A','Ostomy',5],['B','Wound',20],['C','Ostomy',7],['D','Ostomy',None]]}],'tables':[]}}
    actor=SimpleNamespace(username='viewer',version=1)
    s=SimpleNamespace(SOURCES={'stock':None},authorize=Mock(return_value=(storage,actor)))
    return s,storage,actor


def body(question='Which products need ordering?',user='user'):
    return SimpleNamespace(organization_id='org',user_id=user,message=question)


def test_filter_sum_full_set():
    table={'name':'Orders','headers':['Segment','Need'],'rows':[['Ostomy',i] for i in range(30)]+[['Other',999],['Ostomy',None]]}
    result=c.analyze(table,c.Analysis(table='Orders',filters=[c.Filter(column='Segment',op='eq',value='Ostomy')],sums=['Need']))
    assert result['totals_all_matches']['Need']=='435'
    assert result['matched_rows']==31 and len(result['rows'])==20
    assert result['blank_numeric_values_excluded']['Need']==1


def test_query_validation():
    table={'name':'x','headers':['Product','Need'],'rows':[['A',None],['B',5]]}
    with pytest.raises(ValueError):c.analyze(table,c.Analysis(table='x',sums=['fake']))
    assert c.analyze(table,c.Analysis(table='x',filters=[c.Filter(column='Need',op='gt',value=0)]))['matched_rows']==1
    with pytest.raises(ValueError):c.analyze(table,c.Analysis(table='x',sums=['Product']))
    with pytest.raises(Exception):c.Analysis.model_validate({'table':'x','sql':'DROP TABLE accounts'})


def test_group_sort():
    table={'name':'x','headers':['Segment','Need'],'rows':[['Ostomy',1],['Other',5],['Ostomy',2]]}
    result=c.analyze(table,c.Analysis(table='x',group_by=['Segment'],sums=['Need'],sort_column='Need'))
    assert result['rows']==[{'Segment':'Other','Need':'5'},{'Segment':'Ostomy','Need':'3'}]


def test_followups_and_fresh_evidence(backend):
    s,storage,_=backend
    plans=[{'workspace':'stock','query':''},{'table':'Orders','filters':[{'column':'Need','op':'gt','value':0}],'sums':['Need']},'There are 3 products requiring 32 units.',
           {'workspace':'stock','query':''},{'table':'Orders','filters':[{'column':'Source.Name','op':'contains','value':'Ostomy'},{'column':'Need','op':'gt','value':0}],'sums':['Need']},'Ostomy needs 12 units.']
    with patch.object(c,'ai',side_effect=plans) as provider:
        assert '32' in c.reply(body(),s)['text']
        assert '12' in c.reply(body('Only Ostomy'),s)['text']
        assert provider.call_args_list[3].args[1]['history'][0]['question']=='Which products need ordering?'
        assert provider.call_args_list[5].args[1]['evidence']['totals_all_matches']['Need']=='12'
        assert storage.get_dataset.call_count==2
        assert storage.require_permission.call_count==4


def test_other_user_has_no_history(backend,monkeypatch):
    s,_,_=backend
    c.remember(('org','user'),(('stock','viewer',1),),[{'question':'private customer'}])
    monkeypatch.setenv('CLIQ_USERS_JSON',json.dumps({'other':{'stock':{}}}))
    with patch.object(c,'ai',return_value={'workspace':'clarify','question':'What data?'}) as provider:
        c.reply(body('Explain that',user='other'),s)
        assert provider.call_args.args[1]['history']==[]


def test_revocation_blocks_ai_and_purges_memory(backend):
    s,_,_=backend
    c.remember(('org','user'),(('stock','viewer',1),),[{'question':'private'}])
    s.authorize.side_effect=HTTPException(403,'disabled')
    with patch.object(c,'ai') as provider,pytest.raises(HTTPException):c.reply(body(),s)
    provider.assert_not_called()
    assert ('org','user') not in c.MEMORY


def test_new_version_discards_old_context(backend):
    s,_,actor=backend
    c.remember(('org','user'),(('stock','viewer',1),),[{'question':'old'}])
    actor.version=2
    with patch.object(c,'ai',return_value={'workspace':'clarify','question':'Which data?'}) as provider:
        c.reply(body(),s)
        assert provider.call_args.args[1]['history']==[]


def test_ai_sharing_optin(backend,monkeypatch):
    s,_,_=backend
    monkeypatch.delenv('AI_DATA_SHARING_ENABLED')
    with patch.object(c,'ai') as provider:
        assert 'AI_DATA_SHARING_ENABLED=true' in c.reply(body(),s)['text']
        provider.assert_not_called()


def test_failed_plan_does_not_reach_answer(backend):
    s,storage,_=backend
    with patch.object(c,'ai',side_effect=[{'workspace':'stock','query':''},{'table':'Orders','filters':[{'column':'secret','op':'eq','value':'x'}]}]) as provider:
        assert 'could not safely' in c.reply(body(),s)['text']
        assert provider.call_count==2
        storage.log_event.assert_not_called()


def test_general_answer_and_reset(backend):
    s,_,_=backend
    with patch.object(c,'ai',side_effect=[{'workspace':'general'},'General guidance: safety stock is a buffer.']):
        assert 'safety stock' in c.reply(body('What is safety stock?'),s)['text']
    assert c.MEMORY
    assert 'cleared' in c.reply(body('reset'),s)['text']
    assert not c.MEMORY


def test_commands_and_natural_input():
    for message in ['stock tables','stock Summary | catheter','boe latest','/research fda laser','awc catalogue foam']:
        assert c.explicit(message)
    for message in ['Which products need ordering?','Only Ostomy','Explain that shortage','stock for Ostomy']:
        assert not c.explicit(message)
