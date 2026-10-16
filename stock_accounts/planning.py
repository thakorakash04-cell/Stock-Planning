"""The master workbook's BOM -> Need to Order Sheet (PS) query, in Python.

Required Quantity is Int64.From(plan * Component quantity), rounded to even
per BOM row, before grouping. Stock is List.Min per component group, not Sum.
There is deliberately no base-quantity division, FG-stock deduction, recursive
BOM explosion or zero clamp: none is present in the master's PS query.
"""
from __future__ import annotations
import math,secrets
import streamlit as st

HEADERS=['Component','Component(text)','Material Type','Required Quantity',
         'Total Available Stock','Total On-order Stock','Need to Order Quantity']
STOCK='Sum of Stock Data.Current Stock'
ORDER='Sum of Order List.Still to be delivered (qty)'
REQUIRED=['Material','Material(text)','Component','Component(text)','Material Type',
          'Component quantity',STOCK,ORDER]


def bom_rows(dataset):
    table=next((t for t in dataset.get('tables',[]) if t['name']=='BOM'),None)
    if not table or not all(h in table['headers'] for h in REQUIRED):
        raise ValueError('Planning requires the embedded BOM model with component quantities, available stock and on-order stock. Refresh All in the master workbook, save, then upload it again.')
    return [dict(zip(table['headers'],r)) for r in table['rows']]


def number(value,label,nullable=False):
    if value is None and nullable:return None
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite number.')
    return value


def int64(value):
    if not math.isfinite(value):raise ValueError('Calculated quantity is outside the workbook range.')
    result=round(value)  # Power Query Int64.From default: RoundingMode.ToEven
    if not -(2**63)<=result<2**63:raise ValueError('Calculated quantity exceeds the workbook whole-number range.')
    return result


def options(dataset):
    found={}
    for r in bom_rows(dataset):
        code=r.get('Material')
        if not code or not r.get('Component'):continue
        if code not in found:
            found[code]={'code':code,'description':r.get('Material(text)') or '',
                         'segment':r.get('Source.Name') or '', 'unit':r.get('Base unit of measure') or ''}
    return sorted(found.values(),key=lambda r:r['code'])


def calculate(dataset,entries):
    rows=bom_rows(dataset)
    if not isinstance(entries,list) or not 1<=len(entries)<=1000:
        raise ValueError('Enter between 1 and 1,000 FG planning quantities.')
    valid={r['Material'] for r in rows if r.get('Material') and r.get('Component')}
    plans={}
    for entry in entries:
        if not isinstance(entry,dict):raise ValueError('Invalid planning row.')
        code=entry.get('code')
        if not isinstance(code,str) or code not in valid:raise ValueError('Choose an FG material with BOM records in the current workbook.')
        if code in plans:raise ValueError('Each FG material can be entered only once.')
        qty=number(entry.get('quantity'),'Planning quantity')
        if qty<0 or qty!=int(qty) or qty>=2**63:raise ValueError('Planning quantities must be non-negative whole numbers within the workbook range.')
        if qty>0:plans[code]=qty
    if not plans:raise ValueError('Enter a quantity greater than zero for at least one FG material.')
    groups={}
    for r in rows:
        if r.get('Material') not in plans or not r.get('Component'):continue
        key=tuple(r.get(h) for h in HEADERS[:3])
        group=groups.setdefault(key,{'required':[],'stock':[],'order':[]})
        component=number(r.get('Component quantity'),'BOM component quantity',True)
        if component is not None:group['required'].append(int64(plans[r['Material']]*component))
        for name,col in [('stock',STOCK),('order',ORDER)]:
            v=number(r.get(col),col,True)
            if v is not None:group[name].append(v)
    result=[]
    for key,g in groups.items():
        required=sum(g['required']) if g['required'] else None
        stock=min(g['stock']) if g['stock'] else None
        order=min(g['order']) if g['order'] else None
        need=None if any(v is None for v in (required,stock,order)) else int64(required-stock-order)
        result.append([*key,required,stock,order,need])
    result.sort(key=lambda r:tuple(str(v or '') for v in r[:3]))
    return {'headers':HEADERS,'rows':result,'materials':len(plans),'components':len(result)}


def handle_planning(store,actor,event):
    current=store.get_dataset(actor)  # Always rechecks active user/session.
    if not current:raise ValueError('Upload the master workbook before planning.')
    version=current['version']
    if event.get('action')=='planning_status':
        return {'version':version,'options':options(current['data'])}
    if event.get('version')!=version:raise ValueError('The workbook changed. Reload planning materials and enter your quantities again.')
    result=calculate(current['data'],event.get('entries'))
    store.record_access(actor,'Order requirements planning')
    plan_id=secrets.token_urlsafe(18)
    st.session_state['_order_plan_export']={'owner':(actor.username,actor.session_id),'version':version,'plan_id':plan_id,'table':result}
    return {**result,'version':version,'plan_id':plan_id}


def export_planning_table(store,actor,event):
    from .matched_export import export_table
    current=store.get_dataset(actor)
    if not current or event.get('version')!=current['version']:
        raise ValueError('The workbook changed. Reload this table before downloading.')
    source=event.get('source')
    names={'forecast_purchasing':'Forecast Need to Order List','order_requirements_saved':'Need to Order Sheet-B.O. PS'}
    if not isinstance(source,str):raise ValueError('Invalid purchasing table.')
    if source in names:
        table=next((s for s in current['data'].get('sheets',[]) if s['name']==names[source]),None)
        if table is None:raise ValueError('This purchasing worksheet is unavailable.')
    elif source=='order_requirements_plan':
        saved=st.session_state.get('_order_plan_export',{})
        if saved.get('owner')!=(actor.username,actor.session_id) or saved.get('version')!=current['version'] or not saved.get('plan_id') or saved.get('plan_id')!=event.get('plan_id'):
            raise ValueError('This planning result has expired. Calculate the plan again before downloading.')
        table=saved['table']
    else:raise ValueError('Only Forecast purchasing and Order requirements tables are available for this download.')
    label='Forecast purchasing' if source=='forecast_purchasing' else 'Order requirements'
    return export_table(store,actor,event,current,table,label,label.replace(' ','_')+'.xlsx')

TABLE_EXPORT_REVISION=1
