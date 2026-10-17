from __future__ import annotations
import os,time,logging,importlib
from datetime import datetime,timezone
import pandas as pd
import streamlit as st
from stock_accounts.store import Store,Actor,AccessDenied
# Update permission defaults even for Store objects cached before this deployment.
from stock_accounts import store as _account_module
from stock_accounts.access import PERMISSION_DEFAULTS
_account_module.DEFAULT_PERMISSIONS.update(PERMISSION_DEFAULTS)
import workbook as _workbook
if getattr(_workbook,'PRODUCTION_REVISION',0)!=1:importlib.reload(_workbook)
from workbook import read_upload,TITLES,SPECS,forecast_summary,segment_map,segment_filter,related_tables
from tables import table_controls
# Streamlit may retain helper modules across a source update. Reload only an
# older analysis revision, in dependency order; never reload account storage.
import importlib
import grounded_ai as _grounded_ai
from stock_accounts import insights as _insights, assistant_insights as _assistant, workspace_insights as _workspace
for _module in (_grounded_ai,_insights,_assistant,_workspace):
    if getattr(_module,'INSIGHTS_REVISION',0)!=3:
        importlib.reload(_module)
# Refresh the dispatcher when an already-running process gains planning RPCs.
if getattr(_workspace,'PLANNING_REVISION',0)!=5:
    importlib.reload(_workspace)
from stock_accounts import planning as _planning, matched_export as _matched_export
for _module in (_planning,_matched_export):
    if getattr(_module,'TABLE_EXPORT_REVISION',0)!=(2 if _module is _matched_export else 1):
        importlib.reload(_module)
from stock_accounts import production as _production
if getattr(_production,'REVISION',0)!=5:importlib.reload(_production)
from stock_accounts.workspace_insights import render_exact_workspace,process_account_navigation,account_page_style
from stock_accounts import auth as _account_auth
if getattr(_account_auth,'PRODUCTION_ACCESS_REVISION',0)!=2:importlib.reload(_account_auth)
from stock_accounts.auth import user_page as account_admin_page,password_page,initialize as initialize_account_store

st.set_page_config(page_title="Stock & Planning",page_icon="📦",layout="wide")
st.markdown("""<style>.block-container{padding-top:2rem;max-width:1900px}h1,h2,h3{color:#285e4c}div[data-testid='stMetric']{display:none}.stButton>button{border-radius:7px}div[data-testid='stDataFrame']{border:1px solid #e0e8e3;border-radius:8px}</style>""",unsafe_allow_html=True)

@st.cache_resource
def initialize(url,admin_username,admin_password):
    store=Store(url);store.bootstrap_admin(admin_username,admin_password);return store

def configuration():
    try:secrets=dict(st.secrets)
    except (FileNotFoundError,st.errors.StreamlitSecretNotFoundError):secrets={}
    return {k:str(secrets.get(k,os.environ.get(k,""))) for k in ["DATABASE_URL","ADMIN_USERNAME","ADMIN_PASSWORD"]}

def sign_out():
    st.session_state.clear();st.rerun()

def login_page(store):
    _,middle,_=st.columns([1,1.3,1])
    with middle:
        st.title("Stock & Planning")
        st.write("Sign in to your inventory workspace.")
        with st.form("login",clear_on_submit=True):
            username=st.text_input("Username",autocomplete="username",key="login_username")
            password=st.text_input("Password",type="password",autocomplete="current-password",key="login_password")
            submit=st.form_submit_button("Sign in",type="primary",width="stretch")
        if submit:
            actor=store.login(username,password)
            if actor:
                st.session_state.actor=actor
                st.session_state.login_at=st.session_state.last_active=time.time()
                st.rerun()
            st.error("Invalid credentials, disabled account, or temporary lock. After repeated failures, wait 15 minutes.")
        st.caption("Accounts are created by the administrator. There is no public registration.")
    st.stop()

def require_admin(store,actor):
    if store.identity(actor)["role"]!="admin":
        raise AccessDenied("Administrator access required.")

