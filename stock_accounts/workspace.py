"""Serve the original React interface through Streamlit's authenticated session."""
from __future__ import annotations
import base64
from datetime import datetime,timezone
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from .store import AccessDenied
from workbook import read_upload,SPECS,segment_map

_component=components.declare_component("stock_planning_web_ui",path=str(Path(__file__).resolve().parents[1]/"frontend_dist"))

def ui_payload(current):
    if current:
        dataset=current["data"]
        mapping=segment_map(dataset.get("tables",[]))
        return {"filename":current["filename"],"updatedAt":datetime.fromtimestamp(current["updated_at"],tz=timezone.utc).isoformat(),"asOf":"Saved Excel results","sheets":dataset["sheets"],"segmentMap":{k:sorted(v) for k,v in mapping.items()}},dataset.get("tables",[]),current["version"]
    return {"filename":"No workbook uploaded yet","updatedAt":None,"asOf":"—","sheets":[{"name":s[0],"headers":["Material","Description"],"rows":[]} for s in SPECS],"segmentMap":{}},[],"empty"

def handle_request(store,actor,event):
    """Never trust frontend visibility or a client-supplied role."""
    identity=store.identity(actor)
    action=event.get("action")
    if action in ("heartbeat","refresh","ack"):
        return {"ok":True}
    if action=="logout":
        store.log_event(actor,"logout")
        return {"logout":True}
    if action=="open_password":return {"route":"password"}
    if action=="view":
        index=event.get("tab")
        if type(index) is not int or not 0<=index<len(SPECS):raise ValueError("Unknown view.")
        store.record_access(actor,SPECS[index][0]);return {"ok":True}
    if action=="export":
        store.log_event(actor,"export","Table export");return {"ok":True}
    if action=="upload":
        store.require_permission(actor,"update_data")
        content=event.get("content","")
        if not isinstance(content,str) or len(content)>34_000_000:raise ValueError("Choose a workbook under 25 MB.")
        raw=base64.b64decode(content,validate=True)
        dataset=read_upload(raw,str(event.get("filename","workbook.xlsx"))[:255])
        store.save_dataset(actor,str(event.get("filename","workbook.xlsx"))[:255],dataset)
        return {"ok":True}
    if identity["role"]!="admin":raise AccessDenied("Administrator access required.")
    if action=="open_admin":return {"route":"admin"}
    if action=="list_users":
        return {"users":store.users(actor)}
    if action=="create_viewer":
        store.create_viewer(actor,str(event.get("username","")),str(event.get("password","")))
        return {"ok":True}
    if action=="update_viewer":
        username=str(event.get("username",""));operation=event.get("operation")
        if operation=="reset":store.update_viewer(actor,username,password=str(event.get("password","")))
        elif operation in ("disable","enable"):store.update_viewer(actor,username,active=operation=="enable")
        else:raise ValueError("Unknown account operation.")
        return {"ok":True}
    raise ValueError("Unknown operation.")

def process_account_navigation(store,actor):
    event=st.session_state.get("exact_website_ui")
    if not isinstance(event,dict) or event.get('action') not in ('open_admin','open_password'):return
    if not isinstance(event.get('id'),str) or event['id']==st.session_state.get('_ui_last_request'):return
    st.session_state._ui_last_request=event['id']
    try:
        result=handle_request(store,actor,event)
        st.session_state._account_page=result['route']
        st.session_state._ui_response={'id':event['id'],'body':result}
    except AccessDenied as exc:
        st.session_state._ui_response={'id':event['id'],'body':None,'error':str(exc)}

def account_page_style():
    st.markdown("""<style>
    .stMain{height:auto!important;min-height:100dvh;overflow:auto!important}
    .stMainBlockContainer,.block-container{max-width:1500px!important;margin:0 auto!important;padding:2rem!important}
    div[data-testid='stVerticalBlock']{gap:1rem!important}
    header[data-testid='stHeader']{display:block!important}
    </style>""",unsafe_allow_html=True)

def render_exact_workspace(store,actor,identity):
    # Login remains Streamlit-native; after sign-in there is only one sidebar:
    # the original website's sidebar inside the full-width component.
    st.markdown("""<style>
    header[data-testid="stHeader"],section[data-testid="stSidebar"],div[data-testid="stToolbar"],#MainMenu,footer{display:none!important}
    .stAppViewContainer,.stMain,.block-container{padding:0!important;margin:0!important;max-width:none!important}
    .stMainBlockContainer{padding:0!important;max-width:none!important}
    .stMain{height:100dvh;overflow:hidden!important}
    div[data-testid="stElementContainer"]:has(iframe){line-height:0}
    div[data-testid="stVerticalBlock"]{gap:0!important}
    div[data-testid="stElementContainer"]:has(iframe){width:100%!important}
    iframe[title$="stock_planning_web_ui"]{width:100%;border:0}
    </style>""",unsafe_allow_html=True)
    # Read the existing widget value before rendering. A component event already
    # reruns Streamlit; handling it here returns the response in that same run.
    event=st.session_state.get("exact_website_ui")
    if isinstance(event,dict) and isinstance(event.get("id"),str) and event["id"]!=st.session_state.get("_ui_last_request"):
        st.session_state._ui_last_request=event["id"]
        try:
            result=handle_request(store,actor,event)
            if result.get("route"):
                st.session_state._account_page=result["route"];st.rerun()
            if result.get("logout"):
                st.session_state.clear();st.rerun()
            st.session_state._ui_response={"id":event["id"],"body":result}
        except (ValueError,AccessDenied) as exc:
            st.session_state._ui_response={"id":event["id"],"body":None,"error":str(exc)}
        except Exception:
            st.session_state._ui_response={"id":event["id"],"body":None,"error":"The request failed. Check the workbook or database connection; your previous data is unchanged."}
    store.record_access(actor,"Workspace")
    current=store.get_dataset(actor)
    data,tables,version=ui_payload(current)
    # Stable arguments also let a newly mounted iframe recover without issuing
    # refresh requests. The browser applies data only when its version changes.
    _component(data=data,tables=tables,version=version,user=identity["username"],role=identity["role"],permissions=identity["permissions"],response=st.session_state.get("_ui_response"),default=None,key="exact_website_ui")
