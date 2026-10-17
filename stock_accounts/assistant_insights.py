"""Authenticated Ask AI bridge; all context is checked against the current workbook."""
import base64,hashlib,io,secrets
import pandas as pd
import streamlit as st
from grounded_ai import ask,tables_from_frames,json_text,execute_query
from .store import AccessDenied
from workbook import forecast_summary

def stock_tables(store,actor):
    from .workspace_insights import workspace_payload
    data,model_tables,version=workspace_payload(store,actor)
    from .planning_assistant import knowledge
    cache_key=(version,str(data.get('planningRevision')),knowledge()['revision'],str(store.identity(actor)['permissions']))
    cached=st.session_state.get('_stock_ai_tables')
    if not cached or cached[0]!=cache_key:
        frames=[(s['name'],pd.DataFrame(s['rows'],columns=s['headers'])) for s in data['sheets']]
        if len(data['sheets'])>4:
            sheet=data['sheets'][4]
            if sheet['rows'] and len(sheet['headers'])>=7:
                frames.append((sheet['name']+' — product totals',forecast_summary(pd.DataFrame(sheet['rows'],columns=sheet['headers']))))
        frames.extend((t['name'],pd.DataFrame(t['rows'],columns=t['headers'])) for t in model_tables)
        cached=(cache_key,tables_from_frames(frames));st.session_state['_stock_ai_tables']=cached
    return cached[1],version,data['filename']

