"""Authenticated Ask AI bridge; all context is checked against the current workbook."""
import hashlib
import pandas as pd
import streamlit as st
from grounded_ai import ask,tables_from_frames,json_text
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

def handle_ai(store,actor,event):
    store.require_permission(actor,'use_tools')
    tables,version,filename=stock_tables(store,actor)
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
    return {**result,'version':version}
