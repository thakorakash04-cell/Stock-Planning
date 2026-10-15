"""Regression for Streamlit processes retaining pre-update generic helper modules."""
import sys,tempfile,types
from pathlib import Path
from unittest.mock import patch
import streamlit as st
from streamlit.testing.v1 import AppTest

def test_startup_and_login_ignore_stale_legacy_helper_modules():
    old_auth=types.ModuleType('workspace_auth')
    old_auth.require_workspace=lambda:None
    old_store=types.ModuleType('workspace_store')
    # Deliberately omit can/require_permission/Store, as an older cached helper can.
    with tempfile.TemporaryDirectory() as folder:
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30)
        at.secrets.update({'DATABASE_URL':'sqlite:///'+str(Path(folder)/'startup.db'),
            'ADMIN_USERNAME':'startup_admin','ADMIN_PASSWORD':'Startup-admin-password!123'})
        with patch.dict(sys.modules,{'workspace_auth':old_auth,'storage':old_store,'exact_ui':types.ModuleType('exact_ui')}):
            at.run()
            assert not at.exception
            assert any(field.label=='Username' for field in at.text_input)
            at.text_input(key='login_username').set_value('startup_admin')
            at.text_input(key='login_password').set_value('Startup-admin-password!123')
            next(button for button in at.button if button.label=='Sign in').click().run()
            assert not at.exception
            assert at.session_state['actor'].username=='startup_admin'
            assert len(at.get('component_instance'))==1
        st.cache_resource.clear()