def export_evidence(store,actor,event,tables,version):
    if store.identity(actor)['role']!='admin':raise AccessDenied('Only administrators can download Ask AI tables.')
    store.require_permission(actor,'download')
    entry=st.session_state.get('_stock_ai_exports',{}).get(str(event.get('export_id','')))
    if not entry:raise ValueError('This download has expired. Ask the question again to generate a new table.')
    if entry['version']!=version or event.get('version')!=version:raise ValueError('The workbook changed. Ask the question again before downloading.')
    if 'table' in entry:
        from .matched_export import export_table
        current=store.get_dataset(actor)
        table=entry['table'];projection={**event,'headers':event.get('headers',table['headers']),'rows':event.get('rows',table['rows'])}
        return export_table(store,actor,projection,current,table,'Planning assistant results','Planning_assistant_result.xlsx')
    if entry.get('source_table'):tables=[t for t in tables if t['id']!=entry['source_table']['id']]+[entry['source_table']]
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
    def write_sheet(name,records,selected_headers=None):
        sheet=workbook.create_sheet(name)
        headers=selected_headers if selected_headers is not None else list(records[0]) if records else []
        def cell(value):
            if isinstance(value,str):
                if len(value)>32767:raise ValueError('A text field exceeds Excel’s cell limit. Narrow the exported columns or filters.')
                item=WriteOnlyCell(sheet,value=value);item.data_type='s';return item
            return value
        sheet.append([cell(h) for h in headers])
        for record in records:sheet.append([cell(record.get(h)) for h in headers])
    from .ai_table_view import project
    displayed=project(result['records'],event)
    write_sheet('Result table',displayed,event.get('headers'))
    if 'headers' not in event:write_sheet('Matching records',matching['records'])
    write_sheet('Query details',[{'Source table':table['name'],'Matched records':matching['matched_records'],'Result rows':result['result_rows'],'Workbook version':version,'Query':json_text(query)}])
    output=io.BytesIO();workbook.save(output)
    if output.tell()>25_000_000:raise ValueError('The Excel export exceeds 25 MB. Narrow your question filters.')
    if store.identity(actor)['role']!='admin':raise AccessDenied('Administrator access is no longer active.')
    store.require_permission(actor,'download')
    store.log_event(actor,'export','Ask AI matching records')
    return {'content':base64.b64encode(output.getvalue()).decode(),'filename':'Ask_AI_matching_records.xlsx','mime':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','matched_records':matching['matched_records']}

def insight_records(store,actor,event,tables,version):
    entry=st.session_state.get('_stock_insight_sources',{}).get(str(event.get('source_id','')))
    if not entry:raise ValueError('This chart has expired. Generate insights again.')
    if entry['version']!=version or event.get('version')!=version:raise ValueError('The workbook changed. Generate insights again.')
    page=event.get('page',0)
    if type(page) is not int or not 0<=page<=10000:raise ValueError('Invalid source table page.')
    if entry.get('source_table'):tables=[t for t in tables if t['id']!=entry['source_table']['id']]+[entry['source_table']]
    query=entry['query']
    raw={'table':query['table'],'filters':query.get('filters',[]),'limit':20}
    table=next(t for t in tables if t['id']==query['table'])
    if query.get('sort_by') in table['headers']:raw.update(sort_by=query['sort_by'],descending=query.get('descending',True))
    result=execute_query(tables,raw,all_rows=True)
    records=result['records'][page*50:(page+1)*50]
    records=[{k:(v[:2000]+'…' if isinstance(v,str) and len(v)>2000 else v) for k,v in r.items()} for r in records]
    store.require_permission(actor,'use_tools')
    return {'records':records,'total':result['result_rows'],'page':page,'page_size':50,'table':table['name']}

def handle_ai(store,actor,event):
    store.require_permission(actor,'use_tools')
    tables,version,filename=stock_tables(store,actor)
    if event.get('action')=='insight_records':return insight_records(store,actor,event,tables,version)
    if event.get('action')=='ai_export':return export_evidence(store,actor,event,tables,version)
    if event.get('action')=='ai_status':
        from grounded_ai import settings
        key,model=settings()
        from .planning_assistant import knowledge
        return {'configured':bool(key),'model':model,'version':version,'tables':len(tables),'filename':filename,'knowledge_revision':knowledge()['revision'],'planning_revision':str(data_revision(store,actor)),'report_scope':report_scope(store,actor)}
    if event.get('action')=='ai_clear':
        thread=hashlib.sha256(json_text([version,event.get('context')]).encode()).hexdigest()
        st.session_state.setdefault('_stock_ai_threads',{}).pop(thread,None)
        st.session_state.setdefault('_planning_scenarios',{}).pop(thread,None)
        return {'ok':True}
    if event.get('consent') is not True:raise ValueError('Enable sharing the question and relevant loaded records with Google Gemini first.')
    if event.get('version')!=version:raise ValueError('The workbook changed. Refresh this chat and ask again using the current data.')
    if event.get('action')=='add_insight_chart':
        from .custom_insight import handle
        return handle(store,actor,event,tables,version)
    if event.get('action')=='generate_insights':
        from .insights import build_report,report_views
        from .workspace_insights import workspace_payload
        data,_,_=workspace_payload(store,actor)
        from .insight_attention import prepare
        current=store.get_dataset(actor)
        production_revision=str(data_revision(store,actor))
        report_tables,views,planning_context=prepare(store,actor,tables,report_views(data),current,data)
        result=build_report(report_tables,views,planning_context)
        store.require_permission(actor,'use_tools')
        if stock_tables(store,actor)[1]!=version:raise ValueError('The workbook changed. Generate the report again.')
        if str(data_revision(store,actor))!=production_revision:raise ValueError('Production plans changed while analysing. Generate the report again.')
        sources=st.session_state.setdefault('_stock_insight_sources',{})
        for section in result['sections']:
            for chart in section['charts']:
                token=secrets.token_urlsafe(18)
                sources[token]={'version':version,'query':chart['evidence']['query'],'source_table':next((t for t in report_tables if t['id']==chart['evidence']['query']['table']),None)}
                chart['evidence']['source_id']=token
        while len(sources)>100:sources.pop(next(iter(sources)))
        if store.identity(actor)['role']=='admin':
            exports=st.session_state.setdefault('_stock_ai_exports',{})
            for section in result['sections']:
                for chart in section['charts']:
                    token=secrets.token_urlsafe(18)
                    exports[token]={'version':version,'query':chart['evidence']['query'],'source_table':next((t for t in report_tables if t['id']==chart['evidence']['query']['table']),None)}
                    chart['evidence']['export_id']=token
            while len(exports)>100:exports.pop(next(iter(exports)))
        store.log_event(actor,'tool_use','Insights & Graphs')
        report_id=secrets.token_urlsafe(18)
        reports=st.session_state.setdefault('_stock_custom_reports',{})
        reports[report_id]={'version':version,'planning_revision':production_revision,'scope':report_scope(store,actor),'knowledge_revision':result.get('knowledge_revision',planning_context['knowledge']['revision']),
                            'charts':{s['view']:[{'title':c['title'],'query':c['evidence']['query']} for c in s['charts']] for s in result['sections']}}
        while len(reports)>5:reports.pop(next(iter(reports)))
        return {**result,'version':version,'report_id':report_id,'planning_revision':production_revision,'report_scope':report_scope(store,actor)}
    context=event.get('context')
    thread=hashlib.sha256(json_text([version,context]).encode()).hexdigest()
    threads=st.session_state.setdefault('_stock_ai_threads',{})
    history=threads.get(thread,[])
    question=event.get('question')
    from .planning_assistant import reply
    scenarios=st.session_state.setdefault('_planning_scenarios',{})
    result=reply(store,actor,tables,question,history,context,scenarios.get(thread))
    scenarios[thread]=result.pop('scenario',scenarios.get(thread,{}))
    while len(scenarios)>10:scenarios.pop(next(iter(scenarios)))
    # Recheck revocation before returning the provider result.
    store.require_permission(actor,'use_tools')
    threads[thread]=(history+[{'role':'user','text':question},{'role':'assistant','text':result['answer']}])[-40:]
    while len(threads)>10:threads.pop(next(iter(threads)))
    store.log_event(actor,'tool_use','Ask AI')
    exports=st.session_state.setdefault('_stock_ai_exports',{})
    for item in result.get('evidence',[]):
        tool_table=item.pop('_table',None)
        if store.identity(actor)['role']=='admin':
            token=secrets.token_urlsafe(18)
            exports[token]={'version':version,'table':tool_table} if tool_table else {'version':version,'query':item['query']}
            item['export_id']=token
    while len(exports)>100:exports.pop(next(iter(exports)))
    return {**result,'version':version}

# Increment with analysis protocol changes to invalidate hot-deployment helpers.
INSIGHTS_REVISION=3

AI_EXPORT_REVISION=1

PLANNING_ASSISTANT_REVISION=1

INSIGHT_ATTENTION_REVISION=1

def data_revision(store,actor):
    from .production import shared
    return [(r['kind'],r['id'],r['revision'],r['updated_at']) for r in shared(store,actor)]

def report_scope(store,actor):
    return hashlib.sha256(json_text([actor.username,store.identity(actor)['permissions']]).encode()).hexdigest()[:16]

CUSTOM_INSIGHT_REVISION=1
