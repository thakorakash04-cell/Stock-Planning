import tempfile,time,unittest
from pathlib import Path
import streamlit as st
from streamlit.testing.v1 import AppTest
from storage import Store

class UITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.url="sqlite:///"+str(Path(self.tmp.name)/"ui.db")
        s=Store(self.url);s.bootstrap_admin("admin_user","Test-admin-password!123")
        admin=s.login("admin_user","Test-admin-password!123")
        s.create_viewer(admin,"viewer_user","Test-viewer-password!123")
        sheets=[]
        from workbook import SPECS
        for name,*_ in SPECS:sheets.append({"name":name,"headers":["Material","Material(text)","Quantity"],"rows":[["SKU-1","Synthetic test product",10]]})
        s.save_dataset(admin,"synthetic-test.xlsx",{"sheets":sheets,"tables":[]})
        self.at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=30)
        self.at.secrets.update({"DATABASE_URL":self.url,"ADMIN_USERNAME":"admin_user","ADMIN_PASSWORD":"Test-admin-password!123"})
    def tearDown(self):
        st.cache_resource.clear();self.tmp.cleanup()
    def login(self,user,password):
        self.at.run()
        self.assertEqual(len(self.at.exception),0)
        self.at.text_input(key="login_username").set_value(user)
        self.at.text_input(key="login_password").set_value(password)
        next(b for b in self.at.button if b.label=="Sign in").click().run()
        self.assertEqual(len(self.at.exception),0)
        self.assertEqual(len(self.at.error),0,[e.value for e in self.at.error])
    def test_viewer_sees_data_without_admin_widgets(self):
        self.login("viewer_user","Test-viewer-password!123")
        nav=next(r for r in self.at.radio if r.label=="Workspace")
        self.assertEqual(nav.options,["Dashboard"])
        self.assertTrue(len(self.at.dataframe)>0)
        self.assertEqual(len(self.at.get("file_uploader")),0)
        self.assertEqual(len(self.at.get("download_button")),0)
    def test_admin_can_open_upload_and_manage_users(self):
        self.login("admin_user","Test-admin-password!123")
        nav=next(r for r in self.at.radio if r.label=="Workspace")
        self.assertIn("Upload workbook",nav.options)
        nav.set_value("Upload workbook").run()
        self.assertEqual(len(self.at.get("file_uploader")),1)
        next(r for r in self.at.radio if r.label=="Workspace").set_value("Manage users").run()
        self.assertTrue(any(b.label=="Create viewer" for b in self.at.button))
        self.assertEqual(len(self.at.error),0,[e.value for e in self.at.error])
    def test_wrong_password_cannot_render_database(self):
        self.at.run();self.at.text_input(key="login_username").set_value("viewer_user")
        self.at.text_input(key="login_password").set_value("wrong")
        next(b for b in self.at.button if b.label=="Sign in").click().run()
        self.assertEqual(len(self.at.dataframe),0)
        self.assertEqual(len(self.at.get("file_uploader")),0)
        self.assertTrue(self.at.error)
