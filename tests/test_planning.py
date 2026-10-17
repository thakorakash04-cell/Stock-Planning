import pytest
from stock_accounts.planning import calculate,options,REQUIRED,STOCK,ORDER
from test_stock_assistant import accounts


def dataset():
    headers=REQUIRED+['Base quantity','Base unit of measure','Source.Name']
    # A's base quantity is deliberately 100. PS multiplies component quantity
    # directly; dividing by BOM base or deducting FG stock would change results.
    rows=[['A','FG A','X','Shared','ZRAW',2.5,8,3,100,'EA','S'],
          ['A','FG A','Y','Only A','ZPKG',0.5,10,0,100,'EA','S'],
          ['B','FG B','X','Shared','ZRAW',1.5,8,3,1,'BOX','S'],
          ['C','FG C','Z','Unselected','ZRAW',10,4,0,1,'EA','S']]
    return {'tables':[{'name':'BOM','headers':headers,'rows':rows}], 'sheets':[]}


def test_shared_components_round_per_bom_row_and_deduct_stock_once():
    result=calculate(dataset(),[{'code':'A','quantity':1},{'code':'B','quantity':1}])
    # 2.5 -> 2 and 1.5 -> 2, not rounding the aggregate or rounding up.
    assert result['rows']==[['X','Shared','ZRAW',4,8,3,-7],['Y','Only A','ZPKG',0,10,0,-10]]
    assert result['materials']==2 and result['components']==2
    assert all(r[0]!='Z' for r in result['rows'])
    assert options(dataset())[0]['unit']=='EA'


def test_same_group_uses_min_not_sum_and_nulls_remain_null():
    d=dataset();d['tables'][0]['rows'][2][6]=6
    result=calculate(d,[{'code':'A','quantity':2},{'code':'B','quantity':2}])
    assert result['rows'][0]==['X','Shared','ZRAW',8,6,3,-1]
    d['tables'][0]['rows'][0][6]=None
    assert calculate(d,[{'code':'A','quantity':1}])['rows'][0][-1] is None


@pytest.mark.parametrize('entries',[
 [],[{'code':'A','quantity':0}],[{'code':'A','quantity':-1}],
 [{'code':'A','quantity':1.5}],[{'code':'A','quantity':True}],
 [{'code':'A','quantity':float('inf')}],[{'code':'A','quantity':'10'}],
 [{'code':'unknown','quantity':1}],
 [{'code':'A','quantity':1},{'code':'A','quantity':2}],
])
def test_invalid_plans_are_rejected(entries):
    with pytest.raises(ValueError):calculate(dataset(),entries)


def test_missing_model_is_not_silently_replaced_with_saved_totals():
    with pytest.raises(ValueError,match='embedded BOM'):calculate({'tables':[]},[{'code':'A','quantity':1}])


def test_plan_requests_are_authorized_versioned_and_leave_shared_data_unchanged(accounts):
    from stock_accounts.workspace_insights import handle_request
    store,admin,viewer=accounts
    store.save_dataset(admin,'master.xlsx',dataset())
    original=store.get_dataset(viewer)
    status=handle_request(store,viewer,{'action':'planning_status'})
    event={'action':'planning_calculate','version':status['version'],'entries':[{'code':'A','quantity':4}]}
    assert handle_request(store,viewer,event)['rows'][0][6]==-1
    assert store.get_dataset(viewer)==original
    with pytest.raises(ValueError,match='changed'):handle_request(store,viewer,{**event,'version':'old'})
    store.update_viewer(admin,'viewer_user',active=False)
    with pytest.raises(Exception,match='[Ss]ession|[Aa]ccess|[Aa]ccount'):handle_request(store,viewer,event)
