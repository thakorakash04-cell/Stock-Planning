from test_stock_assistant import accounts
from stock_accounts.lead_time import build,purchasing
from stock_accounts.access import allowed,MENU_LABELS

def table(name,rows):
 return {'name':name,'headers':list(rows[0]),'rows':[list(r.values()) for r in rows]}

def dataset():
 bom={'Material':'FG','Component':'RM','Component(text)':'Raw','Component quantity':2,'Material Type':'ZRAW','Source.Name':'Care.xlsx'}
 movements=[{'Material':'RM','Batch':'0001','Posting Date':d,'Movement Type':m,'Purchase Order':'123'} for d,m in [('2026-01-11',101),('2026-01-15',101),('2026-01-13',321),('2026-01-16',261)]]
 return {'tables':[table('BOM',[bom,bom]),table('Material Document List',movements),table('Order List',[{'Material':'RM','Purchasing Document':123,'Document Date':'01-01-2026'}])], 'sheets':[{'name':'Forecast Planning','headers':[], 'rows':[['FG','Finished',2026,'November',10,0,5,5],['FG','Finished',2026,'December',10,0,5,5]]},{'name':'Forecast Need to Order List','headers':['Component','Component(text)','Component unit','Material Type','Total Required Quantity','Current Stock','Still To be Deliver Quantity','Need to Order Quantity'],'rows':[['RM','Raw','EA','ZRAW',60,20,0,40]]}]}

def test_dates_earliest_and_no_join_weighting():
 d=dataset();t,a=build(d)
 assert len(t['rows'])==1
 assert t['rows'][0][4:11]==['2026-01-01','2026-01-11','2026-01-13','2026-01-16',10,2,5]
 assert a['RM']==[10,2,5]
 # Same batch number on an unrelated material cannot alter the PO or QC date.
 d['tables'][1]['rows'].append(['OTHER','0001','2025-01-01',321,'123'])
 assert build(d)==(t,a)

def test_order_date_cumulative_fg_and_component_cover_once():
 d=dataset();t=purchasing(d)
 # Duplicate BOM rows are distinct source rows, consistent with source total 60.
 # November demand20 consumes current RM20; December demand40 makes shortage.
 assert t['rows'][0][-2]=='2026-11-21'
 assert len(t['rows'][0])==len(t['headers'])
 d['sheets'][1]['rows'][0][7]=0
 assert purchasing(d)['rows'][0][-2] is None

def test_missing_history_and_mismatched_bom_never_invent_dates():
 d=dataset();d['tables'][2]['rows']=[]
 assert purchasing(d)['rows'][0][-2]=='Missing procurement history'
 d=dataset();d['tables'][0]['rows']=[]
 assert purchasing(d)['rows'][0][-2]=='Missing dated forecast / BOM link'

def test_lead_menu_independent_of_gemini_right():
 assert len(MENU_LABELS)==10
 i={'role':'viewer','permissions':{'use_tools':False,'menu_9':True}}
 assert allowed(i,9)
 i['permissions']['menu_9']=False
 assert not allowed(i,9)

def test_standard_bom_demand_is_not_rescaled_to_saved_required():
 d=dataset();d['sheets'][1]['rows'][0][4]=6000
 assert purchasing(d)['rows'][0][-2]=='2026-11-21'
 d['sheets'][1]['rows'][0][5]=100
 assert purchasing(d)['rows'][0][-2]=='No matching dated forecast shortage'

def test_transfers_carry_to_later_months_and_fg_stock_not_repeated():
 d=dataset();d['sheets'][0]['rows'][0][5]=12
 # Transfers 12 + FG stock5 cover all November and7 December; remaining3FG*4RM=12.
 d['sheets'][1]['rows'][0][5]=0
 assert purchasing(d)['rows'][0][-2]=='2026-11-21'

def test_enriched_download_keeps_suggested_date_and_validates_rows(accounts):
 from stock_accounts.workspace_insights import handle_request
 import base64,io
 from openpyxl import load_workbook
 store,admin,viewer=accounts
 d=dataset();store.save_dataset(admin,'master.xlsx',d);current=store.get_dataset(admin)
 result=purchasing(d)
 payload={'action':'planning_table_export','source':'forecast_purchasing','version':current['version'],'headers':result['headers'],'rows':result['rows']}
 export=handle_request(store,viewer,payload)
 rows=list(load_workbook(io.BytesIO(base64.b64decode(export['content']))).active.values)
 assert rows[0][-2]=='Suggested order by date'
 assert rows[0][-1]=='Average Lead Time (Days)'
 assert rows[1][-2]=='2026-11-21'
 assert rows[1][-1]==10

