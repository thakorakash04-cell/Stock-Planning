"""Snapshot-based production views and transactional shared planning edits."""
import hashlib,json,math,re,time,uuid
from datetime import date,datetime,timezone
from statistics import median
from .access import require_menu
from .clock import IST,display as timestamp
from .production_history import record as history_record

REVISION=6
QC_HEADERS=['Material Code','Description','Batch','Order Quantity','Confirmed Quantity','Latest 101 Date','Order Number','Material Type']
ONGOING_HEADERS=['Order Number','Material Type','Material Code','Description','Batch','Order Quantity','Basic Start Date','Expected End Date','Expected FG Quantity','Estimate Basis','Last Saved By','Last Saved At (IST)']
PLAN_HEADERS=['Product Name','Description','Batch','Quantity','Start Date','End Date','Last Saved By','Last Saved At (IST)','Segment']

def day(v):
    if isinstance(v,datetime):return v.date()
    if isinstance(v,date):return v
    if not v:return None
    s=str(v).strip()
    for fmt in ('%Y-%m-%d','%d-%m-%Y','%d/%m/%Y'):
        try:return datetime.strptime(s[:10],fmt).date()
        except ValueError:pass
    return None

def month_start(ref,months):
    n=ref.year*12+ref.month-1-(months-1)
    return date(n//12,n%12+1,1)

def ident(v):
    if v is None:return ''
    if isinstance(v,(float,int)) and not isinstance(v,bool) and float(v).is_integer():return str(int(v))
    return str(v).strip()

def records(dataset,name,required):
    t=next((t for t in dataset.get('tables',[]) if t['name']==name),None)
    if not t or any(h not in t['headers'] for h in required):raise ValueError('Production needs the embedded '+name+' table. Refresh and upload the master workbook with source records.')
    return [dict(zip(t['headers'],r)) for r in t['rows']]

def number(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def order_key(r):return hashlib.sha256(json.dumps([ident(r.get('Order')),ident(r.get('Material Number')),ident(r.get('Batch'))]).encode()).hexdigest()

def build(current):
    dataset=current['data'];ref=day(dataset.get('productionSnapshotDate'))
    basis='Production worksheet updated date'
    if not ref:ref=datetime.fromtimestamp(current['updated_at'],IST).date();basis='Workbook upload date (worksheet date unavailable; refresh and re-upload to capture it)'
    orders=records(dataset,'Production Order Details',['Order','Batch','Material Number','Material description','Order quantity (GMEIN)','Confirmed quantity (GMEIN)','Basic start date','Basic finish date'])
    moves=records(dataset,'Material Document List',['Material','Batch','Movement Type','Posting Date','Material Type'])
    types={};receipts={};released=set();released_qty={};seen_moves=set();bybatch={}
    for m in moves:
        material=ident(m.get('Material'));batch=ident(m.get('Batch'));d=day(m.get('Posting Date'));key=(material,batch)
        if m.get('Material Type'):types[material]=m['Material Type']
        if not material or not batch or not d or d>ref:continue
        if ident(m.get('Movement Type'))=='321':
            released.add(key)
            amount=m.get('Quantity')
            if not number(amount):amount=m.get('Qty in Un. of Entry')
            document=ident(m.get('Material Document'));item=ident(m.get('Material Doc.Item'))
            movement_id=(document,item,ident(m.get('Material Doc. Year')),ident(m.get('Plant'))) if document and item else None
            # SAP records both the QC stock outflow and unrestricted-stock
            # inflow for 321. Count only the positive receiving side.
            if number(amount) and amount>0 and (movement_id is None or movement_id not in seen_moves):
                released_qty[key]=released_qty.get(key,0)+amount
                if movement_id:seen_moves.add(movement_id)
        if ident(m.get('Movement Type'))=='101' and str(m.get('Material Type','')).upper() in ('ZFGS','ZSFG','ZFG','FG','SFG'):
            if key not in receipts or d>receipts[key][0]:receipts[key]=(d,m)
    for r in orders:
        bybatch.setdefault((ident(r.get('Material Number')),ident(r.get('Batch'))),[]).append(r)
    qc=[]
    for key,(d,m) in receipts.items():
        if key[1][0].isdigit() or key in released or not month_start(ref,5)<=d<=ref:continue
        matches=bybatch.get(key,[])
        for r in matches or [{}]:
            qc.append([key[0],r.get('Material description') or m.get('Material Description'),key[1],r.get('Order quantity (GMEIN)'),r.get('Confirmed quantity (GMEIN)'),d.isoformat(),r.get('Order'),m.get('Material Type')])
    ongoing=[]
    for r in orders:
        batch=ident(r.get('Batch'))
        if batch and batch[0].isdigit():continue
        start=day(r.get('Basic start date'));qty=r.get('Order quantity (GMEIN)');confirmed=r.get('Confirmed quantity (GMEIN)')
        if not number(confirmed) or confirmed!=0 or not start or not month_start(ref,2)<=start<=ref or r.get('Deletion flag'):continue
        material=ident(r.get('Material Number'));history=[]
        for h in orders:
            end=day(h.get('Basic finish date'));hq=h.get('Order quantity (GMEIN)');hc=h.get('Confirmed quantity (GMEIN)')
            if ident(h.get('Material Number'))!=material or not ident(h.get('Batch')) or not end or end>ref or not number(hq) or hq<=0 or not number(hc) or hc<=0:continue
            # Same SKU preserves product size. Use completed, QC-released batches.
            fg=released_qty.get((material,ident(h.get('Batch'))))
            if not number(fg) or fg<=0:continue
            history.append((end,hq,fg,ident(h.get('Batch'))))
        # Deduplicate repeated order rows before deriving a historical yield.
        history=list({(h[3],h[1],h[2]):h for h in history}.values())
        comparable=[h for h in history if number(qty) and qty>0 and .75*qty<=h[1]<=1.25*qty]
        used=sorted(comparable or history,reverse=True)[:10]
        expected=round(qty*median(h[2]/h[1] for h in used),2) if used and number(qty) else None
        reason=(str(len(used))+' batches · 321 FG quantity / order quantity · same material / product size · '+('order quantity ±25%' if comparable else 'all order sizes; no close-size lots')) if used else 'Insufficient QC-released history for this material'
        finish=day(r.get('Basic finish date'))
        row=[r.get('Order'),types.get(material) or ('ZSFG' if r.get('MRP controller')=='SFG' else 'ZFGS' if r.get('MRP controller')=='ZFG' else None),material,r.get('Material description'),r.get('Batch'),qty,start.isoformat(),finish.isoformat() if finish else None,expected,reason,None,None]
        ongoing.append({'id':order_key(r),'row':row,'revision':0})
    ongoing.sort(key=lambda r:(r['row'][6],str(r['row'][0])),reverse=True);qc.sort(key=lambda r:(r[5],str(r[0])),reverse=True)
    return {'version':current['version'],'referenceDate':ref.isoformat(),'referenceBasis':basis,'qc':{'headers':QC_HEADERS,'rows':qc},'ongoing':ongoing,'ongoingHeaders':ONGOING_HEADERS,'upcomingHeaders':PLAN_HEADERS}


def schema(store,db):
    from .production_history import schema as history_schema
    history_schema(store,db)
    store.run(db,"""CREATE TABLE IF NOT EXISTS production_shared (
        kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,revision INTEGER NOT NULL,
        updated_by TEXT NOT NULL,updated_at DOUBLE PRECISION NOT NULL,PRIMARY KEY(kind,id))""")

def shared(store,actor):
    with store.transaction() as db:
        store.require(db,actor);schema(store,db)
        return [dict(r) for r in store.run(db,'SELECT * FROM production_shared ORDER BY updated_at DESC').fetchall()]



def read(store,actor):
    require_menu(store,actor,3);current=store.get_dataset(actor)
    if not current:raise ValueError('Upload a workbook first.')
    # Upcoming plans remain available even when an old upload lacks source tables.
    try:result=build(current)
    except ValueError as exc:result={'version':current['version'],'error':str(exc),'ongoing':[],'qc':{'headers':QC_HEADERS,'rows':[]},'ongoingHeaders':ONGOING_HEADERS,'upcomingHeaders':PLAN_HEADERS}
    from workbook import segment_map
    mapping=segment_map(current['data'].get('tables',[]))
    result['segmentMap']={k:sorted(v) for k,v in mapping.items()}
    from .production_materials import catalogue,resolve
    result['materials']=catalogue(current['data'])
    result['segments']=sorted({s for values in mapping.values() for s in values})
    # Resolve a manually typed product name using exact source descriptions.
    product_segments={}
    for table in current['data'].get('tables',[]):
        headers=table['headers']
        code=next((h for h in ('Material','Material Number','Material Code') if h in headers),None)
        desc=next((h for h in ('Material(text)','Material description','Material Description','Material Name') if h in headers),None)
        if code and desc:
            for row in table['rows']:
                product_segments.setdefault(str(row[headers.index(desc)] or '').strip().casefold(),set()).update(mapping.get(ident(row[headers.index(code)]),set()))
    saved=shared(store,actor);overrides={r['id']:r for r in saved if r['kind']=='ongoing'}
    for item in result['ongoing']:
        old=overrides.get(item['id'])
        if old:
            value=json.loads(old['payload']);item['row'][7:9]=[value['endDate'],value['quantity']];item['row'][9]='Saved planning override';item['row'][10:]=[old['updated_by'],timestamp(old['updated_at'])];item['revision']=old['revision']
    from .production_materials import records as source_records
    production_pairs={(ident(r.get('Material Number')).casefold(),ident(r.get('Batch')).casefold()) for r in source_records(current['data'],'Production Order Details') if ident(r.get('Material Number')) and ident(r.get('Batch'))}
    result['upcoming']=[{'id':r['id'],'revision':r['revision'],'row':[*(json.loads(r['payload'])[k] for k in ('product','description','batch','quantity','startDate','endDate')),r['updated_by'],timestamp(r['updated_at'])]} for r in saved if r['kind']=='upcoming' and not str(json.loads(r['payload']).get('batch','')).strip()[:1].isdigit()]
    for item in result['upcoming']:
        saved_row=next(r for r in saved if r['id']==item['id'] and r['kind']=='upcoming')
        payload=json.loads(saved_row['payload']);chosen=payload.get('segment','')
        material=resolve(current['data'],payload)
        item['materialCode']=material['code'] if material else ident(payload.get('materialCode')) or None
        inferred=mapping.get(str(item['row'][0]).strip(),set()) or product_segments.get(str(item['row'][0]).strip().casefold(),set())
        item['segments']=[chosen] if chosen else sorted(inferred)
        item['row'].append(', '.join(item['segments']) or 'Unassigned')
    matched=[item for item in result['upcoming'] if item.get('materialCode') and (ident(item['materialCode']).casefold(),ident(item['row'][2]).casefold()) in production_pairs]
    if matched:
        # Archive automatically once an order exists; retain history and avoid
        # resurrecting old plans when a later SAP dump omits older orders.
        with store.transaction() as db:
            store.require(db,actor)
            for item in matched:
                cursor=store.run(db,"UPDATE production_shared SET kind='upcoming_started' WHERE kind='upcoming' AND id=? AND revision=?",(item['id'],item['revision']))
                if cursor.rowcount:
                    before=json.loads(next(r['payload'] for r in saved if r['kind']=='upcoming' and r['id']==item['id']))
                    history_record(store,db,item['id'],'upcoming','Matched production order','System',{**before,'status':'Upcoming'},{**before,'status':'Production order exists'})
                    store._log(db,actor.username,'production_plan_matched','Upcoming plan matched a production order',actor.session_id)
    matched_ids={item['id'] for item in matched}
    result['upcoming']=[item for item in result['upcoming'] if item['id'] not in matched_ids]
    return result


def save(store,actor,event):
    require_menu(store,actor,3);kind=event.get('kind');permission='edit_production' if kind=='ongoing' else 'edit_upcoming'
    if kind not in ('ongoing','upcoming'):raise ValueError('Invalid production edit.')
    store.require_permission(actor,permission)
    current=store.get_dataset(actor)
    if not current or event.get('version')!=current['version']:raise ValueError('The workbook changed. Refresh Production before saving.')
    value=event.get('value',{});qty=value.get('quantity');end=day(value.get('endDate'))
    if not number(qty) or qty<0 or qty>1e12 or not end:raise ValueError('Enter a valid non-negative quantity and end date.')
    key=event.get('plan_id');expected=event.get('revision',0)
    if type(expected) is not int or expected<0:raise ValueError('Invalid saved revision.')
    if kind=='ongoing':
        item=next((r for r in build(current)['ongoing'] if r['id']==key),None)
        if not item:raise ValueError('This order is no longer in the ongoing production view.')
        if end<day(item['row'][6]):raise ValueError('Expected end date cannot precede the basic start date.')
        payload={'quantity':qty,'endDate':end.isoformat()}
    else:
        def text(field,required=True):
            v=value.get(field,'')
            if not isinstance(v,str) or len(v)>500 or required and not v.strip():raise ValueError('Enter product name, description and batch (maximum 500 characters).')
            return v.strip()
        start=day(value.get('startDate'))
        if not start or start>end or qty<=0:raise ValueError('Enter a positive quantity and start date on or before the end date.')
        payload={k:text(k) for k in ('product','description','batch')}
        code=value.get('materialCode')
        if code:
            from .production_materials import resolve
            material=resolve(current['data'],{'materialCode':code})
            if not material:raise ValueError('Select an FG/SFG material from the current workbook.')
            payload.update(materialCode=material['code'],product=material['code'],description=material['description'])
        if payload['batch'][0].isdigit():raise ValueError('Batch must not start with a numeric character.')
        chosen=value.get('segment','')
        from workbook import segment_map
        valid_segments={s for values in segment_map(current['data'].get('tables',[])).values() for s in values}
        if not isinstance(chosen,str) or chosen and chosen not in valid_segments:raise ValueError('Choose a segment from the current workbook.')
        payload['segment']=chosen
        payload.update(quantity=qty,startDate=start.isoformat(),endDate=end.isoformat())
        if key in (None,'') and expected==0:key=uuid.uuid4().hex
        if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{32}',key):raise ValueError('Invalid plan ID.')
    with store.transaction() as db:
        store.require(db,actor,permission=permission);store.require(db,actor,permission='menu_3');schema(store,db)
        dataset=store.run(db,"SELECT version FROM datasets WHERE id='current'").fetchone()
        if not dataset or dataset['version']!=current['version']:raise ValueError('The workbook changed. Refresh Production.')
        old=store.run(db,'SELECT payload FROM production_shared WHERE kind=? AND id=?',(kind,key)).fetchone()
        before=json.loads(old['payload']) if old else {'quantity':item['row'][8],'endDate':item['row'][7]} if kind=='ongoing' else {}
        now=time.time()
        if expected==0:
            cursor=store.run(db,'INSERT INTO production_shared(kind,id,payload,revision,updated_by,updated_at) VALUES(?,?,?,1,?,?) ON CONFLICT(kind,id) DO NOTHING',(kind,key,json.dumps(payload),actor.username,now))
        else:
            cursor=store.run(db,'UPDATE production_shared SET payload=?,revision=revision+1,updated_by=?,updated_at=? WHERE kind=? AND id=? AND revision=?',(json.dumps(payload),actor.username,now,kind,key,expected))
        if cursor.rowcount!=1:raise ValueError('Someone else changed this row. Refresh Production before saving again.')
        context={'materialCode':item['row'][2],'batch':item['row'][4]} if kind=='ongoing' else {}
        history_record(store,db,key,kind,'Created' if expected==0 and kind=='upcoming' else 'Edited',actor.username,{**before,**context},{**payload,**context})
        store._log(db,actor.username,'production_plan_saved',kind,actor.session_id)
    return read(store,actor)


def selection(store,actor,event):
    report=read(store,actor)
    if event.get('version')!=report['version']:raise ValueError('The workbook changed. Refresh Production and reopen the value.')
    chosen=event.get('selection',{});kind=chosen.get('kind');row=chosen.get('row')
    if kind=='qc':
        if row not in report['qc']['rows']:raise ValueError('This QC row changed. Refresh Production.')
        return row[0],report['qc']['headers']
    if kind not in ('ongoing','upcoming'):raise ValueError('Invalid production selection.')
    item=next((r for r in report[kind] if r['id']==chosen.get('id')),None)
    if not item or item['row']!=row:raise ValueError('This production row changed. Refresh Production.')
    code=item['row'][2] if kind=='ongoing' else item.get('materialCode')
    if not code:raise ValueError('Edit this legacy plan and select its FG/SFG material before checking source records.')
    return code,report['ongoingHeaders'] if kind=='ongoing' else report['upcomingHeaders']


def check_availability(store,actor,event):
    from .production_materials import availability
    report=read(store,actor)
    if event.get('version')!=report['version']:raise ValueError('The workbook changed. Refresh Production.')
    item=next((r for r in report['upcoming'] if r['id']==event.get('plan_id')),None)
    if not item or item['revision']!=event.get('revision'):raise ValueError('This plan changed. Refresh Production.')
    if not item.get('materialCode'):raise ValueError('Edit this legacy plan and select its FG/SFG material first.')
    current=store.get_dataset(actor)
    if current['version']!=report['version']:raise ValueError('The workbook changed. Refresh Production.')
    result=availability(current['data'],item['materialCode'],item['row'][3])
    require_menu(store,actor,3)
    with store.transaction() as db:
        store.require(db,actor)
        latest=store.run(db,"SELECT version FROM datasets WHERE id='current'").fetchone()
        plan=store.run(db,"SELECT revision FROM production_shared WHERE kind='upcoming' AND id=?",(item['id'],)).fetchone()
        if not latest or latest['version']!=report['version'] or not plan or plan['revision']!=item['revision']:
            raise ValueError('The workbook or plan changed. Refresh Production and check again.')
    return {**result,'version':report['version'],'id':item['id'],'revision':item['revision'],'materialCode':item['materialCode'],'quantity':item['row'][3]}


def delete(store,actor,event):
    require_menu(store,actor,3);store.require_permission(actor,'edit_upcoming')
    key=event.get('plan_id');revision=event.get('revision')
    if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{32}',key) or type(revision) is not int or revision<1:raise ValueError('Invalid saved plan selection.')
    with store.transaction() as db:
        store.require(db,actor,permission='edit_upcoming');store.require(db,actor,permission='menu_3');schema(store,db)
        current=store.run(db,"SELECT version FROM datasets WHERE id='current'").fetchone()
        if not current or current['version']!=event.get('version'):raise ValueError('The workbook changed. Refresh Production before deleting.')
        row=store.run(db,"SELECT payload FROM production_shared WHERE kind='upcoming' AND id=? AND revision=?",(key,revision)).fetchone()
        if not row:raise ValueError('This plan changed or was removed. Refresh Production.')
        # Soft-delete keeps history available to every authorised viewer.
        cursor=store.run(db,"UPDATE production_shared SET kind='upcoming_deleted',revision=revision+1,updated_by=?,updated_at=? WHERE kind='upcoming' AND id=? AND revision=?",(actor.username,time.time(),key,revision))
        if cursor.rowcount!=1:raise ValueError('Someone else changed this plan. Refresh Production.')
        history_record(store,db,key,'upcoming','Deleted',actor.username,json.loads(row['payload']),{})
        store._log(db,actor.username,'production_plan_deleted','Upcoming plan',actor.session_id)
    return read(store,actor)
