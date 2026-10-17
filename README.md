# Stock & Planning — Streamlit

A Streamlit Cloud version of the Stock & Planning workspace, with username/password sign-in, one configured administrator, and administrator-created viewer accounts.

## Deploy on Streamlit Community Cloud

1. Open https://share.streamlit.io and create an app from `thakorakash04-cell/Stock-Planning`.
2. Select branch `main`, entry point **`app.py`**, and **Python 3.12** in Advanced settings.
3. Create a persistent PostgreSQL database (for example, Supabase or Neon). For Community Cloud, use a provider connection/pooler reachable over IPv4. Copy the PostgreSQL connection string, with SSL enabled.
4. In Advanced settings → Secrets, paste the three settings from `secrets.example.toml` and replace **every placeholder**. Use your own admin username (for example `thakorakash04-cell`) and a unique password of at least 12 characters. Do not commit the actual secrets to GitHub.
5. Deploy. Sign in with the admin username/password you configured.
6. Use **Update workbook** at the top right of the dashboard and select your refreshed `Master File.xlsx`.
7. Open **Manage users** in the dashboard sidebar to create viewer usernames and passwords. Share those credentials privately, along with the Streamlit URL.

No default password, company workbook, extracted model, or existing user credentials are included in this public repository. Your workbook is uploaded inside the protected app and stored in your PostgreSQL database. The app does not write uploads back to GitHub.

### Required Cloud Secrets

```toml
ADMIN_USERNAME = "thakorakash04-cell"
ADMIN_PASSWORD = "REPLACE_WITH_YOUR_OWN_RANDOM_PASSWORD_AT_LEAST_12_CHARACTERS"
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
```

The app intentionally shows a setup screen until real settings are provided. There is no first-visitor registration or hard-coded admin password. Changing `ADMIN_PASSWORD` in Secrets and restarting the app rotates the admin password and revokes previous admin sessions. Changing `ADMIN_USERNAME` disables the previous admin account.

The database user needs permission to create tables and read/write them. `accounts` and `datasets` are created automatically. Use a database/user dedicated to this app. Preserve your database and its backups when redeploying; deleting it removes accounts and uploaded data.

## Permissions

| Capability | Admin | Viewer |
|---|---:|---:|
| Sign in and view the shared dataset | Yes | Yes |
| Search, filter, hide/unhide columns, show sums, full screen | Yes | Yes |
| Open underlying model tables | Yes | Yes |
| Upload or replace the shared workbook | Yes | No |
| Create, disable, enable, reset viewer accounts | Yes | No |
| Export visible/filtered data through original table controls | Yes | No |

User creation, password resets, account changes, data reads and data writes are authorized server-side. Passwords are stored as salted PBKDF2-SHA256 hashes with 600,000 iterations. Five failed attempts lock an account for 15 minutes. Every server action and the 60-second heartbeat recheck account access. Sessions expire after 30 minutes without interface activity or eight hours total. Disabling or resetting a viewer revokes their existing sessions.

Streamlit's `client.disableDataExport = true` removes built-in CSV export and clipboard copying for read-only dataframes. Static serving is disabled; viewer accounts receive no download controls or raw-file links. The original table export controls are available only to administrators. This controls application export features; authorized users can still photograph/screenshoot the screen or capture data their browser receives. No website can make visible data impossible to copy. Do not give viewers GitHub/Streamlit/database owner credentials.

## Workbook views

The original worksheet layout is expected:

| App view | Workbook source |
|---|---|
| Stock overview | `Summary` |
| BOM cost | `BOM Cost` |
| Sales & transfers | `Sales Data` |
| Production | `Production Data` |
| Forecast planning | `Forecast Planning` |
| Forecast purchasing | `Forecast Need to Order List` |
| Order requirements | `Need to Order Sheet-B.O. PS` |

- Forecast opens with product totals. **Pending = sum of forecast − sum of transfers − current stock once per material.** Monthly details remain available; filtered stock/pending totals use the same rule.
- Purchasing views preserve the named worksheets' saved values, including blank cells, negative balances and the unmatched-component row.
- Segment options come from **Source.Name** in the material/BOM tables. Shared components inherit their parent products' segments; no marketing `Segment` fallback is used. The supplied workbook's five categories are General Wound Care, Advance Wound Care, Ostomy Care, Energy Devices and Designer Cap.
- Select a cell to open a full-width record page. All related embedded tables, columns, components, parent products, batches and periods are available. **Entire workbook** removes the material restriction.
- The original ChatGPT Sites React interface is used directly inside Streamlit: the same seven-item sidebar, light-gray workspace, table headers, per-column filter controls, Columns and Totals menus, grouping, and full-window record screens. Use the table's **Full screen** button at the upper right. Column/total preferences remain per table in the browser.
- The four KPI cards are omitted.

