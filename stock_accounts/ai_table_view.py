"""Validate a displayed AI result projection against the server-generated query."""
import json,math
from collections import Counter

def project(records,event):
    if 'headers' not in event:return records
    headers=event.get('headers');rows=event.get('rows')
    available={h for record in records for h in record}
    if not isinstance(headers,list) or not headers or any(not isinstance(h,str) or h not in available for h in headers) or len(set(headers))!=len(headers):
        raise ValueError('Invalid AI result columns.')
    if not isinstance(rows,list) or len(rows)*len(headers)>2_000_000 or len(json.dumps(rows))>25_000_000:
        raise ValueError('Narrow the AI result before downloading.')
    def cell(v):return ('true' if v else 'false') if isinstance(v,bool) else v
    def fingerprint(values):
        if any(isinstance(v,float) and not math.isfinite(v) for v in values):raise ValueError('Invalid AI result number.')
        return tuple(values)
    allowed=Counter(fingerprint([cell(r.get(h)) for h in headers]) for r in records)
    result=[]
    for row in rows:
        if not isinstance(row,list) or len(row)!=len(headers) or any(isinstance(v,bool) or v is not None and not isinstance(v,(str,int,float)) for v in row):raise ValueError('Invalid AI result row.')
        token=fingerprint(row)
        if allowed[token]<=0:raise ValueError('Download only rows from this AI result.')
        allowed[token]-=1;result.append(dict(zip(headers,row)))
    return result
