import base64,tempfile,unittest
from pathlib import Path
from exact_ui import handle_request,ui_payload
from storage import Store,AccessDenied

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store('sqlite:///'+str(Path(self.tmp.name)/'db.sqlite'))
        self.store.bootstrap_admin('admin_user','Test-admin-password!123');self.admin=self.store.login('admin_user','Test-admin-password!123')
        self.store.create_viewer(self.admin,'viewer_user','Test-viewer-password!123');self.viewer=self.store.login('viewer_user','Test-viewer-password!123')
    def tearDown(self):self.tmp.cleanup()
    def test_viewer_cannot_invoke_hidden_admin_actions(self):
        for action in ('upload','list_users','create_viewer','update_viewer'):
            with self.assertRaises(AccessDenied):handle_request(self.store,self.viewer,{'action':action,'username':'other_viewer','password':'An-example-password!123','content':'x'})
    def test_admin_account_actions_use_existing_store(self):
        handle_request(self.store,self.admin,{'action':'create_viewer','username':'new_viewer','password':'New-viewer-password!123'})
        self.assertTrue(self.store.login('new_viewer','New-viewer-password!123'))
        names=[u['username'] for u in handle_request(self.store,self.admin,{'action':'list_users'})['users']]
        self.assertIn('new_viewer',names)
        handle_request(self.store,self.admin,{'action':'update_viewer','username':'new_viewer','operation':'disable'})
        self.assertIsNone(self.store.login('new_viewer','New-viewer-password!123'))
    def test_revoked_actor_cannot_heartbeat(self):
        self.store.update_viewer(self.admin,'viewer_user',active=False)
        with self.assertRaises(AccessDenied):handle_request(self.store,self.viewer,{'action':'heartbeat'})
    def test_empty_and_saved_payloads_have_seven_views(self):
        data,tables,version=ui_payload(None);self.assertEqual(len(data['sheets']),7);self.assertEqual(tables,[])
        dataset={'sheets':[{'name':'Summary','headers':['Material'],'rows':[['TEST']]}],'tables':[]}
        self.store.save_dataset(self.admin,'test.xlsx',dataset)
        current=self.store.get_dataset(self.viewer);data,tables,version=ui_payload(current)
        self.assertEqual(data['sheets'][0]['rows'],[['TEST']]);self.assertEqual(data['filename'],'test.xlsx')

    def test_delegated_actions_do_not_grant_administration(self):
        from unittest.mock import patch
        self.store.update_permissions(self.admin,'viewer_user',{'download':True,'update_data':True})
        viewer=self.store.login('viewer_user','Test-viewer-password!123')
        self.assertTrue(handle_request(self.store,viewer,{'action':'export'})['ok'])
        with patch('stock_accounts.workspace.read_upload',return_value={'sheets':[],'tables':[]}):
            answer=handle_request(self.store,viewer,{'action':'upload','filename':'fixture.xlsx','content':base64.b64encode(b'fixture').decode()})
        self.assertTrue(answer['ok'])
        self.assertEqual(self.store.get_dataset(viewer)['filename'],'fixture.xlsx')
        with self.assertRaises(AccessDenied):handle_request(self.store,viewer,{'action':'open_admin'})
        self.store.update_permissions(self.admin,'viewer_user',{'download':False})
        with self.assertRaises(AccessDenied):handle_request(self.store,viewer,{'action':'export'})
