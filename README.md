# Stock & Planning — Streamlit

A Streamlit Cloud version of the Stock & Planning workspace, with username/password sign-in, one configured administrator, and administrator-created viewer accounts.

## Deploy on Streamlit Community Cloud

1. Open https://share.streamlit.io and create an app from `thakorakash04-cell/Stock-Planning`.
2. Select branch `main`, entry point **`app.py`**, and **Python 3.12** in Advanced settings.
3. Create a persistent PostgreSQL database (for example, Supabase or Neon). For Community Cloud, use a provider connection/pooler reachable over IPv4. Copy the PostgreSQL connection string, with SSL enabled.
4. In Advanced settings → Secrets, paste the three settings from `secrets.example.toml` and replace **every placeholder**. Use your own admin username (for example `thakorakash04-cell`) and a unique password of at least 12 characters. Do not commit the actual secrets to GitHub.
5. Deploy. Sign in with the admin username/password you configured.
6. Open **Upload workbook**, upload your refreshed `Master File.xlsx`, and press **Validate and replace shared data**.
7. Open **Manage users** to create viewer usernames and passwords. Share those credentials privately, along with the Streamlit URL.

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
| Download/export data files through the app | No | No |

User creation, password resets, account changes, data reads and data writes are authorized server-side. Passwords are stored as salted PBKDF2-SHA256 hashes with 600,000 iterations. Five failed attempts lock an account for 15 minutes. Sessions are checked against the database on every interaction and expire after 30 minutes idle or eight hours total. Disabling or resetting a viewer revokes their existing sessions.

Streamlit's `client.disableDataExport = true` removes built-in CSV export and clipboard copying for read-only dataframes. Static serving is disabled and this app supplies no download buttons or raw-file links. This controls application export features; authorized users can still photograph/screenshoot the screen or capture data their browser receives. No website can make visible data impossible to copy. Do not give viewers GitHub/Streamlit/database owner credentials.

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
- Use **Filters, columns and totals** for text/numeric/value filters, hiding/unhiding fields and optional sums. Use the dataframe toolbar for full screen. Table preferences remain within the current Streamlit session.
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

Automated checks cover password authentication/lockout, admin/viewer write restrictions, disabled-session revocation, persistent saved data, workbook extraction and forecast aggregation, Source.Name segment filtering, and Streamlit login/role UI rendering. PostgreSQL behavior requires a real deployment connection; local automated storage tests use SQLite with the same schema/authorization layer.
