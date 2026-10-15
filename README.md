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