## Excel refresh and embedded models

Refresh All and save in Excel before uploading. The server reads saved worksheet cells with `openpyxl` and extracts embedded Power Pivot tables using `pbixray`. Direct `.xlsx` uploads include the embedded model automatically; the older `.stock.zip` package format is also supported. No Power Query, SAP connection, or DAX refresh runs on the server. Related source records are provided as calculation context, not a new DAX engine.

Uploads are limited to 25 MB, with expanded archive/table bounds. Workbooks with missing required sheets are rejected. A parsing/validation failure leaves the previous shared dataset in place. A workbook without an embedded model can supply summary views, but will have no underlying-model tables.

## Local development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `secrets.example.toml` to `.streamlit/secrets.toml` and provide your own admin credentials. For local testing only, use:

```toml
DATABASE_URL = "sqlite:///stock_planning.db"
```

Then:

```bash
streamlit run app.py
python -m unittest discover -s tests -v
```

Local SQLite is **not durable on Streamlit Cloud**. Cloud deployments should use PostgreSQL. The app displays a warning if SQLite is selected. The checked-in `.streamlit/config.toml` is required; the app fails closed if data export is not disabled.

## Validation

Automated checks cover password authentication/lockout, admin/viewer write restrictions, disabled-session revocation, persistent saved data, workbook extraction and forecast aggregation, Source.Name segment filtering, Streamlit login/role UI rendering, and server-side authorization of component requests. PostgreSQL behavior requires a real deployment connection; local automated storage tests use SQLite with the same schema/authorization layer.


## Frontend source and build

`frontend/src/` contains the original Sites dashboard components, with a small Streamlit message bridge replacing the Sites endpoints. `frontend_dist/` contains the built static component. **Streamlit Cloud does not need Node or an extra build step.** No workbook records or secrets are built into these assets.

For frontend development with Node 22+:

```bash
cd frontend
npm install
npm run check
npm run build
```

Commit both frontend source and the updated `frontend_dist` build. Keep existing Streamlit Secrets and the PostgreSQL database unchanged when updating the UI. Login and account checks remain in Python. Client-side filtering stays responsive; a periodic server heartbeat checks access and refreshes changed datasets.

## Account access controls

See [ACCOUNT_ACCESS.md](ACCOUNT_ACCESS.md) for administrator permissions, persistent access logs and self-service password changes. These controls extend the original viewer-only defaults described above.


## One Zoho Cliq bot for all four apps

See [zoho_bot/README.md](zoho_bot/README.md) for the standalone unified backend, Docker deployment, Zoho Message Handler and account mappings. Streamlit does not need to stay awake for the separately hosted backend to answer.

## Ask AI

See [ASK_AI.md](ASK_AI.md) for the Gemini Secrets setup, data sharing, query evidence and permissions.

## FG planning inside Order requirements

Select an FG material, enter its planning quantity in the displayed unit, and
choose **Add FG**. Add more FG items or edit the quantity rows, then choose
**Calculate need to order**. Results contain only components linked to positive
entered quantities. Editing any quantity clears the previous result until it is
recalculated. Reloading materials or replacing the workbook clears the plan.
Plans are session calculations and do not replace the shared workbook.

