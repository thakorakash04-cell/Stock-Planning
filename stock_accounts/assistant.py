"""Authenticated Ask AI bridge; all context is checked against the current workbook."""
import base64,hashlib,io,secrets
import pandas as pd
import streamlit as st
from grounded_ai import ask,tables_from_frames,json_text,execute_query
from .store import AccessDenied
from workbook import forecast_summary

def stock_tables(store,actor):
    from .workspace import workspace_payload
    data,model_tables,version=workspace_payload(store,actor)
    cached=st.session_state.get('_stock_ai_tables')
    if not cached or cached[0]!=version:
        frames=[(s['name'],pd.DataFrame(s['rows'],columns=s['headers'])) for s in data['sheets']]
        if len(data['sheets'])>4:
            sheet=data['sheets'][4]
            if sheet['rows'] and len(sheet['headers'])>=7:
                frames.append((sheet['name']+' — product totals',forecast_summary(pd.DataFrame(sheet['rows'],columns=sheet['headers']))))
        frames.extend((t['name'],pd.DataFrame(t['rows'],columns=t['headers'])) for t in model_tables)
        cached=(version,tables_from_frames(frames));st.session_state['_stock_ai_tables']=cached
    return cached[1],version,data['filename']

def export_evidence(store,actor,event,tables,version):
    if store.identity(actor)['role']!='admin':raise AccessDenied('Only administrators can download Ask AI tables.')
    store.require_permission(actor,'download')
    entry=st.session_state.get('_stock_ai_exports',{}).get(str(event.get('export_id','')))
    if not entry:raise ValueError('This download has expired. Ask the question again to generate a new table.')
    if entry['version']!=version or event.get('version')!=version:raise ValueError('The workbook changed. Ask the question again before downloading.')
    query=entry['query'];table=next((t for t in tables if t['id']==query['table']),None)
    if table is None:raise ValueError('The source table is no longer available. Ask the question again.')
    result=execute_query(tables,query,all_rows=True)
    raw_query={'table':query['table'],'filters':query.get('filters',[]),'limit':20}
    if query.get('sort_by') in table['headers']:
        raw_query.update(sort_by=query['sort_by'],descending=query.get('descending',True))
    matching=execute_query(tables,raw_query,all_rows=True)
    cells=sum(sum(len(r) for r in rows) for rows in (result['records'],matching['records']))
    if cells>2_000_000:raise ValueError('This export is too large. Narrow the question filters and download the smaller matching table.')
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    workbook=Workbook(write_only=True)
    def write_sheet(name,records):
        sheet=workbook.create_sheet(name)
        headers=list(records[0]) if records else []
        def cell(value):
            if isinstance(value,str):
                if len(value)>32767:raise ValueError('A text field exceeds Excel’s cell limit. Narrow the exported columns or filters.')
                item=WriteOnlyCell(sheet,value=value);item.data_type='s';return item
            return value
        sheet.append([cell(h) for h in headers])
        for record in records:sheet.append([cell(record.get(h)) for h in headers])
    write_sheet('Result table',result['records'])
    write_sheet('Matching records',matching['records'])
    write_sheet('Query details',[{'Source table':table['name'],'Matched records':matching['matched_records'],'Result rows':result['result_rows'],'Workbook version':version,'Query':json_text(query)}])
    output=io.BytesIO();workbook.save(output)
    if output.tell()>25_000_000:raise ValueError('The Excel export exceeds 25 MB. Narrow your question filters.')
    if store.identity(actor)['role']!='admin':raise AccessDenied('Administrator access is no longer active.')
    store.require_permission(actor,'download')
    store.log_event(actor,'export','Ask AI matching records')
    return {'content':base64.b64encode(output.getvalue()).decode(),'filename':'Ask_AI_matching_records.xlsx','mime':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','matched_records':matching['matched_records']}

def handle_ai(store,actor,event):
    store.require_permission(actor,'use_tools')
    tables,version,filename=stock_tables(store,actor)
    if event.get('action')=='ai_export':return export_evidence(store,actor,event,tables,version)
    if event.get('action')=='ai_status':
        from grounded_ai import settings
        key,model=settings()
        return {'configured':bool(key),'model':model,'version':version,'tables':len(tables),'filename':filename}
    if event.get('action')=='ai_clear':
        thread=hashlib.sha256(json_text([version,event.get('context')]).encode()).hexdigest()
        st.session_state.setdefault('_stock_ai_threads',{}).pop(thread,None)
        return {'ok':True}
    if event.get('consent') is not True:raise ValueError('Enable sharing the question and relevant loaded records with Google Gemini first.')
    if event.get('version')!=version:raise ValueError('The workbook changed. Refresh this chat and ask again using the current data.')
    context=event.get('context')
    thread=hashlib.sha256(json_text([version,context]).encode()).hexdigest()
    threads=st.session_state.setdefault('_stock_ai_threads',{})
    history=threads.get(thread,[])
    question=event.get('question')
    result=ask(tables,question,history,context,scope='Stock Planning: '+filename+'. Saved workbook snapshot; mixed units and repeated monthly stock must not be summed. No cross-table joins or production feasibility calculation.')
    # Recheck revocation before returning the provider result.
    store.require_permission(actor,'use_tools')
    threads[thread]=(history+[{'role':'user','text':question},{'role':'assistant','text':result['answer']}])[-12:]
    while len(threads)>10:threads.pop(next(iter(threads)))
    store.log_event(actor,'tool_use','Ask AI')
    if store.identity(actor)['role']=='admin':
        exports=st.session_state.setdefault('_stock_ai_exports',{})
        for item in result.get('evidence',[]):
            token=secrets.token_urlsafe(18)
            exports[token]={'version':version,'query':item['query']}
            item['export_id']=token
        while len(exports)>30:exports.pop(next(iter(exports)))
    return {**result,'version':version}
