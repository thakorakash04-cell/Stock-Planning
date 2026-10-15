# Accounts, permissions and access logs — Stock & Planning

## Administrator

Open **Manage users**. Select a viewer, choose **Access rights**, then **Save access rights**. Only the administrator can create accounts, edit permissions, reset another user's password, or enable/disable users. An active account provides basic workspace access. Applicable additional rights: Download/export data; upload and replace the shared workbook.

A permission change revokes that user's existing sessions. They must sign in again for their new access. Granting upload/update rights allows replacement of shared data, not account administration. Existing viewer defaults are preserved: no download or shared-data updates; existing AWC/research tool access remains enabled. Administrators always retain full access.

The user list displays last login, last access, status and permissions. **Access log** shows up to 500 recent matching events; filter by an exact username to include actions by that user and account changes targeting that user. Use Refresh access log for current data. Logs use UTC and persist in PostgreSQL across Streamlit restarts. Events include successful/failed/locked logins, workspace/result-table access, sign-out/expiry, permission/account changes, password changes/resets, uploads and exports. Repeated access to the same resource/session is combined within five minutes. A view event means the workspace or results were served, not that every row was read. New logs begin with this deployment; historical sessions cannot be reconstructed. Passwords, assessment contents, query contents and uploaded file contents are not logged. Account administration and logs remain administrator-only even when a viewer is granted more rights.

## Every signed-in user

Open **Change password**, enter the current password and a new password of at least 12 characters, and confirm it. A successful change signs out all sessions, including the current one. Sign in again with the new password. Users can only change their own passwords this way; the administrator can reset viewer passwords under Manage users.

The administrator can also change their own password on-screen. That change survives restarts and unchanged Streamlit Secrets. To recover access through Secrets, set `ADMIN_PASSWORD` to a NEW value different from the configured bootstrap secret and reboot. Do not set Secrets back to an old value unintentionally; changing that secret is an explicit administrator password reset.

## Deployment

No new Secrets are required. Keep `DATABASE_URL`, `ADMIN_USERNAME` and `ADMIN_PASSWORD`. Database tables are migrated automatically without replacing existing accounts or datasets. Each app keeps separate accounts/logs, even if the PostgreSQL database is shared. Reboot each Streamlit app once after the code updates. Native toolbar export is disabled; app export buttons are permission-gated. Visible data can still be copied or captured.

Account navigation is dispatched directly instead of waiting for the dashboard RPC queue. Native account pages render in the same server request with normal scrolling. The live app imports its isolated stock_accounts package so cached legacy storage/exact_ui/account helpers cannot be mixed with new entry-point code. Reboot once after deployment; no Secrets or database changes are needed.
