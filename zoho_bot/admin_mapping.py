"""Run only in the private backend console: python admin_mapping.py CLIQ_ID APP_USERNAME."""
import json
import sys
from service import SOURCES, store, account_module

if len(sys.argv) != 3:
    raise SystemExit('Usage: python admin_mapping.py CLIQ_USER_ID APP_USERNAME')
user_id, username = sys.argv[1:]
output = {}
for workspace in SOURCES:
    storage = store(workspace)
    tables = {'stock':'accounts','boe':'boe_accounts','research':'meddevice_accounts','awc':'awc_accounts'}
    with storage.transaction() as db:
        row = storage.run(db, 'SELECT username,session_version,active,role,permissions FROM '+tables[workspace]+' WHERE username=?', (username,)).fetchone()
        if row and row['active'] and account_module(workspace).permissions_for(row).get('use_tools'):
            output[workspace]={'username':row['username'],'version':row['session_version']}
print(json.dumps({user_id:output}))
