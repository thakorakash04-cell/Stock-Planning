import json,sqlite3,tempfile,time,unittest
from pathlib import Path
from storage import Store,AccessDenied,password_record

class AccountAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'accounts.db';self.url='sqlite:///'+str(self.path)
        self.store=Store(self.url);self.store.bootstrap_admin('admin_user','Initial-admin-password!123')
        self.admin=self.store.login('admin_user','Initial-admin-password!123')
        self.store.create_viewer(self.admin,'viewer_user','Initial-viewer-password!123')
        self.viewer=self.store.login('viewer_user','Initial-viewer-password!123')
    def tearDown(self):self.tmp.cleanup()
    def test_permissions_only_admin_can_grant_and_revoke(self):
        for action in [lambda:self.store.update_permissions(self.viewer,'viewer_user',{'download':True}),lambda:self.store.access_log(self.viewer),lambda:self.store.save_dataset(self.viewer,'x',{})]:
            with self.assertRaises(AccessDenied):action()
        self.store.update_permissions(self.admin,'viewer_user',{'download':True,'update_data':True})
        with self.assertRaises(AccessDenied):self.store.identity(self.viewer)
        self.viewer=self.store.login('viewer_user','Initial-viewer-password!123')
        self.store.require_permission(self.viewer,'download');self.store.save_dataset(self.viewer,'test',{'rows':[1]})
        with self.assertRaises(AccessDenied):self.store.create_viewer(self.viewer,'rogue_user','Never-allowed-password!123')
        self.store.update_permissions(self.admin,'viewer_user',{'download':False,'update_data':False})
        current=self.store.login('viewer_user','Initial-viewer-password!123')
        with self.assertRaises(AccessDenied):self.store.require_permission(current,'download')
        for invalid in [{'admin':True},{'download':'true'},{'download':1}]:
            with self.assertRaises(ValueError):self.store.update_permissions(self.admin,'viewer_user',invalid)
    def test_self_password_change_revokes_sessions_and_survives_restart(self):
        second=self.store.login('viewer_user','Initial-viewer-password!123')
        with self.assertRaises(ValueError):self.store.change_password(self.viewer,'wrong','Replacement-viewer-password!123')
        self.store.change_password(self.viewer,'Initial-viewer-password!123','Replacement-viewer-password!123')
        for actor in (self.viewer,second):
            with self.assertRaises(AccessDenied):self.store.identity(actor)
        self.assertIsNone(self.store.login('viewer_user','Initial-viewer-password!123'))
        reopened=Store(self.url)
        self.assertIsNotNone(reopened.login('viewer_user','Replacement-viewer-password!123'))
        self.store.change_password(self.admin,'Initial-admin-password!123','Replacement-admin-password!123')
        reopened.bootstrap_admin('admin_user','Initial-admin-password!123')
        self.assertIsNotNone(reopened.login('admin_user','Replacement-admin-password!123'))
        self.assertIsNone(reopened.login('admin_user','Initial-admin-password!123'))
        reopened.bootstrap_admin('admin_user','Recovery-secret-password!123')
        self.assertIsNotNone(reopened.login('admin_user','Recovery-secret-password!123'))
    def test_audit_logs_persist_and_do_not_include_passwords(self):
        self.store.login('viewer_user','incorrect-secret-123')
        self.store.record_access(self.viewer,'Stock overview');self.store.record_access(self.viewer,'Stock overview')
        self.store.log_event(self.viewer,'logout')
        events=Store(self.url).access_log(self.admin,'viewer_user')
        self.assertTrue({'login_success','login_failed','view','logout'}<={e['action'] for e in events})
        self.assertEqual(sum(e['action']=='view' for e in events),1)
        self.assertTrue(all(e['session_id'] for e in events if e['action']=='view'))
        self.assertNotIn('password!123',json.dumps(events));self.assertNotIn('incorrect-secret',json.dumps(events))
        user=next(u for u in self.store.users(self.admin) if u['username']=='viewer_user')
        self.assertIsNotNone(user['last_login_at']);self.assertIsNotNone(user['last_access_at'])
    def test_existing_database_migrates_without_losing_accounts_or_datasets(self):
        path=Path(self.tmp.name)/'legacy.db';salt,digest=password_record('Legacy-admin-password!123')
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE accounts(username TEXT PRIMARY KEY,salt TEXT NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,active INTEGER DEFAULT 1,session_version INTEGER DEFAULT 1,failed_attempts INTEGER DEFAULT 0,locked_until DOUBLE PRECISION DEFAULT 0,created_at DOUBLE PRECISION NOT NULL)')
            db.execute('INSERT INTO accounts(username,salt,password_hash,role,created_at) VALUES(?,?,?,?,?)',('legacy_admin',salt,digest,'admin',time.time()))
        migrated=Store('sqlite:///'+str(path));migrated.bootstrap_admin('legacy_admin','Legacy-admin-password!123')
        actor=migrated.login('legacy_admin','Legacy-admin-password!123');self.assertIsNotNone(actor)
        migrated.save_dataset(actor,'existing',{'data':[123]})
        self.assertEqual(Store('sqlite:///'+str(path)).get_dataset(actor)['data'],{'data':[123]})
