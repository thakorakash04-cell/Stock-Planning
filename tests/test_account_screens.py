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
    def test_manage_users_opens_in_one_run_and_returns_to_dashboard(self):
        at=self.login('admin_user','Initial-admin-password!123')
        at.session_state['exact_website_ui']={'id':uuid.uuid4().hex,'action':'open_admin'}
        with patch('streamlit.rerun',side_effect=AssertionError('Navigation must not trigger an extra rerun')):
            at.run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any(x.value=='Access log' for x in at.subheader))
        self.assertTrue(any(x.label=='New viewer username' for x in at.text_input))
        self.assertEqual(len(at.get('component_instance')),0)
        self.assertIn("key='account_scroll'",Path('app.py').read_text())
        self.assertEqual(len(at.dataframe),2)
        next(b for b in at.button if b.label=='← Back to workspace').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(len(at.get('component_instance')),1)
        self.assertTrue(any('[data-stale="true"]:has(iframe' in m.value and 'opacity:1!important' in m.value for m in at.markdown))

    def test_viewer_cannot_open_admin_console(self):
        at=self.login('viewer_user','Initial-viewer-password!123')
        if IS_STOCK:
            at.session_state['exact_website_ui']={'id':uuid.uuid4().hex,'action':'open_admin'};at.run()
            self.assertNotIn('_account_page',at.session_state)
        else:self.assertFalse(any(x.label=='Manage users' for x in at.toggle))
        self.assertFalse(any(x.value=='Access log' for x in at.subheader))

    def test_production_and_menu_rights_save_repeatedly_with_confirmation(self):
        at=self.login('admin_user','Initial-admin-password!123');self.open_screen(at,'users')
        old_viewer=self.store.login('viewer_user','Initial-viewer-password!123')
        at.checkbox(key='permission_viewer_user_edit_production').set_value(True)
        at.checkbox(key='permission_viewer_user_edit_upcoming').set_value(True)
        at.checkbox(key='permission_viewer_user_menu_0').set_value(False)
        next(b for b in at.button if b.label=='Save access rights').click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any('Access rights saved for viewer_user' in x.value for x in at.success))
        with self.assertRaises(AccessDenied):self.store.identity(old_viewer)
        viewer=self.store.login('viewer_user','Initial-viewer-password!123')
        rights=self.store.identity(viewer)['permissions']
        self.assertTrue(rights['edit_production'] and rights['edit_upcoming']);self.assertFalse(rights['menu_0'])
        self.assertTrue(at.checkbox(key='permission_viewer_user_edit_production').value)
        self.assertFalse(at.checkbox(key='permission_viewer_user_menu_0').value)
        at.checkbox(key='permission_viewer_user_edit_production').set_value(False)
        at.checkbox(key='permission_viewer_user_menu_0').set_value(True)
        next(b for b in at.button if b.label=='Save access rights').click().run()
        self.assertFalse(at.exception)
        viewer=self.store.login('viewer_user','Initial-viewer-password!123')
        rights=self.store.identity(viewer)['permissions'];self.assertFalse(rights['edit_production']);self.assertTrue(rights['menu_0'])

    def test_permission_save_error_is_shown_without_crashing(self):
        at=self.login('admin_user','Initial-admin-password!123');self.open_screen(at,'users')
        with patch('stock_accounts.store.Store.update_permissions',side_effect=ValueError('Permission settings need refresh')):
            next(b for b in at.button if b.label=='Save access rights').click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any('Permission settings need refresh' in x.value for x in at.error))
