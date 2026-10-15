from unittest.mock import Mock,patch,MagicMock
import pytest
from stock_accounts.workspace import workspace_payload
from stock_accounts.store import AccessDenied

def test_payload_reuses_same_revision_and_refreshes_on_shared_update():
    store=Mock();actor=Mock(username='viewer',session_id='session')
    store.transaction=MagicMock()
    store.run.return_value.fetchone.return_value={'version':'v1','updated_at':1}
    del store.dataset_revision
    with patch('stock_accounts.workspace.st.session_state',{}),patch('stock_accounts.workspace.ui_payload',side_effect=[('first',[], 'v1'),('next',[],'v2')]) as payload:
        assert workspace_payload(store,actor)[0]=='first'
        assert workspace_payload(store,actor)[0]=='first'
        assert store.get_dataset.call_count==1
        store.run.return_value.fetchone.return_value={'version':'v2','updated_at':2}
        assert workspace_payload(store,actor)[0]=='next'
        assert payload.call_count==2
        store.require.side_effect=AccessDenied('Revoked')
        with pytest.raises(AccessDenied):workspace_payload(store,actor)
