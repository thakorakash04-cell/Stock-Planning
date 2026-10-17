"""Menu and production edit capabilities, independent of broad export rights."""
MENU_LABELS=['Stock overview','BOM cost','Sales & transfers','Production','Forecast planning','Forecast purchasing','Order requirements','Ask AI','Insights & Graphs','Lead time & Consumption']
PERMISSION_DEFAULTS={'download':False,'update_data':False,'use_tools':True,
                     'edit_production':False,'edit_upcoming':False,
                     **{'menu_'+str(i):True for i in range(10)}}

def allowed(identity,index):
    return identity['role']=='admin' or identity['permissions'].get('menu_'+str(index),True) and (index not in (7,8) or identity['permissions'].get('use_tools',False))

def require_menu(store,actor,index):
    from .store import AccessDenied
    if not allowed(store.identity(actor),index):raise AccessDenied('Your administrator has disabled access to this section.')