def upload_page(store,actor):
    require_admin(store,actor)
    st.title("Update workbook")
    st.write("Refresh All in Excel, save the workbook, then upload it. Saved worksheets and the embedded Power Pivot tables are read together.")
    file=st.file_uploader("Master workbook",type=["xlsx","zip"],help="Up to 25 MB. .xlsx or a previously prepared .stock.zip package.")
    if st.button("Validate and replace shared data",type="primary",disabled=file is None):
        require_admin(store,actor)
        try:
            with st.spinner("Reading worksheets and embedded model…"):
                dataset=read_upload(file.getvalue(),file.name)
                store.save_dataset(actor,file.name,dataset)
            st.success(f"Updated all seven views and {len(dataset['tables'])} model tables. All users see this shared version.")
            if not dataset["tables"]:st.warning("This workbook has no embedded model; only saved worksheet views are available.")
        except (ValueError,KeyError) as exc:
            st.error(str(exc))
        except AccessDenied:raise
        except Exception:
            st.error("The workbook could not be processed or saved. The previous dataset is still available. Confirm the workbook format and database connection.")

def user_page(store,actor):
    require_admin(store,actor)
    st.title("Manage viewer accounts")
    st.caption("Only the configured administrator can create, disable or reset viewer accounts.")
    users=store.users(actor)
    st.table(pd.DataFrame(users)[["username","role","active"]])
    with st.form("create_viewer",clear_on_submit=True):
        st.subheader("Create viewer")
        username=st.text_input("New viewer username")
        password=st.text_input("Initial password (at least 12 characters)",type="password")
        create=st.form_submit_button("Create viewer",type="primary")
    if create:
        try:store.create_viewer(actor,username,password);st.success("Viewer created. Share their credentials privately.")
        except ValueError as exc:st.error(str(exc))
    viewers=[r["username"] for r in users if r["role"]=="viewer"]
    if viewers:
        with st.form("update_viewer",clear_on_submit=True):
            st.subheader("Reset or enable/disable viewer")
            selected=st.selectbox("Viewer",viewers)
            action=st.selectbox("Action",["Reset password","Disable account","Enable account"])
            new_password=st.text_input("New password for reset only",type="password")
            update=st.form_submit_button("Apply change")
        if update:
            try:
                if action=="Reset password":store.update_viewer(actor,selected,password=new_password)
                else:store.update_viewer(actor,selected,active=action=="Enable account")
                st.success("Account updated. Existing sessions for this user have been revoked.")
            except ValueError as exc:st.error(str(exc))


def details_page(dataset,mapping,segment):
    selected=st.session_state.detail
    if st.button("← Back to table"):
        del st.session_state.detail
        st.session_state.grid_revision=st.session_state.get("grid_revision",0)+1
        st.rerun()
    code=selected["code"]
    st.title(str(code))
    st.caption(f"{selected['title']} · {selected['column']}")
    with st.expander("Selected row — all values"):
        st.table(pd.DataFrame([selected["row"]]))
    tables=dataset.get("tables",[])
    if not tables:
        st.info("No embedded model tables are available in this workbook.");return
    entire=st.radio("Record scope",["All related records","Entire workbook"],horizontal=True,key="detail_scope")=="Entire workbook"
    matched=related_tables(tables,code,entire)
    options=[t["name"] for t in matched]
    available=[t["name"] for t in matched if t["rows"]]
    default=options.index(available[0]) if available else 0
    table_name=st.selectbox("Source table",options,index=default,key="detail_table")
    t=next(t for t in matched if t["name"]==table_name)
    segment=st.selectbox("Segment (Source.Name)",["All segments"]+sorted({v for s in mapping.values() for v in s}),key="detail_segment")
    frame=segment_filter(pd.DataFrame(t["rows"],columns=t["headers"]),mapping,segment)
    st.caption("Every source column is available. Related records include components, parent products, batches and periods. The selected value is a saved/calculated worksheet result; DAX is not re-evaluated.")
    table_controls(frame,"detail_"+table_name)