The calculation reproduces the master's Power Query `BOM` → `Need to Order
Sheet` logic: multiply each entered FG quantity by `Component quantity`, convert
each BOM-row requirement to Int64 with round-to-even, group by `Component`,
`Component(text)` and `Material Type`, sum requirements, and deduct the minimum
merged available stock and minimum merged on-order stock once per group. The
final need-to-order quantity is converted to Int64. Nulls and negative balances
are preserved. There is no extra division by BOM base quantity, FG-stock
subtraction, or recursive BOM explosion in this PS calculation.

Planning needs an uploaded embedded `BOM` table with the existing merged stock
and on-order columns. An upload containing only saved worksheet summaries cannot
support recalculation. All planning requests recheck account access, and a stale
workbook version must be reloaded before calculation. No Gemini key is needed.

### Viewer downloads from a clicked value

Viewers can download the filtered matched-records table opened by clicking a
worksheet value. The Excel file contains only the displayed columns and matching
rows from that one source table. The server validates the selected worksheet row,
workbook revision, source table, columns and every exported row against the
related material context. This does not grant the broad `download` permission:
main worksheet tables, Entire workbook, ZIP exports and Ask AI exports retain
their existing access rules. Downloads are recorded in the administrator log.

Viewers can also download the **Forecast purchasing** table and the calculated
**Order requirements** material list as Excel, using the current grid filters
and visible columns. These are scoped exceptions; other table export permissions
are unchanged. Planning downloads are checked against the result calculated for
that login session and workbook version, and both downloads are audited.

FG planning inputs, unfinished entries and calculated results stay in memory
when navigating to another worksheet, Ask AI or Insights and returning during
the same login. Signing out, loading a newer workbook, choosing Clear plan or
reloading planning materials starts a new plan. Browser reloads start a new
in-memory view.

## Production workspace

Production now contains four independently collapsible tables: the existing
completed/QC-released worksheet, ongoing orders, batches under QC release, and
shared upcoming production plans.

* **Under QC release:** match material **and batch**, restrict to FG/SFG types,
  require movement 101 and no 321 through the snapshot date, then use the latest
  101 posting date. The window includes the reference month and four preceding
  calendar months. Quantities come from matching production order records;
  unmatched quantities stay blank.
* **Ongoing:** confirmed quantity must equal zero; Basic start date must lie in
  the reference month or preceding month, no later than the snapshot date.
  Expected end date starts from Basic finish date. Expected FG uses median
  positive 321 receiving quantity / order quantity from up to ten completed,
  QC-released batches of the exact same material (same product size). Order
  quantities within ±25% are prioritised; otherwise all sizes for that material
  are used and labelled. SAP's negative 321 QC outflow is excluded to avoid
  cancelling the corresponding positive unrestricted-stock inflow. If no usable
  history exists, no quantity is invented. Estimates remain planning assumptions.
* **Reference date:** the dated header in the first five rows of Production Data
  is captured on workbook upload. Earlier uploads fall back to their upload date
  and show that fallback explicitly. Re-upload the refreshed workbook once to
  capture its worksheet date.
* **Shared changes:** expected FG quantity/end date overrides and upcoming plans
  are stored in `production_shared` in the same persistent database. Viewers
  start with edit access off. Manage users provides separate **Edit ongoing
  production** and **Add/edit upcoming plans** rights. Saves recheck permissions
  and dataset version, detect concurrent edits, and appear in the access log.
  Other users see updates on refresh or the production screen's 60-second poll.
* **Sidebar:** Manage users also controls each viewer's nine section permissions.
  Restricted menus are hidden, their worksheet rows are removed from the UI
  payload, and their view/tool/edit/export requests are denied server-side.
  These control section access; underlying records may still be available in an
  authorised section's drill-down or Ask AI context. Permission changes revoke
  existing sessions, so the viewer signs in again for the new rights.

The three new Production tables each have their own grouping selector and segment
filter. Material-backed rows use the workbook's Source.Name segment mapping.
Upcoming plans infer a segment from an exact material code/product-name match,
or an authorised editor can choose a workbook segment explicitly; unresolved
plans can be found under Unassigned. Batches beginning with a numeric character
are excluded from these three views (existing history remains stored). New
upcoming plans must use a batch that does not start with a digit. All table
pagination layouts keep Previous/Next beside the record count.

### Upcoming material selector and availability

Upcoming plans now offer a searchable FG/SFG catalogue. Selecting a material
loads its code and canonical description; legacy plans can be edited to select
their material. All three new production tables open the existing full-window
source-record drill-down when a value is clicked. Their matched-record downloads
validate the production selection server-side.

Each saved upcoming plan has a Material availability control. Green means every
BOM component is verified as sufficient; red opens shortages or explains why
availability cannot be verified. Required consumption is calculated as planned
FG/SFG quantity / BOM base quantity * component quantity, without premature
integer rounding. Duplicate joined BOM items are removed; distinct consuming
items are summed per component/unit and stock is deducted once. Current stock
includes unrestricted and quality-inspection stock; on-order receipts do not
count. The detail window shows shortages and every BOM calculation, including
base quantity and consumption. Missing/ambiguous BOMs, invalid quantities,
unknown stock and mismatched units never produce a green result. The check uses
one plan against the uploaded snapshot; it does not reserve stock across plans
or recursively explode SFG subassemblies. Plan revision, workbook version and
Production access are checked again before the result is returned.

Production save and availability requests use a separate `plan_id`; the RPC
request `id` is reserved for request/response correlation. New plan IDs are
created by the server. This prevents Invalid plan ID errors and edit/check
requests waiting for a response under the wrong ID.

Upcoming plans are automatically archived when both their resolved material code
and batch match Production Order Details. Matching ignores surrounding spaces
and letter case, never matches on material or batch alone, retains the saved
history/audit trail, and keeps archived plans out of future upcoming lists even
when a later SAP dump omits older orders.

### Shared edits, deletion and IST history

Upcoming plans offer Edit and Delete actions to administrators and viewers with
`edit_upcoming` access. Delete requires confirmation and soft-deletes the shared
plan so it disappears for everyone; it retains the record and history. Delete
rechecks the workbook version, plan revision and permissions to prevent deleting
someone else's intervening edit.

The Edit history tab is readable by users with Production section access. It
shows the latest 500 history events, with username, action, material/batch,
changed field, previous/new values and an IST timestamp. Creating/editing/deleting
plans and automatic production-order matches write history in the same database
transaction as the change. Detailed history starts with this deployment; earlier
before/after values cannot be recovered. Internal timestamps remain absolute
instants; production saved times, history, account logs, upload times and Insights
generation times are explicitly displayed in Asia/Kolkata (IST), independent of
the viewer's browser/server timezone. Date-only planning dates are unchanged.

## Private saved filters and column views

View settings are now saved in `user_view_preferences` under the authenticated
username and a distinct section/table scope. Column filters, visible columns,
totals and sorting survive logouts, future logins and use on another browser.
Sidebar searches, segment selections, grouping and forecast mode are stored per
section; the new production tables keep separate segment/grouping settings.
Drill-down tables also have distinct scopes for each originating section and
source table. Older unowned browser-local settings are not imported into another
user's account.

Changes save automatically after a short debounce, and pending changes flush
before queued navigation/logout requests. Users can clear column filters or use
Reset table view to reset that table's saved view. Saving never changes another
user's preferences or shared workbook data. Preferences survive workbook updates;
only fields available in the current table are applied.

The three new Production tables load by default when Production opens. A new
uploaded workbook automatically reloads their source data, clears stale
availability/detail windows and ignores older in-flight responses. The saved
filters and column views remain intact.

### Lead time & Consumption
The sidebar reproduces the Days Calculation intervals from the supplied reference workbook using the active master model's BOM, Material Document List and Order List. Each material/batch uses its earliest movement date: inward=min(101,102,105,106), QC=321, use=min(261,262). Days are calendar differences; inward-to-use is not final FG release. PO joins include material, avoiding unrelated batches and PO items. Missing or ambiguous dates remain blank. Segment, material type, PO year, inward year, grouping and column views are private saved user settings. Admin controls section access through menu_9 independently of Gemini tools.

Forecast Purchasing preserves all saved quantities and adds **Suggested order by date** for positive need-to-order rows only. This is a timing estimate: outstanding dated FG demand deducts transfers and FG stock once, then standard-BOM component quantity / base quantity × outstanding FG quantity determines monthly requirements, recursively expanding SFG components, as requested. No flattened BOM without SFG is required; saved purchasing quantities are unchanged. Component stock and on-order are deducted once; the first uncovered month starts the need date. Subtract ceil(mean procurement days + max(mean QC days, mean inward-to-use days)). QC is already inside inward-to-use, so it is not added twice. Historical means use non-negative material/batch observations, excluding repeated BOM/PO joins. All on-order is assumed available; scheduled PO delivery dates and working-day calendars are unavailable. Past suggested dates mean overdue. Cyclic or ambiguous alternative BOMs are marked for review. Missing histories or dated BOM links are reported instead of invented dates. Data and dates refresh with the master workbook; filters do not change purchasing calculations. Existing viewer Forecast Purchasing export includes the suggested date. Mail remains unconfigured.
