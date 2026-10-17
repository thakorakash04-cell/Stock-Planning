"""Attention signals derived from the same read-only planning tools as Ask AI."""
from datetime import datetime
from .clock import IST
from .lead_time import day,num
from .planning_assistant import knowledge,run_tool
from .access import allowed

def prepare(store,actor,tables,views,current,data):
    tables=list(tables);views=list(views);warnings=['All saved rows are reviewed; filters on other tabs and unsaved FG scenarios do not apply. Order Requirements uses the saved worksheet. Units remain separate; no cross-view shortage totals or complete production-feasibility conclusions are inferred.']
    ref=day(current['data'].get('productionSnapshotDate')) or datetime.fromtimestamp(current['updated_at'],IST).date()
    identity=store.identity(actor)
    def add(index,title,table):
        tables.append({'id':'INSIGHT'+str(index),'name':title,'headers':table['headers'],'rows':table['rows']})
        views.append({'view':index,'title':title,'table':title})
    if allowed(identity,9) and data.get('leadTime'):add(9,'Lead time & Consumption',data['leadTime'])
    if allowed(identity,3):
        try:
            evidence,_=run_tool(store,actor,{'operation':'production'},current)
            for index,item in zip((10,11,12),evidence):
                table=item['_table'];headers=table['headers'];rows=[]
                for raw in table['rows']:
                    row=list(raw)
                    if index==10:
                        end=day(row[7]);row.append(max(0,(ref-end).days) if end else None)
                    elif index==11:
                        receipt=day(row[5]);row.append(max(0,(ref-receipt).days) if receipt else None)
                    else:
                        code=str(row[0]);qty=num(row[3]);status='Not checked';missing=None
                        if len(rows)<50:
                            try:
                                from .production_materials import resolve,availability
                                material=resolve(current['data'],{'materialCode':code,'product':code,'description':row[1]})
                                if not material:raise ValueError('Unresolved material')
                                check=availability(current['data'],material['code'],qty)
                                missing=sum(r[-1]=='Shortage' for r in check['rows'])
                                status='Available' if check['available'] else 'Shortage' if missing else 'Cannot verify'
                            except ValueError:status='Cannot verify'
                        row.extend([status,missing])
                    rows.append(row)
                extra=['Days overdue'] if index==10 else ['Days since 101'] if index==11 else ['Material availability','Shortage components']
                add(index,item['table'],{'headers':headers+extra,'rows':rows})
            warnings.append('Upcoming material checks assess up to50 plans independently against the same stock; stock is not reserved across plans. QC age is not a release delay without an agreed SLA.')
        except ValueError as exc:warnings.append('Production review unavailable: '+str(exc))
    attention=[];charts={}
    def signal(view,table,column,op,value,title,action,priority='review'):
        if column not in table['headers']:return
        i=table['headers'].index(column)
        def matches(r):
            x=r[i]
            if op=='eq':return x==value
            n=num(x)
            return n is not None and (n>value if op=='gt' else n<value)
        matching=[r for r in table['rows'] if matches(r)]
        if not matching:return
        ident='A'+str(len(attention)+1)
        item={'id':ident,'view':view,'priority':priority,'title':title,'detail':f'{len(matching):,} of {len(table["rows"]):,} records match {column} {op} {value}.','action':action,'table':table['name'],'count':len(matching)}
        attention.append(item)
        numeric=op in ('gt','lt') or isinstance(value,(int,float))
        label=next((h for h in (('Batch','Material Code') if view==11 else ('Order Number','Material Code') if view==10 else ('Component','Material Code','Material','Product Name','Order Number','Batch')) if h in table['headers']),table['headers'][0])
        metric=column if numeric else next((h for h in ('Shortage components','Quantity','Order Quantity') if h in table['headers']),None)
        if metric:
            charts.setdefault(view,[]).append({'title':title,'attention_id':ident,'finding':item['detail'],'action':action,'type':'bar','label':label,'value':metric,'query':{'table':table['id'],'filters':[{'column':column,'op':op,'value':value}],'columns':list(dict.fromkeys([label,metric])),'sort_by':metric,'descending':True,'limit':10}})
    for view in views:
        table=next((t for t in tables if t['name']==view['table']),None)
        if not table or not table['rows']:continue
        index=view['view'];headers=table['headers']
        if index==5 and 'Suggested order by date' in headers and 'Need to Order Quantity' in headers:
            due=headers.index('Suggested order by date');need=headers.index('Need to Order Quantity')
            age=[]
            for r in table['rows']:
                date_value=day(r[due]);age.append(list(r)+[max(0,(ref-date_value).days) if (num(r[need]) or 0)>0 and date_value else None])
            table={**table,'headers':headers+['Days past suggested order date'],'rows':age}
            tables=[table if t['id']==table['id'] else t for t in tables];headers=table['headers']
        if index in (5,6):
            need=next((h for h in headers if h.lower().replace(' ','')=='needtoorderquantity'),None)
            if need:signal(index,table,need,'gt',0,'Positive material order requirements','Verify the matching materials, on-order quantities and purchasing priority.','high')
        if index==5:
            signal(index,table,'Days past suggested order date','gt',0,'Suggested purchasing dates already passed','Review procurement against the current production coverage and existing orders. Dates use PO-to-inward lead time only.','high')
            if 'Average Lead Time (Days)' in headers:signal(index,table,'Average Lead Time (Days)','eq',None,'Missing procurement lead-time history','Check PO-to-inward dates before relying on suggested order dates.')
        if index==0 and 'Current Stock' in headers:signal(index,table,'Current Stock','eq',0,'Materials with zero current stock','Compare these materials with forecast demand and production coverage before ordering.')
        if index==4 and 'Pending Quantity' in headers:signal(index,table,'Pending Quantity','gt',0,'Forecast demand not covered by transfers and FG stock','Review ongoing and under-QC production before treating this as a new purchasing requirement.')
        if index==10:
            signal(index,table,'Days overdue','gt',0,'Ongoing production past expected end','Confirm the revised expected end date and quantity; assess affected forecasts.','high')
            signal(index,table,'Expected FG Quantity','eq',None,'Ongoing production without an expected FG estimate','Verify an expected FG quantity before relying on this production as forecast coverage.')
        if index==11:signal(index,table,'Days since 101','gt',0,'Under-QC batches by age since receipt','Review the oldest batches with QC; age alone does not establish an overdue release.')
        if index==12:
            signal(index,table,'Material availability','eq','Shortage','Upcoming plans with material shortages','Open plan availability details and review component shortages. Checks do not reserve stock.','high')
            signal(index,table,'Material availability','eq','Cannot verify','Upcoming plans with unverified material availability','Resolve missing stock, units, material identification or BOM alternatives before confirming readiness.')
    attention.sort(key=lambda a:a['priority']!='high')
    return tables,views,{'knowledge':knowledge(),'referenceDate':ref.isoformat(),'attention':attention,'priority_charts':charts,'limitations':warnings}
