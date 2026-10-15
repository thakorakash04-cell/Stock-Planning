# One Zoho Cliq bot for four repositories

This standalone FastAPI service calls the existing Stock-Planning, BOE, MedDevice and AWC code directly. Streamlit UI and logins are unchanged. One backend deployment and one Cliq bot are required. Repository changes alone do not create a live Zoho bot.

## 1. Deploy the backend

Use the **Stock-Planning** repository. In a Docker-capable host choose repository root as the build context and `zoho_bot/Dockerfile` as the Dockerfile. Alternatively use the Render blueprint at `zoho_bot/render.yaml` (select that blueprint path). The Docker image fetches the other three public repositories at the exact commits in `source-pins.json`; no GitHub token is needed. Research data makes this a large build. Select sufficient build disk, memory and request timeouts; broad CDSCO scans can be slow.

The start command and `/health` check are already provided. Configure HTTPS. Set these **private host environment variables**, not GitHub files:

- `CLIQ_GATEWAY_KEY`: random secret of at least 32 characters. Generate locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Share only with the restricted Zoho handler.
- `CLIQ_ORGANIZATION_ID`: your Zoho organization ID.
- `DATABASE_URL`: the same PostgreSQL connection already used by the Streamlit apps.
- If databases differ, set `STOCK_DATABASE_URL`, `BOE_DATABASE_URL`, `RESEARCH_DATABASE_URL`, `AWC_DATABASE_URL` individually.
- `CLIQ_USERS_JSON`: admin-approved mappings, described below. Start with `{}`.

The backend never creates an admin or resets a password. Sign in to each dashboard once to initialize its tables and accounts. Stock and BOE read the most recently saved datasets from their databases. AWC catalogue reads its repository workbook; the clinical engine uses its existing seed catalogue. Research searches its pinned repository CDSCO snapshots and live FDA API.

Free hosts may suspend idle services; no uptime promise is added. Choose a host/plan supporting always-on execution if immediate replies 24/7 are required. External AI and Zoho limits also apply.

## 2. Create ONE Zoho bot

In Zoho Cliq open **Bots & Tools / Developer Platform → Bots → Create bot**. Name it `Workspace Assistant`. Edit its **Message Handler**, paste `message_handler.deluge`, and replace:

- `https://YOUR-BACKEND-HOST/chat` with the HTTPS backend URL plus `/chat`.
- `REPLACE_WITH_GATEWAY_SECRET` with exactly `CLIQ_GATEWAY_KEY`.

Restrict handler editing to trusted administrators. The handler supplies the sender's actual `user.id`, `user.organization_id` and chat type; never take these from typed message text. Use a direct bot conversation. Channels, threads and group chats are rejected. No outbound Zoho token is required because the handler returns the reply synchronously.