def dashboard_page(store,actor,identity):
    current=store.get_dataset(actor)
    if not current:
        st.title("Stock & Planning")
        st.info("No workbook has been uploaded yet. The administrator must upload the refreshed Excel workbook.")
        return
    dataset=current["data"];mapping=segment_map(dataset.get("tables",[]))
    segment_names=sorted({v for values in mapping.values() for v in values})
    if "detail" in st.session_state:
        details_page(dataset,mapping,"All segments");return
    st.title("Stock & Planning")
    date=datetime.fromtimestamp(current["updated_at"],tz=timezone.utc).strftime("%d %b %Y %H:%M UTC")
    st.caption(f"{current['filename']} · Updated {date}")
    a,b=st.columns([2,1])
    title=a.selectbox("Worksheet view",TITLES)
    segment=b.selectbox("Segment (Source.Name)",["All segments"]+segment_names,key="main_segment")
    idx=TITLES.index(title);sheet=dataset["sheets"][idx]
    frame=pd.DataFrame(sheet["rows"],columns=sheet["headers"])
    frame=segment_filter(frame,mapping,segment)
    monthly=False
    if idx==4:
        monthly=st.radio("Forecast view",["Product totals","Monthly details"],horizontal=True)=="Monthly details"
        if not monthly:frame=forecast_summary(frame)
        st.caption("Pending quantity = total forecast − total transfers − current stock once per material. Monthly-detail filtered totals recalculate this formula.")
    elif idx in (5,6):st.caption("Source: "+SPECS[idx][0]+". Blanks and negative balances are retained.")
    filtered,selected=table_controls(frame,"main_"+str(idx)+"_"+str(monthly),selectable=True,forecast_monthly=idx==4 and monthly)
    if selected:
        row,column=selected
        code=row.get("Material") or row.get("Component")
        st.session_state.detail={"code":code,"row":row,"column":column,"title":title}
        st.rerun()
    st.caption("This app has no data-download links. Refresh in Excel before updating. Excel Power Query/DAX refresh does not run here.")


def main():
    if not st.get_option("client.disableDataExport"):
        st.error("Deployment requires client.disableDataExport = true in .streamlit/config.toml.");st.stop()
    cfg=configuration()
    if not all(cfg.values()) or len(cfg["ADMIN_PASSWORD"])<12 or cfg["ADMIN_PASSWORD"].startswith(("REPLACE_","CHANGE_")):
        st.title("Stock & Planning — deployment setup")
        st.info("The owner must configure DATABASE_URL, ADMIN_USERNAME and ADMIN_PASSWORD in Streamlit Cloud Secrets. See README.md and secrets.example.toml in the repository. No default password is enabled.")
        st.stop()
    try:store=initialize_account_store(cfg["DATABASE_URL"],cfg["ADMIN_USERNAME"],cfg["ADMIN_PASSWORD"],store_revision="2026-10-17-access-rights-v2")
    except Exception:
        st.error("Cannot initialize the account database. Check the database connection and admin settings in Streamlit Secrets.");st.stop()
    actor=st.session_state.get("actor")
    if not actor:login_page(store)
    now=time.time()
    event=st.session_state.get("exact_website_ui")
    if isinstance(event,dict) and isinstance(event.get("activity"),(int,float)):
        st.session_state.last_active=max(st.session_state.get("last_active",0),min(now,event["activity"]))
    if now-st.session_state.get("login_at",0)>8*3600 or now-st.session_state.get("last_active",0)>1800:
        store.log_event(actor,"session_expired")
        sign_out()
    identity=store.identity(actor)
    process_account_navigation(store,actor)
    if st.session_state.get('_account_page'):
        account_page_style()
        st.session_state.last_active=now
        if st.button('← Back to workspace'):
            del st.session_state._account_page;st.rerun()
        with st.container(height=750,border=False,key='account_scroll'):
            if st.session_state._account_page=='password':password_page(store,actor)
            else:account_admin_page(store,actor)
        return
    render_exact_workspace(store,actor,identity)

try:
    main()
except AccessDenied:
    st.session_state.clear()
    st.warning("Your session is no longer active. Sign in again.")
    st.stop()
except Exception:
    logging.getLogger(__name__).exception("Stock Planning request failed")
    st.error("The request could not be completed. Please retry; if it continues, ask the administrator to check the database connection.")
    st.stop()
