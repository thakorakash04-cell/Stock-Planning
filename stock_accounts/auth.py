"""Shared account screens. All authorization is repeated by Store operations."""
import os,time,json
from datetime import datetime,timezone
import pandas as pd
import streamlit as st
from .store import Store,AccessDenied

APP_TITLE='Stock & Planning'
from .access import MENU_LABELS
PERMISSION_LABELS={'download': 'Download / export data', 'update_data': 'Upload and replace shared workbook', 'use_tools': 'Use Ask AI and Insights (share relevant records with Gemini)', 'edit_production':'Edit ongoing production expected quantity and end date', 'edit_upcoming':'Add, edit and delete shared upcoming production plans', **{'menu_'+str(i):'Open '+label for i,label in enumerate(MENU_LABELS)}}
@st.cache_resource
def initialize(url,username,password,store_revision="2026-10-17-access-rights-v2"):
    # The revision invalidates pre-deployment cached Store instances.
    store=Store(url);store.bootstrap_admin(username,password);return store

def sign_out(store=None,reason='logout'):
    if store and st.session_state.get('actor'):
        try:store.log_event(st.session_state.actor,reason)
        except AccessDenied:pass
    st.session_state.clear();st.rerun()

def login_page(store):
    _,middle,_=st.columns([1,1.3,1])
    with middle:
        st.title(APP_TITLE);st.write('Sign in to your workspace.')
        with st.form('login',clear_on_submit=True):
            username=st.text_input('Username',autocomplete='username',key='login_username')
            password=st.text_input('Password',type='password',autocomplete='current-password',key='login_password')
            submit=st.form_submit_button('Sign in',type='primary',width='stretch')
        if submit:
            actor=store.login(username,password)
            if actor:
                st.session_state.actor=actor
                st.session_state.login_at=st.session_state.last_active=time.time();st.rerun()
            st.error('Invalid credentials, disabled account, or temporary lock. After repeated failures, wait 15 minutes.')
        st.caption('Accounts are created by the administrator. There is no public registration.')
    st.stop()

def require_admin(store,actor):
    if store.identity(actor)['role']!='admin':raise AccessDenied('Administrator access required.')

def require_permission(store,actor,permission):
    return store.require_permission(actor,permission)

def format_time(value):
    from .clock import display
    return display(value) if value else 'Not recorded'

def user_page(store,actor):
    require_admin(store,actor)
    st.title('Manage viewer accounts')
    notice=st.session_state.pop('_access_rights_notice',None)
    if notice:st.success(notice)
    st.caption('Only the administrator can set access rights. Permission changes, disabling accounts and password resets revoke existing user sessions.')
    users=store.users(actor)
    display=[{'Username':u['username'],'Role':u['role'],'Active':bool(u['active']),
              'Last login':format_time(u['last_login_at']),'Last access':format_time(u['last_access_at']),
              **{label:bool(u['permissions'].get(key)) for key,label in PERMISSION_LABELS.items()}} for u in users]
    st.dataframe(pd.DataFrame(display),hide_index=True,width="stretch",height=260)
    with st.form('create_viewer',clear_on_submit=True):
        st.subheader('Create viewer')
        username=st.text_input('New viewer username')
        password=st.text_input('Initial password (at least 12 characters)',type='password')
        create=st.form_submit_button('Create viewer',type='primary')
    if create:
        try:store.create_viewer(actor,username,password);st.success('Viewer created. Share credentials privately.');st.rerun()
        except ValueError as exc:st.error(str(exc))
    viewers=[u for u in users if u['role']=='viewer']
    if viewers:
        selected=st.selectbox('Viewer',[u['username'] for u in viewers],key='selected_account')
        user=next(u for u in viewers if u['username']==selected)
        # Sync keyed widgets to persisted rights after saving or switching users.
        fingerprint=(selected,json.dumps(user['permissions'],sort_keys=True))
        if st.session_state.get('_access_rights_fingerprint')!=fingerprint:
            for key in PERMISSION_LABELS:
                st.session_state.pop('permission_'+selected+'_'+key,None)
            st.session_state['_access_rights_fingerprint']=fingerprint
        with st.form('permissions_'+selected):
            st.subheader('Access rights')
            st.caption('Choose the sections this viewer can open and the actions they can perform. Production edit rights also require Open Production. Ask AI and Insights require both their Open section right and Use Ask AI and Insights.')
            permissions={key:st.checkbox(label,value=user['permissions'].get(key,False),key='permission_'+selected+'_'+key) for key,label in PERMISSION_LABELS.items()}
            save=st.form_submit_button('Save access rights',type='primary')
        if save:
            try:
                store.update_permissions(actor,selected,permissions)
                saved_user=next(u for u in store.users(actor) if u['username']==selected)
                if any(saved_user['permissions'].get(k)!=v for k,v in permissions.items()):
                    raise ValueError('The saved rights could not be verified. Refresh this page and retry.')
            except (ValueError,PermissionError) as exc:st.error(str(exc))
            else:
                st.session_state['_access_rights_notice']='Access rights saved for '+selected+'. Existing viewer sessions were signed out; sign in again to apply the new rights.'
                st.rerun()
        with st.form('update_viewer',clear_on_submit=True):
            st.subheader('Reset or enable/disable viewer')
            action=st.selectbox('Action',['Reset password','Disable account','Enable account'])
            new_password=st.text_input('New password for reset only',type='password')
            update=st.form_submit_button('Apply change')
        if update:
            try:
                if action=='Reset password':store.update_viewer(actor,selected,password=new_password)
                else:store.update_viewer(actor,selected,active=action=='Enable account')
                st.success('Account updated. Existing sessions have been revoked.');st.rerun()
            except ValueError as exc:st.error(str(exc))
    st.subheader('Access log')
    st.caption('Events start when this update is deployed. Times are IST. Assessment contents and passwords are never logged.')
    # Free text includes unknown usernames from failed login attempts.
    query=st.text_input('Filter log by exact username (optional)',key='audit_username').strip().lower()
    if st.button('Refresh access log'):st.rerun()
    events=store.access_log(actor,query or None)
    table=pd.DataFrame([{**e,'occurred_at':format_time(e['occurred_at'])} for e in events])
    if table.empty:st.info('No matching access events.')
    else:st.dataframe(table,hide_index=True,width="stretch",height=400)

