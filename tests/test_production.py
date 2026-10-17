import copy,json
from datetime import datetime,timezone
import pytest
from stock_accounts.production import build,read,save
from stock_accounts.workspace_insights import handle_request,ui_payload
from test_stock_assistant import accounts


def fixture():
    orders=[];moves=[]
    def order(n,material,batch,qty,confirmed,start,end):
        orders.append({'Order':n,'Material Number':material,'Batch':batch,'Material description':'Size '+material,'Order quantity (GMEIN)':qty,'Confirmed quantity (GMEIN)':confirmed,'Basic start date':start,'Basic finish date':end,'MRP controller':'ZFG'})
    def move(material,batch,kind,d,qty=0,typ='ZFGS'):
        moves.append({'Material':material,'Batch':batch,'Movement Type':kind,'Posting Date':d,'Material Type':typ,'Quantity':qty})
    order(1,'A','H1',100,100,'2026-08-01','2026-08-20');move('A','H1',321,'2026-08-21',80);move('A','H1',321,'2026-08-21',-80)
    order(2,'A','H2',110,110,'2026-09-01','2026-09-20');move('A','H2',321,'2026-09-21',99)
    order(3,'A','OPEN',100,0,'2026-10-01','2026-10-25')
    order(4,'B','QC',100,90,'2026-06-01','2026-06-20');move('B','QC',101,'2026-06-03');move('B','QC',101,'2026-07-04')
    order(5,'C','QC',100,90,'2026-06-01','2026-06-20');move('C','QC',101,'2026-06-04');move('C','QC',321,'2026-06-05',90)
    order(6,'D','OLD',100,0,'2026-08-31','2026-09-20');move('D','OLD',101,'2026-05-31')
    order(7,'E','NOHISTORY',100,0,'2026-09-01','2026-10-20')
    order(8,'A','FUTURE',100,0,'2026-10-30','2026-11-20')
    def table(name,rows):
        headers=list(rows[0]);return {'name':name,'headers':headers,'rows':[[r.get(h) for h in headers] for r in rows]}
    return {'productionSnapshotDate':'2026-10-10','sheets':[{'name':'Production Data','headers':['Material'],'rows':[['A']]}],
            'tables':[table('Production Order Details',orders),table('Material Document List',moves)]}


def test_snapshot_windows_material_batch_matching_latest_101_and_fg_yield():
    result=build({'data':fixture(),'version':'v1','updated_at':0})
    assert result['referenceDate']=='2026-10-10'
    assert result['qc']['rows']==[['B','Size B','QC',100,90,'2026-07-04',4,'ZFGS']]
    rows={r['row'][0]:r['row'] for r in result['ongoing']}
    assert set(rows)=={3,7}
    assert rows[3][8]==85 # Median released FG/order yields: .8 and .9.
    assert rows[7][8] is None
    assert rows[3][7]=='2026-10-25'


def test_shared_edits_permission_revisions_and_persistence(accounts):
    store,admin,viewer=accounts;store.save_dataset(admin,'master.xlsx',fixture())
    status=read(store,viewer);item=status['ongoing'][0]
    event={'kind':'ongoing','version':status['version'],'id':item['id'],'revision':0,'value':{'quantity':88,'endDate':'2026-10-28'}}
    with pytest.raises(PermissionError):save(store,viewer,event)
    store.update_permissions(admin,'viewer_user',{'edit_production':True,'edit_upcoming':True});viewer=store.login('viewer_user','Test-viewer-password!123')
    updated=save(store,viewer,event);edited=next(i for i in updated['ongoing'] if i['id']==item['id'])
    assert edited['row'][7:9]==['2026-10-28',88] and edited['row'][10]=='viewer_user'
    assert next(i for i in read(store,admin)['ongoing'] if i['id']==item['id'])==edited
    with pytest.raises(ValueError,match='Someone else'):save(store,viewer,event)
    upcoming={'kind':'upcoming','version':status['version'],'revision':0,'value':{'product':'Product A','description':'Size A','batch':'NEXT','quantity':50,'startDate':'2026-11-01','endDate':'2026-11-10'}}
    assert save(store,viewer,upcoming)['upcoming'][0]['row'][:4]==['Product A','Size A','NEXT',50]
    # New Store instance reads the same persistent shared data.
    from stock_accounts.store import Store
    assert len(read(Store(store.url),admin)['upcoming'])==1
    with pytest.raises(ValueError):save(store,viewer,{**upcoming,'value':{**upcoming['value'],'endDate':'2026-10-01'}})
    with pytest.raises(ValueError,match='changed'):save(store,viewer,{**upcoming,'version':'old'})
    store.update_permissions(admin,'viewer_user',{'menu_3':False});viewer=store.login('viewer_user','Test-viewer-password!123')
    with pytest.raises(PermissionError):read(store,viewer)
    with pytest.raises(PermissionError):save(store,viewer,upcoming)


def test_menu_rights_are_admin_only_and_enforced_by_rpc_and_payload(accounts):
    store,admin,viewer=accounts
    with pytest.raises(PermissionError):store.update_permissions(viewer,'viewer_user',{'menu_3':False})
    store.update_permissions(admin,'viewer_user',{'menu_3':False,'menu_6':False,'menu_7':False,'menu_8':False})
    viewer=store.login('viewer_user','Test-viewer-password!123')
    for event in [{'action':'production_status'},{'action':'view','tab':3},{'action':'planning_status'},{'action':'ask_ai'},{'action':'generate_insights'}]:
        with pytest.raises(PermissionError):handle_request(store,viewer,event)
    current={'filename':'test','updated_at':0,'version':'v','data':{'sheets':[{'name':str(i),'headers':['Code'],'rows':[['A']]} for i in range(7)],'tables':[]}}
    payload,_,_=ui_payload(current,store.identity(viewer))
    assert payload['sheets'][3]['rows']==[] and 3 not in payload['accessibleTabs']
    assert payload['sheets'][0]['rows']==[['A']]


def test_month_windows_roll_over_year_and_future_release_does_not_hide_qc():
    from datetime import date
    from stock_accounts.production import month_start
    assert month_start(date(2026,1,10),5)==date(2025,9,1)
    assert month_start(date(2026,1,10),2)==date(2025,12,1)
    d=fixture();t=next(t for t in d['tables'] if t['name']=='Material Document List');h=t['headers']
    t['rows'].append([{'Material':'B','Batch':'QC','Movement Type':321,'Posting Date':'2026-10-11','Material Type':'ZFGS','Quantity':90}.get(k) for k in h])
    assert build({'data':d,'version':'v','updated_at':0})['qc']['rows'][0][2]=='QC'


def test_stale_workbook_cannot_save_and_disabled_edit_right_stays_denied(accounts):
    store,admin,viewer=accounts;store.save_dataset(admin,'master.xlsx',fixture());status=read(store,admin)
    item=status['ongoing'][0];event={'kind':'ongoing','id':item['id'],'revision':0,'version':status['version'],'value':{'quantity':10,'endDate':'2026-10-28'}}
    store.save_dataset(admin,'changed.xlsx',{**fixture(),'changed':True})
    with pytest.raises(ValueError,match='changed'):save(store,admin,event)
    store.update_permissions(admin,'viewer_user',{'edit_upcoming':True})
    viewer=store.login('viewer_user','Test-viewer-password!123')
    with pytest.raises(PermissionError):save(store,viewer,{**event,'version':store.get_dataset(viewer)['version']})