def test_standard_bom_expands_sfg_using_base_quantity():
 d=dataset()
 d['tables'][0]=table('BOM',[{'Material':'FG','Component':'SFG','Component(text)':'Semi','Component quantity':2,'Base quantity':1,'Material Type':'ZSFG','Source.Name':'Care.xlsx'}, {'Material':'SFG','Component':'RM','Component(text)':'Raw','Component quantity':4,'Base quantity':2,'Material Type':'ZRAW','Source.Name':'Care.xlsx'}])
 # RM rate4 per FG; first November5FG consumes20RM exactly, December shortages.
 assert purchasing(d)['rows'][0][-2]=='2026-11-21'

def test_ambiguous_alternative_invalidates_descendant_components():
 d=dataset()
 d['tables'][0]=table('BOM',[{'Material':'FG','Component':'SFG','Component(text)':'Semi','Component quantity':2,'Base quantity':1,'Alternative BOM':1}, {'Material':'FG','Component':'SFG','Component(text)':'Semi','Component quantity':3,'Base quantity':1,'Alternative BOM':2}, {'Material':'SFG','Component':'RM','Component(text)':'Raw','Component quantity':4,'Base quantity':2,'Alternative BOM':1}])
 assert purchasing(d)['rows'][0][-2]=='Check BOM consumption'

def test_average_column_keeps_missing_blank_and_zero_valid():
 from stock_accounts.lead_time import with_average,AVERAGE_HEADER
 t={'headers':['Component','Need'],'rows':[['RM',1],['UNKNOWN',2],['ZERO',3]]}
 result=with_average(t,{}, {'RM':[10.5,None,None],'ZERO':[0,None,None]})
 assert result['headers'][-1]==AVERAGE_HEADER
 assert result['rows']==[['RM',1,10.5],['UNKNOWN',2,None],['ZERO',3,0]]
 assert t['rows']==[['RM',1],['UNKNOWN',2],['ZERO',3]]

def test_calculated_ps_result_includes_po_to_inward_only(accounts):
 from test_planning import dataset as planning_dataset
 from stock_accounts.planning import handle_planning
 store,admin,viewer=accounts;d=planning_dataset()
 d['tables'] += [table('Material Document List',[{'Material':'X','Batch':'001','Posting Date':'2026-01-11','Movement Type':101,'Purchase Order':'123'}]),table('Order List',[{'Material':'X','Purchasing Document':'123','Document Date':'2026-01-01'}])]
 store.save_dataset(admin,'master.xlsx',d);version=store.get_dataset(admin)['version']
 result=handle_planning(store,viewer,{'action':'planning_calculate','version':version,'entries':[{'code':'A','quantity':10}]})
 assert result['headers'][-1]=='Average Lead Time (Days)'
 assert result['rows'][0]==['X','Shared','ZRAW',25,8,3,14,10]
 assert result['rows'][1][-1] is None

def production_dataset():
 d=dataset();d['productionSnapshotDate']='2026-10-10'
 moves=d['tables'][1];moves['headers']+=['Material Type'];moves['rows']=[r+['ZRAW'] for r in moves['rows']]
 d['tables'].append(table('Production Order Details',[{'Order':1,'Material Number':'FG','Material description':'Finished','Batch':'OPEN','Order quantity (GMEIN)':10,'Confirmed quantity (GMEIN)':0,'Basic start date':'2026-10-01','Basic finish date':'2026-11-10','MRP controller':'ZFG'}]))
 return d

def test_only_po_to_inward_offsets_date_even_without_qc_or_use():
 d=dataset();d['tables'][1]['rows']=[r for r in d['tables'][1]['rows'] if r[3]==101]
 assert purchasing(d)['rows'][0][-2]=='2026-11-21'
 # Arbitrarily long QC/use intervals cannot affect this date.
 assert purchasing(d,{'RM':[10,900,1200]})['rows'][0][-2]=='2026-11-21'

def test_dated_ongoing_production_covers_only_forecasts_after_expected_end():
 d=production_dataset()
 # Nov1 demand uses5FG stock, then5FG production demand; Nov10 order covers December.
 assert purchasing(d)['rows'][0][-2]=='No matching dated forecast shortage'
 # Finishing after the December need date must not hide that shortage.
 d['tables'][-1]['rows'][0][7]='2026-12-10'
 assert purchasing(d)['rows'][0][-2]=='2026-11-21'

def test_shared_expected_quantity_and_end_date_override_are_used():
 from stock_accounts.production import build as production_build
 import json
 d=production_dataset();report=production_build({'data':d,'version':'x','updated_at':0});order=report['ongoing'][0]
 override={'kind':'ongoing','id':order['id'],'payload':json.dumps({'quantity':20,'endDate':'2026-10-20'})}
 assert purchasing(d,overrides=[override])['rows'][0][-2]=='Covered by FG stock / production'

def test_qc_stock_is_counted_once_and_same_batch_not_added_as_ongoing():
 d=production_dataset();moves=d['tables'][1]
 moves['rows'].append(['FG','OPEN','2026-10-05',101,None,'ZFGS'])
 # FG worksheet stock5 already includes this QC batch. Do not credit the order10 again.
 assert purchasing(d)['rows'][0][-2]=='2026-11-21'
