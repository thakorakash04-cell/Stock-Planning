# Ask AI setup and behavior

Add these top-level values in Streamlit Cloud → Manage app → Settings → Secrets, alongside the existing database and administrator settings. Save and reboot after editing secrets.

```toml
GEMINI_API_KEY = "your-private-key"
ASK_AI_MODEL = "gemini-3.5-flash-lite"
```

The model setting is optional. `GOOGLE_API_KEY` and `[gemini] api_key` are also accepted, with `GEMINI_API_KEY` taking priority. Never put a real key in GitHub. API usage, billing and quota belong to the Google project. Missing keys disable chat without disabling tables.

Open **Ask AI**, enable sharing with Google for the session, and ask about loaded data. The prompt shares table names/headings, one bounded sample row per table, the question, recent conversation and at most three query results (20 rows each). It does not send account credentials or access logs. Results may contain confidential workbook or regulatory data; enable sharing only if authorised to send that information to Google.

Gemini proposes allowlisted table filters, grouping and calculations. Python validates and executes them against the complete loaded table before limiting displayed results. No model-generated SQL, Python or shell commands are executed. The answer includes expandable query evidence, matching-record counts and source row references within the current snapshot. Missing numeric values remain unknown, not zero. AI explanations can still be wrong; verify the supplied evidence. This is read-only and does not change uploaded files or run external regulatory searches.

Stock Planning includes seven saved worksheet views, a calculated forecast product-totals table, and uploaded embedded model tables when available. Use product totals for forecast questions; monthly stock is repeated and must not be summed. Source tables may contain different units, parent/component relationships and overlapping segments. Joins and new multi-level production-feasibility calculations are not supported; ask about existing saved values or individual tables. The Ask AI icon beside any table cell opens a compact chat window with a server-verified selected record. Existing record-detail clicks still work.

Regulatory Research uses the current results of the three research tabs. Run a search first; a new result snapshot clears chat. FDA clearances, CDSCO classifications and registration listings are distinct sources, and a search subset is not a complete registry or a legal/clinical conclusion. The chat tab shows which result tables are available. Interactive browser column filters do not narrow the assistant's dataset: name the desired filters in your question.

Both chats use the existing `use_tools` permission and recheck it before each request and before returning an answer. Administrators can manage this permission in Manage users. Download permission remains separate; Ask AI provides bounded evidence, not a new export endpoint. Chat history is session-private, capped, and cleared on sign-out or data changes. Access logs record only a generic Ask AI tool event, not questions, answers or keys.

Requests may take two Gemini calls. No background AI calls occur until a question is submitted. Provider errors distinguish missing/rejected keys, denied access, unavailable models, rate limits and provider outages. Automated tests use mocked provider responses; they do not establish live project quota or model accuracy.
