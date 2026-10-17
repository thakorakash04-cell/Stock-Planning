"""Narrow viewer export: rows from one validated value drill-down only."""
import base64,io,json
from openpyxl import Workbook
from workbook import related_tables


def export_matched(store,actor,event):
    current=store.get_dataset(actor)
    if not current or event.get('version')!=current['version']:
        raise ValueError('The workbook changed. Reopen the selected value before downloading.')
    if event.get('scope')!='related' or event.get('exportTables'):
        raise ValueError('Only the selected matched-records table can be downloaded.')
    data=current['data']
    if event.get('selection') is not None:
        from .production import selection
        code,headers=selection(store,actor,event)
        col=event.get('col')
        if type(col) is not int or not 0<=col<len(headers):raise ValueError('Select a production table value.')
    else:
        data=current['data'];tab=event.get('tab');row=event.get('row');col=event.get('col')
        sheets=data.get('sheets',[])
        if type(tab) is not int or not 0<=tab<len(sheets) or not isinstance(row,list):
            raise ValueError('Select a saved worksheet value before downloading matched records.')
        valid_rows=sheets[tab]['rows']
        if tab==4 and row not in valid_rows:
            # Match the browser's product-total rows, including blank FG stock.
            groups={}
            for r in valid_rows:
                if not r[0]:continue
                g=groups.setdefault(str(r[0]),[r[0],r[1],0,0,None])
                for target,source in [(2,4),(3,5)]:
                    if isinstance(r[source],(int,float)):g[target]+=r[source]
                if g[4] is None and isinstance(r[6],(int,float)):g[4]=r[6]
            valid_rows=[g+[g[2]-g[3]-(g[4] or 0)] for g in groups.values()]
        if row not in valid_rows:raise ValueError('Select a saved worksheet value before downloading matched records.')
        if type(col) is not int or not 0<=col<len(sheets[tab]['headers']):
            raise ValueError('Select a table value before downloading matched records.')
        code=row[3 if tab in (2,3) else 0]
    table=next((t for t in related_tables(data.get('tables',[]),code) if t['name']==event.get('table')),None)
    if table is None:raise ValueError('The selected source table is unavailable.')
    if table['name']=='Calendar':
        table={**table,'headers':table['headers']+['Relationship to selection'],
               'rows':[r+['Date in related source records'] for r in table['rows']]}
    return export_table(store,actor,event,current,table,'Value matched records: '+table['name'],'Matched_records.xlsx')


def export_table(store,actor,event,current,table,resource,filename):
    """Validate a grid projection against one server-selected, approved table."""
    headers=event.get('headers');rows=event.get('rows')
    if not isinstance(headers,list) or not headers or any(not isinstance(h,str) or h not in table['headers'] for h in headers) or len(set(headers))!=len(headers):
        raise ValueError('Invalid matched table columns.')
    if not isinstance(rows,list) or len(rows)*len(headers)>2_000_000 or len(json.dumps(rows))>25_000_000:
        raise ValueError('Narrow the matched table before downloading.')
    indices=[table['headers'].index(h) for h in headers]
    allowed={tuple(r[i] for i in indices) for r in table['rows']}
    for r in rows:
        if not isinstance(r,list) or len(r)!=len(headers) or any(v is not None and not isinstance(v,(str,int,float)) for v in r) or tuple(r) not in allowed:
            raise ValueError('The download must contain only records matching the selected value.')
    workbook=Workbook(write_only=True);sheet=workbook.create_sheet(filename.removesuffix('.xlsx').replace('_',' ')[:31])
    from openpyxl.cell import WriteOnlyCell
    def literal(v):
        if isinstance(v,str):
            c=WriteOnlyCell(sheet,value=v);c.data_type='s';return c
        return v
    sheet.append([literal(h) for h in headers])
    for r in rows:sheet.append([literal(v) for v in r])
    output=io.BytesIO();workbook.save(output)
    if output.tell()>25_000_000:raise ValueError('Narrow the matched table before downloading.')
    # This scoped export is independent of the broad download permission.
    # Recheck revocation before auditing or returning the generated file.
    with store.transaction() as db:
        store.require(db,actor)
        revision=store.run(db,"SELECT version FROM datasets WHERE id='current'").fetchone()
        if not revision or revision['version']!=current['version']:raise ValueError('The workbook changed. Reopen the selected value.')
        store._log(db,actor.username,'export',resource,actor.session_id)
    return {'content':base64.b64encode(output.getvalue()).decode(),'filename':filename,
            'mime':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}

TABLE_EXPORT_REVISION=2
