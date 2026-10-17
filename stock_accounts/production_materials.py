"""FG/SFG catalogue and auditable current-stock BOM checks."""
from decimal import Decimal,InvalidOperation

TYPES={'ZFGS','ZSFG','ZFG','FG','SFG'}

def records(dataset,name):
    t=next((t for t in dataset.get('tables',[]) if t['name']==name),None)
    return [dict(zip(t['headers'],r)) for r in t['rows']] if t else []

def catalogue(dataset):
    found={}
    def add(code,description,typ,unit=None):
        code=str(code or '').strip();typ=str(typ or '').upper()
        if not code or typ not in TYPES:return
        item=found.setdefault(code,{'code':code,'description':str(description or code),'type':typ,'unit':unit or ''})
        if item['description']==code and description:item['description']=str(description)
        if unit:item['unit']=unit
    for r in records(dataset,'Material Document List'):add(r.get('Material'),r.get('Material Description'),r.get('Material Type'),r.get('Base Unit of Measure'))
    for r in records(dataset,'Planning Quantity'):add(r.get('Material Code'),r.get('Material Name'),r.get('Material Type'),r.get('Unit'))
    for r in records(dataset,'Production Order Details'):add(r.get('Material Number'),r.get('Material description'),'ZSFG' if r.get('MRP controller')=='SFG' else 'ZFGS' if r.get('MRP controller')=='ZFG' else '',r.get('Unit of measure (=GMEIN)'))
    for r in records(dataset,'BOM'):
        code=str(r.get('Material') or '').strip()
        if code in found:add(code,r.get('Material(text)'),found[code]['type'],r.get('Base unit of measure'))
        add(r.get('Component'),r.get('Component(text)'),r.get('Material Type'),r.get('Component unit'))
    return sorted(found.values(),key=lambda x:x['code'])

def resolve(dataset,payload):
    items=catalogue(dataset);code=payload.get('materialCode')
    if code:return next((m for m in items if m['code']==code),None)
    text=str(payload.get('product') or '').strip().casefold()
    matches=[m for m in items if text in (m['code'].casefold(),m['description'].casefold())]
    return matches[0] if len(matches)==1 else None

def dec(value):
    if isinstance(value,bool) or value is None:return None
    try:
        v=Decimal(str(value))
        return v if v.is_finite() else None
    except (ValueError,InvalidOperation):return None

def availability(dataset,code,quantity):
    qty=dec(quantity)
    if qty is None or qty<=0:raise ValueError('Enter a positive planned quantity.')
    rows=[r for r in records(dataset,'BOM') if str(r.get('Material') or '').strip()==code and r.get('Component')]
    if not rows:raise ValueError('No BOM is available for this FG/SFG material. Availability cannot be confirmed.')
    alternatives={(r.get('Bill of material'),r.get('Alternative BOM')) for r in rows}
    if len(alternatives)>1:raise ValueError('Multiple BOM alternatives exist for this material. Availability needs a single selected BOM.')
    stocks={};units={};unknown_stock=set()
    for r in records(dataset,'Stock Data'):
        material=str(r.get('Material') or '').strip();v=dec(r.get('Current Stock'))
        if v is None:
            a,b=dec(r.get('Unrestricted')),dec(r.get('In Quality Insp.'))
            v=a+b if a is not None and b is not None else None
        if v is None:unknown_stock.add(material)
        else:stocks[material]=stocks.get(material,Decimal(0))+v
        if r.get('Base Unit of Measure'):units.setdefault(material,set()).add(r['Base Unit of Measure'])
    groups={};seen=set();detail=[];warnings=[]
    for index,r in enumerate(rows):
        component=str(r['Component']);rate=dec(r.get('Component quantity'));base=dec(r.get('Base quantity'))
        # Distinct BOM items consume independently; duplicate rows from joins do not.
        key=(r.get('Bill of material'),r.get('Alternative BOM'),r.get('Item Number'),component)
        if r.get('Item Number') is not None:
            if key in seen:continue
            seen.add(key)
        unit=r.get('Component unit') or ''
        amount=qty*rate/base if rate is not None and rate>=0 and base is not None and base>0 else None
        group=groups.setdefault((component,unit),{'name':r.get('Component(text)') or component,'required':Decimal(0),'valid':True,'merged':[]})
        if amount is None:group['valid']=False;warnings.append('Invalid or missing BOM consumption/base quantity for '+component)
        else:group['required']+=amount
        merged=dec(r.get('Sum of Stock Data.Current Stock'))
        if merged is not None:group['merged'].append(merged)
        detail.append([component,r.get('Item Number'),float(qty),float(base) if base is not None else None,float(rate) if rate is not None else None,float(amount) if amount is not None else None,unit])
    output=[];all_available=True
    for (component,unit),g in groups.items():
        stock=stocks.get(component)
        if stock is None and component not in unknown_stock and g['merged']:stock=min(g['merged'])
        known=g['valid'] and stock is not None and component not in unknown_stock and (not units.get(component) or units[component]=={unit})
        required=g['required'] if g['valid'] else None
        shortage=max(Decimal(0),required-stock) if known else None
        status='Available' if known and shortage==0 else 'Shortage' if known else 'Cannot verify'
        all_available=all_available and status=='Available'
        output.append([component,g['name'],unit,float(required) if required is not None else None,float(stock) if stock is not None else None,float(shortage) if shortage is not None else None,status])
    return {'available':all_available,'headers':['Component','Description','Unit','Required Quantity','Current Stock','Need to Order','Status'],'rows':output,
            'calculationHeaders':['Component','BOM Item','Planned FG/SFG Quantity','BOM Base Quantity','Component Consumption','Required Quantity','Unit'],'calculations':detail,
            'warnings':sorted(set(warnings)), 'explanation':'Required = planned quantity ÷ BOM base quantity × component consumption, summed per component and unit. Need to order = max(required − current stock, 0). Current stock includes unrestricted and quality-inspection stock. On-order stock is not counted. This checks one plan against the uploaded stock snapshot; it does not reserve stock across plans or recursively explode SFG BOMs.'}