Official references: [message handlers](https://www.zoho.com/cliq/help/platform/bot-messagehandler.html), [user object](https://www.zoho.com/cliq/help/platform/cliq-objects/user-object.html), [chat object](https://www.zoho.com/cliq/help/platform/cliq-objects/chat-object.html).

## 3. Grant account access

Send `/whoami` directly to the bot. It returns the sender's Cliq ID and organization ID. If the organization check rejects the request, get the organization ID from your Cliq administrator and correct the host setting first.

Create the intended user in each app's **Manage users**, and leave/grant **Use tools**. In the **private backend console** run:

```sh
python admin_mapping.py YOUR_CLIQ_USER_ID YOUR_APP_USERNAME
```

The script prints a mapping of active, permitted accounts and their current session versions (no password or connection string). Save it as `CLIQ_USERS_JSON` in the backend settings. Merge additional users into the same outer JSON object. If usernames differ per app, combine the appropriate entries manually. Example structure:

```json
{"123456":{"stock":{"username":"aakash","version":1},"boe":{"username":"aakash","version":1},"research":{"username":"aakash","version":1},"awc":{"username":"aakash","version":1}}}
```

Use actual versions from the script, not necessarily `1`. Missing workspace entries deny access. Account disabling, permission changes and password changes invalidate mappings immediately through the existing session version checks. To re-enable bot access after a legitimate change, rerun the private mapping script and update the environment. Removing a mapping also revokes bot access. Every successful request records an app access/tool-use event, visible to admins in existing logs; message and assessment contents are not logged by this service. The rate limit is 15 requests per minute per sender, with one worker.

## 4. Test the bot

```
/stock tables
/stock Summary | catheter
/boe latest
/research fda photodynamic
/research risk laser
/research manufacturer catheter
/awc catalogue foam
```

The stock command takes the exact returned table name and an optional `|` text filter. All terms must match somewhere in a row. Replies show at most 20 matching records; full analysis remains in the dashboard. This does not rerun DAX or recompute stock measures.

BOE example (uses the existing repository calculator, including its fixed SWS/IGST assumptions; verify applicability before business use):

```
/boe calculate {"header":{"exchange_rate":80,"invoice_value_fc":100,"freight_inr":0},"items":[{"material_name":"Example","quantity":10,"unit_price_fc":10,"bcd_rate_percent":10}]}
```

Calculations are not saved and uploads/downloads/account changes are not supported through chat.

AWC: catalogue lookup is informational. `/awc schema` describes the assessment fields. `/awc assess` requires every `WoundAssessment` field explicitly, plus `clinician_confirmed:true`. It calls the existing triage and contraindication engine; it does not infer findings from chat or images. Use the protected dashboard for its three-photo workflow and full clinical review. Responses can be shortened to fit chat; always use the dashboard for the complete care plan.

## 5. Conversational AI answers and follow-ups

Set these private Render environment variables, then Save and deploy:

- `GEMINI_API_KEY`: your Gemini API key.
- `GEMINI_MODEL`: a model ID enabled for your account.
- `AI_DATA_SHARING_ENABLED=true`: explicit administrator opt-in to send questions, recent question/tool-plan context, table schemas and selected permitted app records to Google's Gemini API. This changes the previous question-only routing behavior. Do not enable unless your organization permits this processing. No raw photos, database passwords, account hashes or full workbooks are sent by the assistant.

Users can ask naturally: “Which products need ordering?”, then “Only Ostomy”, then “Explain that shortage”. The assistant validates a structured table plan, calculates filters, grouping, sorting and numeric sums locally across all matching rows, retrieves a preview of up to 20 records and asks Gemini to explain that evidence. It will clarify when a table lacks the columns needed for the question. It does not execute generated Python, SQL, DAX, or workbook instructions. It cannot invent root causes, perform unsupported joins, or access another user's permissions.

BOE can explain latest saved results; new computations still use confirmed structured inputs. FDA/CDSCO uses the existing search sources. AWC can explain catalogue entries; patient-specific clinical findings are never inferred from chat. Supported general concepts can be explained as general guidance, without claiming a live source search.

Follow-up memory is private to an organization/user and current permission/session versions, expires after 30 minutes and retains only four question/tool-plan turns. It is temporary process memory: sleeping/restarting Render clears it. No previous answer or result rows are cached for later use: app evidence is retrieved fresh and permissions rechecked before disclosure and before replying. `reset`, `clear` or `new conversation` clears the history. No chat contents are written to application access logs. A disabled account or changed permission/session version invalidates the old context.

Explicit commands work without AI. If the model/key or sharing opt-in is missing, natural questions explain the missing setting. AI provider calls have short timeouts; provider outages or complex searches can still require a retry. The current handler is synchronous and does not deliver delayed push replies.

## Maintenance and verification

One deployment serves all four repositories. Changes to an upstream app are not automatically used: update its commit in the Dockerfile and `source-pins.json`, run tests and rebuild. Setup pointers in the other repositories refer back here. For local testing, put the four checkouts beside one another, set `REPOS_ROOT` to their parent directory and run:

```sh
python -m pytest zoho_bot/tests -q
```

The tests use SQLite fixtures and mocked FDA responses. Live Zoho handler execution, host provisioning, PostgreSQL connectivity, Gemini and external research calls must be checked after setting your private credentials. No application secrets or company workbook are committed.