def password_page(store,actor):
    st.title('Change password')
    st.caption('Enter your current password. After a successful change, all existing sessions are signed out, including this one.')
    with st.form('change_password',clear_on_submit=True):
        current=st.text_input('Current password',type='password',autocomplete='current-password')
        new=st.text_input('New password (at least 12 characters)',type='password',autocomplete='new-password')
        confirm=st.text_input('Confirm new password',type='password',autocomplete='new-password')
        submit=st.form_submit_button('Change password',type='primary')
    if submit:
        if new!=confirm:st.error('The new passwords do not match.')
        else:
            try:store.change_password(actor,current,new)
            except ValueError as exc:st.error(str(exc))
            else:
                st.session_state.clear();st.rerun()

def require_workspace():
    try:secrets=dict(st.secrets)
    except (FileNotFoundError,st.errors.StreamlitSecretNotFoundError):secrets={}
    cfg={key:str(secrets.get(key,os.environ.get(key,''))) for key in ('DATABASE_URL','ADMIN_USERNAME','ADMIN_PASSWORD')}
    if not all(cfg.values()) or len(cfg['ADMIN_PASSWORD'])<12:
        st.title(APP_TITLE+' — setup');st.info('Set DATABASE_URL, ADMIN_USERNAME and ADMIN_PASSWORD in Streamlit Secrets. No default login is enabled.');st.stop()
    try:store=initialize(cfg['DATABASE_URL'],cfg['ADMIN_USERNAME'],cfg['ADMIN_PASSWORD'])
    except Exception:st.error('Cannot connect to the account database. Check Streamlit Secrets.');st.stop()
    actor=st.session_state.get('actor')
    if actor is None:login_page(store)
    now=time.time()
    if now-st.session_state.get('login_at',0)>8*3600 or now-st.session_state.get('last_active',0)>1800:sign_out(store,'session_expired')
    try:identity=store.identity(actor)
    except AccessDenied:sign_out()
    st.session_state.last_active=now
    st.session_state.workspace_role=identity['role'];st.session_state.workspace_permissions=identity['permissions']
    # This context remains server-side, never sent to the component/browser.
    st.session_state._account_store=store
    with st.sidebar:
        st.caption('Signed in as '+identity['username']+' · '+identity['role'])
        if st.button('Sign out',key='workspace_signout'):sign_out(store)
        password=st.toggle('Change password',key='workspace_password')
        manage=st.toggle('Manage users',key='workspace_users') if identity['role']=='admin' else False
    if password:password_page(store,actor);st.stop()
    if manage:user_page(store,actor);st.stop()
    store.record_access(actor,'Workspace')
    return store,actor,identity

def can(permission):
    store=st.session_state.get('_account_store');actor=st.session_state.get('actor')
    if not store or not actor:return False
    try:store.require_permission(actor,permission);return True
    except AccessDenied:return False

def can_export():return can('download')

def admin_download(*args,**kwargs):
    if not can_export():return False
    clicked=st.download_button(*args,**kwargs)
    if clicked:st.session_state._account_store.log_event(st.session_state.actor,'export','File download')
    return clicked

PRODUCTION_ACCESS_REVISION=3
