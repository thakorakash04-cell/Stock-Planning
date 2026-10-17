"""Private, durable view settings scoped to the authenticated user and table."""
import json,re,time

def schema(store,db):
    store.run(db,"""CREATE TABLE IF NOT EXISTS user_view_preferences (
        username TEXT NOT NULL,scope TEXT NOT NULL,payload TEXT NOT NULL,updated_at DOUBLE PRECISION NOT NULL,
        PRIMARY KEY(username,scope))""")

def read(store,actor):
    with store.transaction() as db:
        store.require(db,actor);schema(store,db)
        return {r['scope']:json.loads(r['payload']) for r in store.run(db,'SELECT scope,payload FROM user_view_preferences WHERE username=?',(actor.username,)).fetchall()}

def save(store,actor,event):
    scope=event.get('scope');value=event.get('value')
    if not isinstance(scope,str) or not 1<=len(scope)<=240 or not re.fullmatch(r'[\w :./()—–&+\-]+',scope):raise ValueError('Invalid view settings scope.')
    if not isinstance(value,dict):raise ValueError('Invalid view settings.')
    try:payload=json.dumps(value,allow_nan=False)
    except (TypeError,ValueError):raise ValueError('Invalid view settings.')
    if len(payload)>100_000:raise ValueError('Too many saved filter values. Narrow the selection.')
    with store.transaction() as db:
        store.require(db,actor);schema(store,db)
        store.run(db,'INSERT INTO user_view_preferences(username,scope,payload,updated_at) VALUES(?,?,?,?) ON CONFLICT(username,scope) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',(actor.username,scope,payload,time.time()))
    return {'ok':True}
