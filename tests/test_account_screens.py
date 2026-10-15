import os,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
import streamlit as st
from streamlit.testing.v1 import AppTest
from storage import Store,AccessDenied
IS_STOCK=True
RIGHT='download'

class AccountScreenTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.url='sqlite:///'+str(Path(self.tmp.name)/'screens.db')
        self.env=patch.dict(os.environ,{'DATABASE_URL':self.url,'ADMIN_USERNAME':'admin_user','ADMIN_PASSWORD':'Initial-admin-password!123'});self.env.start()
        self.store=Store(self.url);self.store.bootstrap_admin('admin_user','Initial-admin-password!123');self.admin=self.store.login('admin_user','Initial-admin-password!123')
        self.store.create_viewer(self.admin,'viewer_user','Initial-viewer-password!123')
    def tearDown(self):st.cache_resource.clear();self.env.stop();self.tmp.cleanup()
    def login(self,username,password):
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30)
        at.secrets.update({'DATABASE_URL':self.url,'ADMIN_USERNAME':'admin_user','ADMIN_PASSWORD':'Initial-admin-password!123'})
        at.run();at.text_input(key='login_username').set_value(username);at.text_input(key='login_password').set_value(password)
        next(b for b in at.button if b.label=='Sign in').click().run();self.assertEqual(len(at.exception),0)
        return at
    def open_screen(self,at,screen):
        if IS_STOCK:
            at.session_state['exact_website_ui']={'id':uuid.uuid4().hex,'action':'open_admin' if screen=='users' else 'open_password'};at.run()
        else:at.toggle(key='workspace_'+screen).set_value(True).run()
        self.assertEqual(len(at.exception),0)
    def test_admin_can_edit_rights_and_inspect_logs(self):
        at=self.login('admin_user','Initial-admin-password!123');self.open_screen(at,'users')
        checkbox=at.checkbox(key='permission_viewer_user_'+RIGHT);target=not checkbox.value
        checkbox.set_value(target);next(b for b in at.button if b.label=='Save access rights').click().run()
        viewer=self.store.login('viewer_user','Initial-viewer-password!123')
        self.assertEqual(self.store.identity(viewer)['permissions'][RIGHT],target)
        self.assertTrue(any(x.value=='Access log' for x in at.subheader))
        self.assertTrue(any(e['action']=='permissions_changed' for e in self.store.access_log(self.admin)))
    def test_every_role_can_change_own_password(self):
        for username,old,new in [('viewer_user','Initial-viewer-password!123','New-viewer-password!123'),('admin_user','Initial-admin-password!123','New-admin-password!123')]:
            at=self.login(username,old);self.open_screen(at,'password')
            next(x for x in at.text_input if x.label=='Current password').set_value(old)
            next(x for x in at.text_input if x.label=='New password (at least 12 characters)').set_value(new)
            next(x for x in at.text_input if x.label=='Confirm new password').set_value(new)
            next(b for b in at.button if b.label=='Change password').click().run()
            self.assertEqual(len(at.exception),0)
            self.assertTrue(any(x.label=='Username' for x in at.text_input))
            self.assertIsNotNone(Store(self.url).login(username,new))
    def test_viewer_cannot_open_admin_console(self):
        at=self.login('viewer_user','Initial-viewer-password!123')
        if IS_STOCK:
            at.session_state['exact_website_ui']={'id':uuid.uuid4().hex,'action':'open_admin'};at.run()
            self.assertNotIn('_account_page',at.session_state)
        else:self.assertFalse(any(x.label=='Manage users' for x in at.toggle))
        self.assertFalse(any(x.value=='Access log' for x in at.subheader))
