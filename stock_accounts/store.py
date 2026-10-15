"""Persistent accounts, administrator-granted capabilities and privacy-safe audit events."""
from __future__ import annotations
import base64, contextlib, gzip, hashlib, hmac, json, os, re, sqlite3, time, uuid
from dataclasses import dataclass

ITERATIONS = 600_000
DEFAULT_PERMISSIONS = {"download": False, "update_data": False, "use_tools": True}
class AccessDenied(PermissionError):
    pass
@dataclass(frozen=True)
class Actor:
    username: str
    version: int
    session_id: str = ""

def normalize_username(value):
    value=value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.@+-]{2,63}",value):
        raise ValueError("Username must have 3–64 letters, numbers or . _ @ + - characters.")
    return value

def password_record(password):
    if len(password)<12:raise ValueError("Use a password of at least 12 characters.")
    salt=os.urandom(16).hex()
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
    return salt,digest

def password_matches(password,salt,expected):
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
    return hmac.compare_digest(digest,expected)

def permissions_for(row):
    if row["role"]=="admin":return {key:True for key in DEFAULT_PERMISSIONS}
    return {**DEFAULT_PERMISSIONS,**json.loads(row["permissions"] or "{}")}

class Store:
    def __init__(self,url):
        if not url.startswith(("postgresql://","postgres://","sqlite:///")):
            raise ValueError("DATABASE_URL must be PostgreSQL, or sqlite:/// for local testing.")
        self.url,self.sqlite=url,url.startswith("sqlite:///")
        with self.transaction() as db:
            self.run(db,"""CREATE TABLE IF NOT EXISTS accounts (
                username TEXT PRIMARY KEY,salt TEXT NOT NULL,password_hash TEXT NOT NULL,
                role TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,session_version INTEGER NOT NULL DEFAULT 1,
                failed_attempts INTEGER NOT NULL DEFAULT 0,locked_until DOUBLE PRECISION NOT NULL DEFAULT 0,
                created_at DOUBLE PRECISION NOT NULL)""")
            columns={"permissions":"TEXT NOT NULL DEFAULT '{}'", "bootstrap_salt":"TEXT", "bootstrap_hash":"TEXT",
                     "last_login_at":"DOUBLE PRECISION", "last_access_at":"DOUBLE PRECISION"}
            existing={r["name"] for r in self.run(db,"PRAGMA table_info(accounts)").fetchall()} if self.sqlite else set()
            for name,kind in columns.items():
                if self.sqlite:
                    if name not in existing:self.run(db,f"ALTER TABLE accounts ADD COLUMN {name} {kind}")
                else:self.run(db,f"ALTER TABLE accounts ADD COLUMN IF NOT EXISTS {name} {kind}")
            self.run(db,"""CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY,payload TEXT NOT NULL,filename TEXT NOT NULL,version TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,updated_at DOUBLE PRECISION NOT NULL)""")
            self.run(db,"""CREATE TABLE IF NOT EXISTS access_log (
                id TEXT PRIMARY KEY,occurred_at DOUBLE PRECISION NOT NULL,username TEXT NOT NULL,
                action TEXT NOT NULL,resource TEXT NOT NULL,session_id TEXT NOT NULL,details TEXT NOT NULL)""")
            self.run(db,"CREATE INDEX IF NOT EXISTS access_log_user_time ON access_log(username,occurred_at)")
    @contextlib.contextmanager
    def transaction(self):
        if self.sqlite:
            db=sqlite3.connect(self.url[len("sqlite:///"):],timeout=20);db.row_factory=sqlite3.Row
            db.execute("PRAGMA busy_timeout=20000");db.execute("BEGIN IMMEDIATE")
        else:
            import psycopg
            from psycopg.rows import dict_row
            db=psycopg.connect(self.url,row_factory=dict_row,connect_timeout=15)
        try:yield db;db.commit()
        except Exception:db.rollback();raise
        finally:db.close()
    def run(self,db,sql,args=()):
        return db.execute(sql if self.sqlite else sql.replace("?","%s"),args)
    def _log(self,db,username,action,resource="",session_id="",details=None):
        self.run(db,"INSERT INTO access_log(id,occurred_at,username,action,resource,session_id,details) VALUES(?,?,?,?,?,?,?)",
                 (uuid.uuid4().hex,time.time(),username,action,str(resource)[:200],session_id,json.dumps(details or {},sort_keys=True)))
    def bootstrap_admin(self,username,password):
        username=normalize_username(username)
        with self.transaction() as db:
            row=self.run(db,"SELECT * FROM accounts WHERE username=?",(username,)).fetchone()
            if row and row["role"]!="admin":raise ValueError("The configured administrator ID belongs to a viewer.")
            self.run(db,"UPDATE accounts SET active=0,session_version=session_version+1 WHERE role='admin' AND username<>? AND active=1",(username,))
            if row:
                # Track the configured secret separately, so an in-app admin password
                # change survives cache clears/restarts. A changed secret is recovery.
                salt=row["bootstrap_salt"] or row["salt"];digest=row["bootstrap_hash"] or row["password_hash"]
                if password_matches(password,salt,digest):
                    if not row["bootstrap_hash"]:self.run(db,"UPDATE accounts SET bootstrap_salt=?,bootstrap_hash=? WHERE username=?",(salt,digest,username))
                    if not row["active"]:self.run(db,"UPDATE accounts SET active=1,session_version=session_version+1 WHERE username=?",(username,))
                    return
            salt,digest=password_record(password)
            if row:
                self.run(db,"UPDATE accounts SET salt=?,password_hash=?,bootstrap_salt=?,bootstrap_hash=?,session_version=session_version+1,active=1,failed_attempts=0,locked_until=0 WHERE username=?",(salt,digest,salt,digest,username))
            else:
                self.run(db,"INSERT INTO accounts(username,salt,password_hash,bootstrap_salt,bootstrap_hash,role,created_at) VALUES(?,?,?,?,?,?,?)",(username,salt,digest,salt,digest,"admin",time.time()))
            self._log(db,username,"admin_secret_changed" if row else "admin_created")
    def login(self,username,password):
        try:username=normalize_username(username)
        except ValueError:username="invalid_username"
        with self.transaction() as db:
            row=self.run(db,"SELECT * FROM accounts WHERE username=?"+("" if self.sqlite else " FOR UPDATE"),(username,)).fetchone()
            if not row:
                password_matches(password,"00"*16,"00"*32);self._log(db,username,"login_failed");return None
            if row["locked_until"]>time.time():self._log(db,username,"login_locked");return None
            if not password_matches(password,row["salt"],row["password_hash"]) or not row["active"]:
                attempts=row["failed_attempts"]+1
                self.run(db,"UPDATE accounts SET failed_attempts=?,locked_until=? WHERE username=?",(attempts,time.time()+900 if attempts>=5 else 0,username))
                self._log(db,username,"login_failed");return None
            self.run(db,"UPDATE accounts SET failed_attempts=0,locked_until=0,last_login_at=?,last_access_at=? WHERE username=?",(time.time(),time.time(),username))
            actor=Actor(username,row["session_version"],uuid.uuid4().hex)
            self._log(db,username,"login_success",session_id=actor.session_id);return actor
    def require(self,db,actor,admin=False,permission=None):
        if not isinstance(actor,Actor):raise AccessDenied("Sign in required.")
        row=self.run(db,"SELECT * FROM accounts WHERE username=?",(actor.username,)).fetchone()
        if not row or not row["active"] or row["session_version"]!=actor.version:raise AccessDenied("This session has expired. Please sign in again.")
        if admin and row["role"]!="admin":raise AccessDenied("Administrator access required.")
        result={key:row[key] for key in ("username","role","active","session_version")};result["permissions"]=permissions_for(row)
        if permission and not result["permissions"].get(permission,False):raise AccessDenied("Your administrator has not granted this permission.")
        return result
    def require_permission(self,actor,permission):
        with self.transaction() as db:return self.require(db,actor,permission=permission)
    def identity(self,actor):
        with self.transaction() as db:return self.require(db,actor)
    def users(self,actor):
        with self.transaction() as db:
            self.require(db,actor,admin=True)
            rows=self.run(db,"SELECT username,role,active,created_at,last_login_at,last_access_at,permissions FROM accounts ORDER BY username").fetchall()
            return [{**dict(r),"permissions":permissions_for(r)} for r in rows]
    def create_viewer(self,actor,username,password):
        username=normalize_username(username)
        with self.transaction() as db:
            self.require(db,actor,admin=True)
            if self.run(db,"SELECT username FROM accounts WHERE username=?",(username,)).fetchone():raise ValueError("That username already exists.")
            salt,digest=password_record(password)
            self.run(db,"INSERT INTO accounts(username,salt,password_hash,role,created_at) VALUES(?,?,?,?,?)",(username,salt,digest,"viewer",time.time()))
            self._log(db,actor.username,"user_created",username,actor.session_id)
    def update_viewer(self,actor,username,active=None,password=None):
        with self.transaction() as db:
            self.require(db,actor,admin=True)
            row=self.run(db,"SELECT role FROM accounts WHERE username=?",(username,)).fetchone()
            if not row or row["role"]!="viewer":raise ValueError("Select a viewer account. Use Change password for your own password.")
            if active is not None:
                self.run(db,"UPDATE accounts SET active=?,session_version=session_version+1 WHERE username=?",(int(active),username))
                self._log(db,actor.username,"user_enabled" if active else "user_disabled",username,actor.session_id)
            if password is not None:
                salt,digest=password_record(password)
                self.run(db,"UPDATE accounts SET salt=?,password_hash=?,session_version=session_version+1,failed_attempts=0,locked_until=0 WHERE username=?",(salt,digest,username))
                self._log(db,actor.username,"password_reset",username,actor.session_id)
    def update_permissions(self,actor,username,permissions):
        if not isinstance(permissions,dict) or any(k not in DEFAULT_PERMISSIONS or type(v) is not bool for k,v in permissions.items()):raise ValueError("Invalid permissions.")
        with self.transaction() as db:
            self.require(db,actor,admin=True)
            row=self.run(db,"SELECT role,permissions FROM accounts WHERE username=?",(username,)).fetchone()
            if not row or row["role"]!="viewer":raise ValueError("Choose a viewer account.")
            values={**DEFAULT_PERMISSIONS,**json.loads(row["permissions"] or "{}"),**permissions}
            self.run(db,"UPDATE accounts SET permissions=?,session_version=session_version+1 WHERE username=?",(json.dumps(values),username))
            self._log(db,actor.username,"permissions_changed",username,actor.session_id,values)
    def change_password(self,actor,current_password,new_password):
        error=None
        with self.transaction() as db:
            self.require(db,actor)
            row=self.run(db,"SELECT * FROM accounts WHERE username=?"+("" if self.sqlite else " FOR UPDATE"),(actor.username,)).fetchone()
            if row["locked_until"]>time.time():error="Account temporarily locked. Please try later."
            elif not password_matches(current_password,row["salt"],row["password_hash"]):
                attempts=row["failed_attempts"]+1
                self.run(db,"UPDATE accounts SET failed_attempts=?,locked_until=? WHERE username=?",(attempts,time.time()+900 if attempts>=5 else 0,actor.username))
                error="Current password is incorrect."
            elif current_password==new_password:error="Choose a different new password."
            else:
                salt,digest=password_record(new_password)
                self.run(db,"UPDATE accounts SET salt=?,password_hash=?,session_version=session_version+1,failed_attempts=0,locked_until=0 WHERE username=?",(salt,digest,actor.username))
                self._log(db,actor.username,"password_changed",actor.username,actor.session_id)
            if error:self._log(db,actor.username,"password_change_failed",session_id=actor.session_id)
        if error:raise ValueError(error)
    def record_access(self,actor,resource):
        with self.transaction() as db:
            self.require(db,actor)
            prior=self.run(db,"SELECT occurred_at FROM access_log WHERE username=? AND session_id=? AND action='view' AND resource=? ORDER BY occurred_at DESC LIMIT 1",(actor.username,actor.session_id,str(resource)[:200])).fetchone()
            if not prior or time.time()-prior["occurred_at"]>=300:
                self._log(db,actor.username,"view",resource,actor.session_id)
                self.run(db,"UPDATE accounts SET last_access_at=? WHERE username=?",(time.time(),actor.username))
    def log_event(self,actor,action,resource=""):
        if action not in ("logout","session_expired","export","tool_use"):raise ValueError("Invalid event.")
        with self.transaction() as db:
            self.require(db,actor,permission="download" if action=="export" else None)
            self._log(db,actor.username,action,resource,actor.session_id)
    def access_log(self,actor,username=None,limit=500):
        with self.transaction() as db:
            self.require(db,actor,admin=True)
            sql="SELECT occurred_at,username,action,resource,session_id,details FROM access_log";args=[]
            if username:sql+=" WHERE username=? OR resource=?";args.extend([username,username])
            sql+=" ORDER BY occurred_at DESC LIMIT ?";args.append(max(1,min(int(limit),1000)))
            return [dict(r) for r in self.run(db,sql,args).fetchall()]
    def save_dataset(self,actor,filename,dataset):
        payload=base64.b64encode(gzip.compress(json.dumps(dataset,allow_nan=False,separators=(",",":")).encode())).decode()
        version=hashlib.sha256(payload.encode()).hexdigest()
        with self.transaction() as db:
            self.require(db,actor,permission="update_data")
            self.run(db,"INSERT INTO datasets(id,payload,filename,version,uploaded_by,updated_at) VALUES('current',?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,filename=excluded.filename,version=excluded.version,uploaded_by=excluded.uploaded_by,updated_at=excluded.updated_at",(payload,filename,version,actor.username,time.time()))
            self._log(db,actor.username,"data_updated",session_id=actor.session_id)
    def get_dataset(self,actor):
        with self.transaction() as db:
            self.require(db,actor);row=self.run(db,"SELECT * FROM datasets WHERE id='current'").fetchone()
        if not row:return None
        result=dict(row);result["data"]=json.loads(gzip.decompress(base64.b64decode(result.pop("payload"))));return result
