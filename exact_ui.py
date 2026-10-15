"""Serve the original React interface through Streamlit's authenticated session."""
from __future__ import annotations
import base64
from datetime import datetime,timezone
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from storage import AccessDenied
from workbook import read_upload,SPECS,segment_map

_component=components.declare_component("stock_planning_web_ui",path=str(Path(__file__).parent/"frontend_dist"))

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
        return {"logout":True}
    if identity["role"]!="admin":
        raise AccessDenied("Administrator access required.")
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
    if action=="upload":
        content=event.get("content","")
        if not isinstance(content,str) or len(content)>34_000_000:
            raise ValueError("Choose a workbook under 25 MB.")
        raw=base64.b64decode(content,validate=True)
        filename=str(event.get("filename","workbook.xlsx"))[:255]
        dataset=read_upload(raw,filename)
        store.save_dataset(actor,filename,dataset)
        return {"ok":True}
    raise ValueError("Unknown operation.")

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
    iframe[title="exact_ui.stock_planning_web_ui"]{width:100%;border:0}
    </style>""",unsafe_allow_html=True)
    # Read the existing widget value before rendering. A component event already
    # reruns Streamlit; handling it here returns the response in that same run.
    event=st.session_state.get("exact_website_ui")
    if isinstance(event,dict) and isinstance(event.get("id"),str) and event["id"]!=st.session_state.get("_ui_last_request"):
        st.session_state._ui_last_request=event["id"]
        try:
            result=handle_request(store,actor,event)
            if result.get("logout"):
                st.session_state.clear();st.rerun()
            st.session_state._ui_response={"id":event["id"],"body":result}
        except (ValueError,AccessDenied) as exc:
            st.session_state._ui_response={"id":event["id"],"body":None,"error":str(exc)}
        except Exception:
            st.session_state._ui_response={"id":event["id"],"body":None,"error":"The request failed. Check the workbook or database connection; your previous data is unchanged."}
    current=store.get_dataset(actor)
    data,tables,version=ui_payload(current)
    # Stable arguments also let a newly mounted iframe recover without issuing
    # refresh requests. The browser applies data only when its version changes.
    _component(data=data,tables=tables,version=version,user=identity["username"],role=identity["role"],response=st.session_state.get("_ui_response"),default=None,key="exact_website_ui")
