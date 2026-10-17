"""Immutable before/after history, committed atomically with production changes."""
import json,time,uuid
from .access import require_menu
from .clock import display


def schema(store,db):
    store.run(db,"""CREATE TABLE IF NOT EXISTS production_history (
        id TEXT PRIMARY KEY,plan_id TEXT NOT NULL,kind TEXT NOT NULL,action TEXT NOT NULL,
        username TEXT NOT NULL,occurred_at DOUBLE PRECISION NOT NULL,
        before_data TEXT NOT NULL,after_data TEXT NOT NULL)""")
    store.run(db,'CREATE INDEX IF NOT EXISTS production_history_plan_time ON production_history(plan_id,occurred_at)')


def record(store,db,plan_id,kind,action,username,before,after):
    store.run(db,'INSERT INTO production_history(id,plan_id,kind,action,username,occurred_at,before_data,after_data) VALUES(?,?,?,?,?,?,?,?)',
              (uuid.uuid4().hex,plan_id,kind,action,username,time.time(),json.dumps(before or {}),json.dumps(after or {})))


def read(store,actor,event):
    require_menu(store,actor,3)
    plan=event.get('plan_id')
    if plan is not None and (not isinstance(plan,str) or len(plan)>64):raise ValueError('Invalid history selection.')
    with store.transaction() as db:
        store.require(db,actor);schema(store,db)
        sql='SELECT * FROM production_history';args=[]
        if plan:sql+=' WHERE plan_id=?';args.append(plan)
        sql+=' ORDER BY occurred_at DESC,id DESC LIMIT 500'
        events=[dict(r) for r in store.run(db,sql,args).fetchall()]
    labels={'product':'Product','materialCode':'Material code','description':'Description','batch':'Batch','quantity':'Quantity','startDate':'Start date','endDate':'End date','segment':'Segment'}
    rows=[]
    for item in events:
        before=json.loads(item['before_data']);after=json.loads(item['after_data']);context=after or before
        fields=[k for k in sorted(set(before)|set(after)) if before.get(k)!=after.get(k)]
        if not fields:fields=['No field changes']
        for key in fields:
            rows.append([display(item['occurred_at']),item['username'],item['kind'],item['action'],context.get('materialCode') or context.get('product'),context.get('batch'),labels.get(key,key),before.get(key),after.get(key),item['plan_id']])
    return {'headers':['Date & Time (IST)','Username','Plan Type','Action','Material / Product','Batch','Changed Field','Previous Value','New Value','Plan ID'],'rows':rows,'events':len(events),'limit':500}
