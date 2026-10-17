"""Material/batch timing from the supplied Days Calculation Power Query rules."""
from collections import defaultdict
from datetime import date, datetime, timedelta
import calendar, math

HEADERS=['Component','Component(text)','Batch','Purchase Order','PO Date','Inward Date','QC Date','Use Date','Procurement Lead Time','QC Release Days','FG CONVERSION DATE FROM THE INWARD','Material Type','Source.Name']

def records(dataset,name):
    t=next((t for t in dataset.get('tables',[]) if t['name']==name),None)
    return [dict(zip(t['headers'],r)) for r in t['rows']] if t else []

def key(value):
    if value is None:return ''
    return str(value).strip().removesuffix('.0').upper()

def day(value):
    if isinstance(value,datetime):return value.date()
    if isinstance(value,date):return value
    if not value:return None
    for fmt in ('%Y-%m-%d','%d-%m-%Y','%d/%m/%Y'):
        try:return datetime.strptime(str(value)[:10],fmt).date()
        except ValueError:pass
    return None

def num(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None

def build(dataset):
    bom=records(dataset,'BOM');components={key(r.get('Component')) for r in bom};meta={}
    for r in bom:
        k=key(r.get('Component'));m=meta.setdefault(k,{'name':r.get('Component(text)'), 'type':r.get('Material Type'),'segments':set()})
        if r.get('Source.Name'):m['segments'].add(str(r['Source.Name']).rsplit('.',1)[0])
    po=defaultdict(set)
    for r in records(dataset,'Order List'):
        d=day(r.get('Document Date'))
        if d:po[(key(r.get('Purchasing Document')),key(r.get('Material')))].add(d)
    batches={}
    for r in records(dataset,'Material Document List'):
        material,batch=key(r.get('Material')),key(r.get('Batch'));d=day(r.get('Posting Date'))
        if material not in components or not batch or not d:continue
        b=batches.setdefault((material,batch),{'dates':{},'pos':set()})
        movement=key(r.get('Movement Type'));old=b['dates'].get(movement)
        if old is None or d<old:b['dates'][movement]=d
        order=key(r.get('Purchase Order'))
        if order and order!='0':b['pos'].add(order)
    rows=[]
    def iso(d):return d.isoformat() if d else None
    def diff(a,b):return (a-b).days if a and b else None
    for (material,batch),b in sorted(batches.items()):
        ds=b['dates'];inward=min((ds[m] for m in ('101','102','105','106') if m in ds),default=None)
        use=min((ds[m] for m in ('261','262') if m in ds),default=None);qc=ds.get('321');m=meta[material]
        for order in sorted(b['pos']) or [None]:
            dates=po.get((order,material),set());pod=next(iter(dates)) if len(dates)==1 else None
            rows.append([material,m['name'],batch,order,iso(pod),iso(inward),iso(qc),iso(use),diff(inward,pod),diff(qc,inward),diff(use,inward),m['type'],', '.join(sorted(m['segments']))])
    # One observation per material/batch/interval, never weighted by BOM joins or PO repetition.
    observations=defaultdict(lambda:[{}, {}, {}])
    for r in rows:
        for i in range(3):
            if r[8+i] is not None and r[8+i]>=0:observations[r[0]][i].setdefault(r[2],set()).add(r[8+i])
    averages={k:[sum(sum(x)/len(x) for x in v.values())/len(v) if v else None for v in groups] for k,groups in observations.items()}
    return {'headers':HEADERS,'rows':rows},averages

def production_supply(dataset,current=None,overrides=()):
    """Reuse the Production windows; QC stock is already in planning stock."""
    from .production import build as production_build
    import json,time
    current=current or {'data':dataset,'version':'calculation','updated_at':time.time()}
    try:report=production_build(current)
    except ValueError:return {},set(),None
    qc_pairs={(key(r[0]),key(r[2])) for r in report['qc']['rows']}
    saved={r['id']:json.loads(r['payload']) for r in overrides if r['kind']=='ongoing'}
    events=defaultdict(list);seen=set();ref=day(report['referenceDate'])
    for item in report['ongoing']:
        r=item['row'];pair=(key(r[2]),key(r[4]))
        if pair in qc_pairs or pair in seen:continue
        seen.add(pair);override=saved.get(item['id'])
        quantity=num(override['quantity']) if override else num(r[8])
        if quantity is None:quantity=num(r[5])  # SAP order quantity when no yield estimate exists.
        available=day(override['endDate'] if override else r[7])
        if quantity is not None and quantity>0 and available:
            events[pair[0]].append((max(available,ref),quantity))
    # Confirmed QC batches are already included in Unrestricted + In Quality Insp.
    # They are available at the snapshot for planning, without a QC duration lag.
    # Excluding these pairs above prevents counting an order in both windows.
    return events,qc_pairs,ref

def purchasing(dataset,averages=None,current=None,overrides=()):
    source=next((s for s in dataset.get('sheets',[]) if s['name']=='Forecast Need to Order List'),None)
    if not source:return None
    if averages is None:_,averages=build(dataset)
    # Allocate outstanding monthly FG demand chronologically, deducting FG stock once.
    forecast=next((s for s in dataset.get('sheets',[]) if s['name']=='Forecast Planning'),{'rows':[]})
    products=defaultdict(list)
    for r in forecast['rows']:
        if len(r)<8:continue
        try:
            month=list(calendar.month_name).index(str(r[3])) if not str(r[3]).isdigit() else int(r[3]);d=date(int(r[2]),month,1)
        except (ValueError,TypeError):continue
        products[key(r[0])].append((d,num(r[4]) or 0,num(r[6]),num(r[5]) or 0))
    supplies,qc_pairs,reference=production_supply(dataset,current,overrides)
    balances={}
    for r in records(dataset,'Stock Data'):
        code=key(r.get('Material'));value=num(r.get('Current Stock'))
        if value is None:
            unrestricted=num(r.get('Unrestricted'));quality=num(r.get('In Quality Insp.'))
            value=unrestricted+quality if unrestricted is not None and quality is not None else None
        if value is not None:balances[code]=balances.get(code,0)+value
    # Forecast worksheet stock is authoritative for each forecasted product.
    tasks=[]
    for product,months in products.items():
        balances[product]=next((v for _,_,v,_ in months if v is not None),0)+sum(t for _,_,_,t in months)
        tasks.extend((max(d,reference) if reference else d,product,qty) for d,qty,_,_ in months if qty>0)
    available_events={code:sorted(values) for code,values in supplies.items()}
    def uncovered(code,quantity,needed):
        pending=available_events.setdefault(code,[])
        while pending and pending[0][0]<=needed:
            _,amount=pending.pop(0);balances[code]=balances.get(code,0)+amount
        taken=min(max(balances.get(code,0),0),quantity)
        balances[code]=balances.get(code,0)-taken
        return quantity-taken
    demand=defaultdict(lambda:defaultdict(float))
    boms=defaultdict(list)
    for b in records(dataset,'BOM'):boms[key(b.get('Material'))].append(b)
    invalid=set()
    def invalidate(parent,visited=None):
        visited=set() if visited is None else visited
        if parent in visited:return
        visited.add(parent)
        for b in boms[parent]:
            component=key(b.get('Component'));invalid.add(component)
            if component in boms:invalidate(component,visited)
    for d,product,requested in sorted(tasks):
        qty=uncovered(product,requested,d)
        if qty<=0:continue
        def consume(parent,quantity,path):
            if parent in path:
                invalidate(parent);return
            alternatives={str(b.get('Alternative BOM') or '') for b in boms[parent]}
            if len(alternatives)>1:
                invalidate(parent);return
            seen=set()
            for b in boms[parent]:
                component=key(b.get('Component'));rate=num(b.get('Component quantity'))
                base=num(b.get('Base quantity',1))
                if rate is None or rate<0 or base is None or base<=0:
                    invalid.add(component);continue
                if b.get('Item Number') is not None:
                    fingerprint=tuple(str(b.get(h)) for h in ('Bill of material','Alternative BOM','Item Number','Plant','Component','Component quantity','Base quantity'))
                    if fingerprint in seen:continue
                    seen.add(fingerprint)
                required=rate if str(b.get('Fixed quantity') or '').strip().upper()=='X' else quantity/base*rate
                demand[component][d]+=required
                if component in boms:
                    remaining=uncovered(component,required,d)
                    if remaining>0:consume(component,remaining,path|{parent})
        consume(product,qty,set())
    linked=set()
    def link(parent,visited):
        if parent in visited:return
        visited.add(parent)
        for b in boms[parent]:
            component=key(b.get('Component'));linked.add(component)
            if component in boms:link(component,visited)
    for product in products:link(product,set())
    out=[]
    for row in source['rows']:
        r=list(row);code=key(r[0]);need=num(r[7]) if len(r)>7 else None;due=None
        if need is not None and need>0:
            avg=averages.get(code,[None,None,None]);stock=num(r[5]);onorder=num(r[6]);coverage=None if stock is None or onorder is None else stock+onorder
            if code in invalid:due='Check BOM consumption'
            elif coverage is None:due='Missing stock / on-order'
            elif sum(demand[code].values())<=0:due='Covered by FG stock / production' if code in linked else 'Missing dated forecast / BOM link'
            elif avg[0] is None:due='Missing procurement history'
            else:
                shortage=None
                scheduled=sorted(supplies.get(code,[]))
                for d,qty in sorted(demand[code].items()):
                    while scheduled and scheduled[0][0]<=d:
                        _,amount=scheduled.pop(0);coverage+=amount
                    # Standard BOM consumption determines the monthly shortage directly.
                    coverage-=qty
                    if coverage<0:shortage=d;break
                if shortage:
                    # Only the historical PO-generation-to-inward interval offsets the need date.
                    due=(shortage-timedelta(days=math.ceil(avg[0]))).isoformat()
                else:due='No matching dated forecast shortage'
        out.append(r+[due])
    return with_average({**source,'headers':source['headers']+['Suggested order by date'],'rows':out},dataset,averages)

AVERAGE_HEADER='Average Lead Time (Days)'

def with_average(table,dataset,averages=None):
    """Append numeric PO-to-inward batch means; unavailable history stays null."""
    if averages is None:_,averages=build(dataset)
    if AVERAGE_HEADER in table['headers']:return table
    return {**table,'headers':table['headers']+[AVERAGE_HEADER],
            'rows':[list(r)+[averages.get(key(r[0]),[None])[0]] for r in table['rows']]}

REVISION=3
