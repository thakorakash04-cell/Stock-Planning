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
    def component_args(self):
        import json
        components=self.at.get("component_instance")
        self.assertEqual(len(components),1)
        return json.loads(components[0].proto.json_args)
    def test_viewer_sees_original_ui_with_viewer_role(self):
        self.login("viewer_user","Test-viewer-password!123")
        args=self.component_args()
        self.assertEqual(args["role"],"viewer")
        self.assertEqual(args["data"]["sheets"][0]["rows"][0][0],"SKU-1")
        self.assertEqual(len(self.at.get("file_uploader")),0)
        self.assertEqual(len(self.at.get("download_button")),0)
    def test_admin_receives_original_ui_with_admin_role(self):
        self.login("admin_user","Test-admin-password!123")
        args=self.component_args()
        self.assertEqual(args["role"],"admin")
        self.assertEqual(args["user"],"admin_user")
        self.assertEqual(len(self.at.error),0)
    def test_revoked_session_removes_dashboard_component(self):
        self.login("viewer_user","Test-viewer-password!123")
        store=Store(self.url)
        admin=store.login("admin_user","Test-admin-password!123")
        store.update_viewer(admin,"viewer_user",active=False)
        self.at.run()
        self.assertEqual(len(self.at.get("component_instance")),0)
        self.assertTrue(self.at.warning)
    def test_component_event_returns_response_without_extra_rerun(self):
        self.login("admin_user","Test-admin-password!123")
        version=self.component_args()["version"]
        event={"id":"heartbeat-test","action":"heartbeat","activity":time.time()}
        self.at.session_state["exact_website_ui"]=event
        self.at.run()
        args=self.component_args()
        self.assertEqual(args["response"],{"id":"heartbeat-test","body":{"ok":True}})
        self.assertEqual(args["version"],version)
        self.assertEqual(args["data"]["filename"],"synthetic-test.xlsx")
        self.at.run()
        self.assertEqual(self.component_args()["response"],args["response"])
        self.assertEqual(len(self.at.exception),0)
    def test_wrong_password_cannot_render_database(self):
        self.at.run();self.at.text_input(key="login_username").set_value("viewer_user")
        self.at.text_input(key="login_password").set_value("wrong")
        next(b for b in self.at.button if b.label=="Sign in").click().run()
        self.assertEqual(len(self.at.dataframe),0)
        self.assertEqual(len(self.at.get("file_uploader")),0)
        self.assertTrue(self.at.error)
        self.assertEqual(len(self.at.get("component_instance")),0)
