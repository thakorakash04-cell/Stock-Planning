import json
from unittest.mock import Mock,patch
import pandas as pd
import pytest
from grounded_ai import execute_query,ask,context_for,tables_from_frames,settings,generate

TABLES=[{'id':'T1','name':'Stock','headers':['Material','Qty','Segment'],'rows':[['A',5,'X'],['B',0,'Y'],['C',None,'X'],['D',10,'X']]}]

def test_calculations_use_all_matches_before_limit_and_preserve_missing():
    result=execute_query(TABLES,{'table':'T1','filters':[{'column':'Segment','op':'eq','value':'X'}],'group_by':[],'metrics':[{'column':'Qty','op':'sum'},{'column':'*','op':'count'}],'limit':1})
    assert result['matched_records']==3 and result['records']==[{'sum(Qty)':15.0,'count(*)':3}]
    result=execute_query(TABLES,{'table':'T1','filters':[{'column':'Material','op':'eq','value':'C'}],'metrics':[{'column':'Qty','op':'sum'}]})
    assert result['records']==[{'sum(Qty)':None}]

def test_raw_sort_and_source_ids_are_stable():
    result=execute_query(TABLES,{'table':'T1','columns':['Material','Qty'],'sort_by':'Qty','descending':True,'limit':1})
    assert result['matched_records']==4 and result['shown_rows']==1 and result['result_rows']==4
    assert result['records']==[{'Source row':'T1:R4','Material':'D','Qty':10}]

def test_grouping_and_literal_search():
    result=execute_query(TABLES,{'table':'T1','group_by':['Segment'],'metrics':[{'column':'*','op':'count'}],'sort_by':'count(*)','limit':20})
    assert result['records']==[{'Segment':'X','count(*)':3},{'Segment':'Y','count(*)':1}]
    result=execute_query(TABLES,{'table':'T1','filters':[{'column':'Material','op':'contains','value':'.*'}]})
    assert result['matched_records']==0

@pytest.mark.parametrize('plan',[{'table':'T1','code':'__import__("os")'},{'table':'accounts'},{'table':'T1','columns':['password']},{'table':'T1','filters':[{'column':'Qty','op':'eval','value':'1'}]},{'table':'T1','metrics':[{'column':'Qty','op':'execute'}]},{'table':'T1','limit':999}])
def test_rejects_arbitrary_code_tables_fields_and_unbounded_results(plan):
    with pytest.raises(ValueError):execute_query(TABLES,plan)

def test_selected_context_must_be_a_real_server_record():
    context={'table':'Stock','row':['A',5,'X'],'column':'Qty'}
    assert context_for(TABLES,context)['source']=='T1:R1'
    with pytest.raises(ValueError):context_for(TABLES,{**context,'row':['A',900,'X']})

def test_key_is_only_in_header_and_http_errors_do_not_echo_provider_content():
    with patch('grounded_ai.requests.post') as post:
        post.return_value=Mock(status_code=429)
        post.return_value.json.return_value={'error':{'message':'private-secret private-record'}}
        with pytest.raises(ValueError,match='quota') as caught:generate('private-secret','model','system',{'question':'q'})
        assert 'private-secret' not in str(caught.value) and 'private-record' not in str(caught.value)
        assert post.call_args.kwargs['headers']['x-goog-api-key']=='private-secret'
        assert 'private-secret' not in json.dumps(post.call_args.kwargs['json'])

def test_question_plan_calculation_and_grounded_response():
    with patch('grounded_ai.settings',return_value=('secret','model')),patch('grounded_ai.generate',side_effect=[{'queries':[{'table':'T1','metrics':[{'column':'Qty','op':'sum'}]}],'clarification':''},'Loaded total is 15 [Q1].']) as call:
        result=ask(TABLES,'What is the total quantity?')
        assert result['evidence'][0]['records']==[{'sum(Qty)':15.0}]
        assert call.call_args.args[3]['evidence']==result['evidence']
        assert 'secret' not in json.dumps(call.call_args.args[3])

def test_missing_key_or_loaded_data_does_not_call_provider():
    with patch('grounded_ai.settings',return_value=('','model')),patch('grounded_ai.generate') as call:
        with pytest.raises(ValueError,match='GEMINI_API_KEY'):ask(TABLES,'q')
        call.assert_not_called()
    with patch('grounded_ai.settings',return_value=('secret','model')),patch('grounded_ai.generate') as call:
        with pytest.raises(ValueError,match='Load data'):ask([],'q')
        call.assert_not_called()

def test_frame_dates_nulls_and_numeric_values_are_json_safe():
    tables=tables_from_frames([('Dates',pd.DataFrame({'date':[pd.Timestamp('2026-01-01')],'missing':[float('nan')],'number':[5]}))])
    assert tables[0]['rows']==[['2026-01-01T00:00:00.000',None,5]]


def test_configuration_uses_streamlit_secrets_and_keeps_model_override():
    with patch('grounded_ai.st.secrets',{'GEMINI_API_KEY':' secret-key ','ASK_AI_MODEL':'models/custom-model'}),patch.dict('os.environ',{'GEMINI_API_KEY':'other-key'}):
        assert settings()==('secret-key','custom-model')
