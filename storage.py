"""Persistent users and data. Authorization is checked at every data operation."""
from __future__ import annotations
import base64, contextlib, gzip, hashlib, hmac, json, os, re, sqlite3, time
from dataclasses import dataclass

ITERATIONS = 600_000
class AccessDenied(PermissionError):
    pass
@dataclass(frozen=True)
class Actor:
    username: str
    version: int

def normalize_username(value):
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.@+-]{2,63}", value):
        raise ValueError("Username must have 3–64 letters, numbers or . _ @ + - characters.")
    return value

def password_record(password):
    if len(password) < 12:
        raise ValueError("Use a password of at least 12 characters.")
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return salt, digest

def password_matches(password, salt, expected):
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return hmac.compare_digest(actual, expected)

class Store:
    def __init__(self, url):
        if not url.startswith(("postgresql://", "postgres://", "sqlite:///")):
            raise ValueError("DATABASE_URL must be PostgreSQL, or sqlite:/// for local testing.")
        self.url, self.sqlite = url, url.startswith("sqlite:///")
        with self.transaction() as db:
            self.run(db, """CREATE TABLE IF NOT EXISTS accounts (
                username TEXT PRIMARY KEY, salt TEXT NOT NULL, password_hash TEXT NOT NULL,
                role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                session_version INTEGER NOT NULL DEFAULT 1,
                failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until DOUBLE PRECISION NOT NULL DEFAULT 0,
                created_at DOUBLE PRECISION NOT NULL)""")
            self.run(db, """CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, filename TEXT NOT NULL,
                version TEXT NOT NULL, uploaded_by TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""")
    @contextlib.contextmanager
    def transaction(self):
        if self.sqlite:
            db = sqlite3.connect(self.url[len("sqlite:///"):], timeout=20)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=20000")
            db.execute("BEGIN IMMEDIATE")
        else:
            import psycopg
            from psycopg.rows import dict_row
            db = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=15)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    def run(self, db, sql, args=()):
        return db.execute(sql if self.sqlite else sql.replace("?", "%s"), args)
    def bootstrap_admin(self, username, password):
        username = normalize_username(username)
        with self.transaction() as db:
            row = self.run(db, "SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
            if row and row["role"] != "admin":
                raise ValueError("The configured admin username is already a viewer; choose a new admin username.")
            self.run(db, "UPDATE accounts SET active=0,session_version=session_version+1 WHERE role='admin' AND username<>? AND active=1", (username,))
            if row and password_matches(password, row["salt"], row["password_hash"]):
                return
            salt, digest = password_record(password)
            if row:
                self.run(db, "UPDATE accounts SET salt=?,password_hash=?,session_version=session_version+1,active=1,failed_attempts=0,locked_until=0 WHERE username=?", (salt,digest,username))
            else:
                self.run(db, "INSERT INTO accounts(username,salt,password_hash,role,created_at) VALUES(?,?,?,?,?)", (username,salt,digest,"admin",time.time()))
    def login(self, username, password):
        try:
            username = normalize_username(username)
        except ValueError:
            username = ""
        with self.transaction() as db:
            suffix = "" if self.sqlite else " FOR UPDATE"
            row = self.run(db, "SELECT * FROM accounts WHERE username=?"+suffix, (username,)).fetchone()
            if not row:
                password_matches(password, "00"*16, "00"*32)
                return None
            if row["locked_until"] > time.time():
                return None
            good = password_matches(password, row["salt"], row["password_hash"])
            if not good or not row["active"]:
                attempts = row["failed_attempts"] + 1
                self.run(db, "UPDATE accounts SET failed_attempts=?,locked_until=? WHERE username=?", (attempts, time.time()+900 if attempts>=5 else 0, username))
                return None
            self.run(db, "UPDATE accounts SET failed_attempts=0,locked_until=0 WHERE username=?", (username,))
            return Actor(username, row["session_version"])
    def require(self, db, actor, admin=False):
        if not isinstance(actor, Actor):
            raise AccessDenied("Sign in required.")
        row = self.run(db, "SELECT username,role,active,session_version FROM accounts WHERE username=?", (actor.username,)).fetchone()
        if not row or not row["active"] or row["session_version"] != actor.version:
            raise AccessDenied("This session has expired. Please sign in again.")
        if admin and row["role"] != "admin":
            raise AccessDenied("Administrator access required.")
        return dict(row)
    def identity(self, actor):
        with self.transaction() as db:
            return self.require(db, actor)
    def users(self, actor):
        with self.transaction() as db:
            self.require(db, actor, admin=True)
            return [dict(r) for r in self.run(db,"SELECT username,role,active,created_at FROM accounts ORDER BY username").fetchall()]
    def create_viewer(self, actor, username, password):
        username=normalize_username(username)
        with self.transaction() as db:
            self.require(db,actor,admin=True)
            if self.run(db,"SELECT username FROM accounts WHERE username=?",(username,)).fetchone():
                raise ValueError("That username already exists.")
            salt,digest=password_record(password)
            self.run(db,"INSERT INTO accounts(username,salt,password_hash,role,created_at) VALUES(?,?,?,?,?)",(username,salt,digest,"viewer",time.time()))
    def update_viewer(self, actor, username, active=None, password=None):
        with self.transaction() as db:
            self.require(db,actor,admin=True)
            row=self.run(db,"SELECT role FROM accounts WHERE username=?",(username,)).fetchone()
            if not row or row["role"]!="viewer":
                raise ValueError("Only viewer accounts can be changed here. Change the admin password in Streamlit Secrets.")
            if active is not None:
                self.run(db,"UPDATE accounts SET active=?,session_version=session_version+1 WHERE username=?",(int(active),username))
            if password is not None:
                salt,digest=password_record(password)
                self.run(db,"UPDATE accounts SET salt=?,password_hash=?,session_version=session_version+1,failed_attempts=0,locked_until=0 WHERE username=?",(salt,digest,username))
    def save_dataset(self, actor, filename, dataset):
        payload=base64.b64encode(gzip.compress(json.dumps(dataset,allow_nan=False,separators=(",",":")).encode())).decode()
        version=hashlib.sha256(payload.encode()).hexdigest()
        with self.transaction() as db:
            self.require(db,actor,admin=True)
            self.run(db,"INSERT INTO datasets(id,payload,filename,version,uploaded_by,updated_at) VALUES('current',?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,filename=excluded.filename,version=excluded.version,uploaded_by=excluded.uploaded_by,updated_at=excluded.updated_at",(payload,filename,version,actor.username,time.time()))
    def get_dataset(self, actor):
        with self.transaction() as db:
            self.require(db,actor)
            row=self.run(db,"SELECT * FROM datasets WHERE id='current'").fetchone()
        if not row:
            return None
        result=dict(row)
        result["data"]=json.loads(gzip.decompress(base64.b64decode(result.pop("payload"))))
        return result
