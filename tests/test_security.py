import tempfile,unittest
from pathlib import Path
from storage import Store,AccessDenied,Actor

class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/"test.db"
        self.store=Store("sqlite:///"+str(self.path));self.store.bootstrap_admin("admin_user","Test-only-admin-password!123")
        self.admin=self.store.login("admin_user","Test-only-admin-password!123")
        self.store.create_viewer(self.admin,"viewer_user","Test-only-viewer-password!123")
        self.viewer=self.store.login("viewer_user","Test-only-viewer-password!123")
    def tearDown(self):self.tmp.cleanup()
    def test_password_and_viewer_permissions(self):
        self.assertIsNone(self.store.login("admin_user","wrong"))
        self.assertEqual(self.store.identity(self.viewer)["role"],"viewer")
        for action in [lambda:self.store.create_viewer(self.viewer,"rogue_user","Not-allowed-password!123"),lambda:self.store.save_dataset(self.viewer,"x",{}),lambda:self.store.users(self.viewer),lambda:self.store.update_viewer(self.viewer,"viewer_user",active=True)]:
            with self.assertRaises(AccessDenied):action()
        with self.assertRaises(AccessDenied):self.store.get_dataset(None)
    def test_revocation_and_password_reset(self):
        self.store.update_viewer(self.admin,"viewer_user",active=False)
        with self.assertRaises(AccessDenied):self.store.identity(self.viewer)
        self.store.update_viewer(self.admin,"viewer_user",active=True,password="Reset-viewer-password!123")
        self.assertIsNone(self.store.login("viewer_user","Test-only-viewer-password!123"))
        self.assertIsNotNone(self.store.login("viewer_user","Reset-viewer-password!123"))
    def test_persistent_data_and_hashes(self):
        self.store.save_dataset(self.admin,"fixture.xlsx",{"sheets":[],"tables":[]})
        reopened=Store("sqlite:///"+str(self.path))
        self.assertEqual(reopened.get_dataset(self.viewer)["filename"],"fixture.xlsx")
        with reopened.transaction() as db:
            r=reopened.run(db,"SELECT salt,password_hash FROM accounts WHERE username=?",("viewer_user",)).fetchone()
            self.assertNotIn("Test-only",r["password_hash"]);self.assertEqual(len(r["salt"]),32)
    def test_lockout_persists(self):
        for _ in range(5):self.store.login("viewer_user","wrong")
        self.assertIsNone(Store("sqlite:///"+str(self.path)).login("viewer_user","Test-only-viewer-password!123"))
    def test_admin_rotation_revokes_session(self):
        self.store.bootstrap_admin("admin_user","Rotated-admin-password!123")
        with self.assertRaises(AccessDenied):self.store.identity(self.admin)
        new=self.store.login("admin_user","Rotated-admin-password!123")
        self.store.bootstrap_admin("new_admin","New-admin-password!123")
        with self.assertRaises(AccessDenied):self.store.identity(new)
