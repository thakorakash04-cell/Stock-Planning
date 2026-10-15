"""One private Cliq bot; source repositories are pinned by the Docker build."""
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
from functools import lru_cache

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(os.getenv('REPOS_ROOT', '/repos'))
SOURCES = {
    'stock': ('Stock-Planning', 'stock_accounts/store.py'),
    'boe': ('boe-cost-calculator', 'boe_accounts/store.py'),
    'research': ('meddevice-research-platform', 'meddevice_accounts/store.py'),
    'awc': ('awc-platform', 'workspace_store.py'),
}
HELP = '''One bot, four workspaces:
/stock tables
/stock Summary | material code or text
/boe latest
/boe calculate {"header": {...}, "items": [...]}
/research fda laser
/research risk laser
/research manufacturer catheter
/research importer catheter
/awc catalogue foam
/awc assess {clinician-confirmed assessment JSON}
Use /whoami for your Cliq ID. Results are limited to 20 records. Use the dashboard for full tables and photos.'''
app = FastAPI(title='Unified Cliq workspace bot', docs_url=None, redoc_url=None, openapi_url=None)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=4)
def account_module(workspace):
    repo, filename = SOURCES[workspace]
    return load('cliq_accounts_' + workspace, ROOT / repo / filename)


@lru_cache(maxsize=4)
def store(workspace):
    url = os.getenv(workspace.upper() + '_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not url:
        raise HTTPException(503, 'Workspace database is not configured.')
    return account_module(workspace).Store(url)


def authorize(workspace, user_id):
    try:
        mapping = json.loads(os.getenv('CLIQ_USERS_JSON', '{}'))[user_id][workspace]
        module = account_module(workspace)
        actor = module.Actor(mapping['username'], int(mapping['version']), 'cliq:' + user_id)
        storage = store(workspace)
        storage.require_permission(actor, 'use_tools')
        storage.record_access(actor, 'zoho_bot:' + workspace)
        return storage, actor
    except HTTPException:
        raise
    except (KeyError, ValueError, TypeError, PermissionError):
        raise HTTPException(403, 'Access unavailable. Ask the app admin to map or renew your Cliq access.') from None


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    user_id: str = Field(min_length=1, max_length=100)
    organization_id: str = Field(min_length=1, max_length=100)
    chat_type: str = Field(min_length=1, max_length=30)


LOCK = threading.Lock()
COUNTS = {}


def authentication(x_api_key: str = Header(default='')):
    expected = os.getenv('CLIQ_GATEWAY_KEY', '')
    if len(expected) < 32:
        raise HTTPException(503, 'Bot gateway secret is not configured.')
    if not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(401, 'Invalid gateway credentials.')


def limit(user):
    now = time.monotonic()
    with LOCK:
        for key in list(COUNTS):
            if now - COUNTS[key][0] > 60:
                del COUNTS[key]
        start, count = COUNTS.get(user, (now, 0))
        if count >= 15 or (user not in COUNTS and len(COUNTS) >= 10000):
            raise HTTPException(429, 'Too many requests. Retry in one minute.')
        COUNTS[user] = (start, count + 1)


def text_value(value):
    # Keep workbook values from injecting Cliq Markdown links or mentions.
    return re.sub(r'[\x00-\x1f\[\]()*`@]', ' ', str(value))[:180]


def rows_reply(title, headers, rows, total):
    lines = [title + f' — {total} matching records; showing up to 20.']
    for row in rows[:20]:
        lines.append(' | '.join(f'{text_value(h)}: {text_value(v)}' for h, v in zip(headers, row)))
    return '\n\n'.join(lines)[:6500]


def stock_query(storage, actor, query):
    saved = storage.get_dataset(actor)
    if not saved:
        return 'No workbook uploaded. Upload one through Stock-Planning first.'
    tables = saved['data'].get('sheets', []) + saved['data'].get('tables', [])
    if query.strip().lower() == 'tables':
        return 'Available tables: ' + ', '.join(t['name'] for t in tables)
    table, _, term = query.partition('|')
    table = table.strip()
    found = next((t for t in tables if t['name'].casefold() == table.casefold()), None)
    if not found:
        return 'Choose an exact table name using /stock tables. Example: /stock Summary | catheter'
    words = term.lower().split()
    rows = [r for r in found['rows'] if all(w in ' '.join(map(str, r)).lower() for w in words)]
    return rows_reply(f"{found['name']} (saved workbook; updated {saved['updated_at']})", found['headers'], rows, len(rows))


def boe_query(storage, actor, query):
    if query == 'latest':
        saved = storage.get_dataset(actor)
        if not saved:
            return 'No saved BOE calculation. Run and save a calculation in the dashboard first.'
        return 'Latest saved BOE calculation:\n' + json.dumps(saved['data'].get('results', {}), ensure_ascii=False)[:6200]
    if not query.startswith('calculate '):
        return 'Use /boe latest or /boe calculate {"header": {...}, "items": [...]}. See setup guide for a complete example.'
    data = json.loads(query[len('calculate '):])
    if set(data) != {'header', 'items'} or not isinstance(data['header'], dict) or not isinstance(data['items'], list) or not 1 <= len(data['items']) <= 20:
        raise ValueError('Provide header and 1–20 items.')
    for item in [data['header']] + data['items']:
        if not isinstance(item, dict):
            raise ValueError('Each item must be an object.')
        for key, value in item.items():
            if key != 'material_name' and (not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1e12):
                raise ValueError('Use finite, nonnegative numeric amounts.')
    if not data['header'].get('exchange_rate') or not data['header'].get('invoice_value_fc'):
        raise ValueError('Positive exchange_rate and invoice_value_fc are required.')
    if any(not i.get('quantity') for i in data['items']):
        raise ValueError('Every item needs positive quantity.')
    engine = load('cliq_boe_engine', ROOT / SOURCES['boe'][0] / 'calculation_engine.py')
    result = engine.compute_boe_costing(data['header'], data['items'])
    return 'BOE calculation using repository rates (not saved):\n' + json.dumps(result, ensure_ascii=False)[:6200]


def research_query(query):
    command, _, term = query.partition(' ')
    if command not in {'fda', 'risk', 'manufacturer', 'importer'} or not term.strip():
        return 'Use /research fda|risk|manufacturer|importer followed by device keywords.'
    if command == 'fda':
        words = re.findall(r'\w+', term)
        if not words:
            raise ValueError('Enter device keywords.')
        response = requests.get('https://api.fda.gov/device/510k.json', params={
            'search': ' AND '.join(f'device_name:"{w}"' for w in words), 'limit': 20, 'sort': 'decision_date:desc'}, timeout=(3, 12))
        if response.status_code == 404:
            return 'No matching FDA 510(k) records.'
        response.raise_for_status()
        payload = response.json()
        keys = ['k_number', 'device_name', 'applicant', 'decision_date']
        return rows_reply('FDA 510(k) clearances; keyword matches', keys, [[r.get(k, '') for k in keys] for r in payload.get('results', [])], payload['meta']['results']['total'])
    import pyarrow.parquet as pq
    filename = 'cdsco_combined_risk.parquet' if command == 'risk' else 'cdsco_approved_devices.parquet'
    search_cols = ['medical_device_name', 'intended_use', 'device_category'] if command == 'risk' else ['devicename', 'brandname', 'modelname', 'str_intended_use']
    keys = ['medical_device_name', 'risk_classification_under_mdr_2017', 'device_category'] if command == 'risk' else ['devicename', 'address', 'str_licence_no', 'classname', 'role']
    rows, total = [], 0
    with pq.ParquetFile(ROOT / SOURCES['research'][0] / filename) as parquet:
        for batch in parquet.iter_batches(batch_size=4096):
            frame = batch.to_pandas()
            if command != 'risk':
                frame = frame[frame['role'].astype(str).str.casefold() == command.casefold()]
            cols = [c for c in search_cols if c in frame]
            corpus = frame[cols].fillna('').astype(str).agg(' '.join, axis=1).str.casefold()
            mask = corpus.map(lambda text: all(w in text for w in term.casefold().split()))
            selected = frame.loc[mask]
            total += len(selected)
            rows.extend(selected.reindex(columns=keys).fillna('').values.tolist()[:max(0, 20-len(rows))])
    return rows_reply('CDSCO saved source records; keyword matches', keys, rows, total)


@lru_cache(maxsize=1)
def awc_modules():
    sys.path.insert(0, str(ROOT / SOURCES['awc'][0]))
    from data.awc_data_manager import AWCDataManager
    manager = AWCDataManager(str(ROOT / SOURCES['awc'][0] / 'data/AWCare_Merged.xlsx'))
    return manager


def awc_query(query):
    if query.startswith('catalogue '):
        frame = awc_modules().df_main
        words = query[len('catalogue '):].casefold().split()
        corpus = frame.astype(str).agg(' '.join, axis=1).str.casefold()
        frame = frame[corpus.map(lambda text: all(w in text for w in words))]
        keys = [k for k in ['Product Name', 'Material of Construction/ Components', 'Indications (AWC)', 'Contraindications'] if k in frame]
        return rows_reply('AWC catalogue lookup; not a treatment recommendation', keys, frame[keys].values.tolist(), len(frame))
    if query.startswith('assess '):
        awc_modules()
        from core.models import WoundAssessment
        from core.rules_engine import process_clinical_assessment
        data = json.loads(query[len('assess '):])
        if data.pop('clinician_confirmed', False) is not True:
            raise ValueError('Clinician confirmation is required.')
        # Do not silently fill clinical safety findings with optimistic model defaults.
        required = set(WoundAssessment.model_fields)
        if set(data) != required:
            raise ValueError('Supply every assessment field explicitly. See /awc schema.')
        assessment = WoundAssessment.model_validate(data)
        tissue = sum(getattr(assessment, k) for k in ('granulation_percent','slough_percent','eschar_percent','epithelial_percent'))
        if tissue != 100:
            raise ValueError('Confirmed tissue percentages must total 100.')
        result = process_clinical_assessment(assessment)
        return 'Clinical decision support; clinician review required. No photos accepted in chat.\n' + result.model_dump_json()[:6000]
    if query == 'schema':
        awc_modules()
        from core.models import WoundAssessment
        schema = WoundAssessment.model_json_schema()
        template = {field: None for field in WoundAssessment.model_fields}
        template['clinician_confirmed'] = False
        enums = {name: value.get('enum') for name, value in schema.get('$defs', {}).items() if 'enum' in value}
        return 'Replace every null with a clinician-confirmed value. Set clinician_confirmed:true only after review.\nTemplate: ' + json.dumps(template) + '\nAllowed enum values: ' + json.dumps(enums)
    return 'Use /awc catalogue <product keywords>. Clinicians: /awc schema and /awc assess <complete confirmed JSON>. Use the AWC dashboard for photos.'


def route(message):
    token, _, query = message.strip().partition(' ')
    token = token.lower().lstrip('/')
    if token in SOURCES:
        return token, query.strip()
    # Optional AI sees the question only. It cannot execute tools, SQL or change access.
    key, model = os.getenv('GEMINI_API_KEY'), os.getenv('GEMINI_MODEL')
    if not key or not model:
        return None, ''
    response = requests.post('https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent', headers={'x-goog-api-key': key}, json={
        'systemInstruction': {'parts': [{'text': 'Route to a single read-only command. Return JSON {"workspace":"stock|boe|research|awc|help", "query":"..."}. Stock: tables or exact table name | keyword. BOE: latest only. Research: fda/risk/manufacturer/importer device keywords. AWC: catalogue product keyword only; never infer clinical findings. Unknown request: help. Do not invent financial values or table names.'}]},
        'contents': [{'parts': [{'text': message}]}],
        'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0}}, timeout=(3, 12))
    response.raise_for_status()
    result = json.loads(response.json()['candidates'][0]['content']['parts'][0]['text'])
    workspace, query = result.get('workspace'), result.get('query', '')
    if workspace not in SOURCES or not isinstance(query, str) or len(query) > 1000:
        return None, ''
    if workspace == 'boe' and query != 'latest' or workspace == 'awc' and not query.startswith('catalogue '):
        return None, ''
    return workspace, query


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.post('/chat', dependencies=[Depends(authentication)])
def chat(body: ChatInput):
    if body.organization_id != os.getenv('CLIQ_ORGANIZATION_ID'):
        raise HTTPException(403, 'Organization is not allowed.')
    if body.chat_type != 'bot':
        raise HTTPException(403, 'Use a direct conversation with this bot; channels and group chats are disabled.')
    limit(body.user_id)
    message = body.message.strip()
    if message.lower() == '/whoami':
        return {'text': 'Cliq user ID: ' + body.user_id + '\nOrganization ID: ' + body.organization_id}
    if message.lower() in {'help', '/help', 'hi', 'hello'}:
        return {'text': HELP}
    try:
        if body.user_id not in json.loads(os.getenv('CLIQ_USERS_JSON', '{}')):
            raise HTTPException(403, 'Ask the administrator to grant your Cliq ID access.')
        conversation = load('cliq_conversation', Path(__file__).with_name('conversation.py')) if 'cliq_conversation' not in sys.modules else sys.modules['cliq_conversation']
        if not conversation.explicit(message):
            return conversation.reply(body, sys.modules[__name__])
        workspace, query = route(message)
        if not workspace:
            return {'text': HELP}
        storage, actor = authorize(workspace, body.user_id)
        if workspace == 'stock':
            result = stock_query(storage, actor, query)
        elif workspace == 'boe':
            result = boe_query(storage, actor, query)
        elif workspace == 'research':
            result = research_query(query)
        else:
            result = awc_query(query)
        storage.log_event(actor, 'tool_use', 'zoho_bot:' + workspace)
        return {'text': result}
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError):
        return {'text': 'Invalid command data. Check the complete JSON fields and numeric values in the setup guide.'}
    except Exception:
        # Do not expose DB credentials, provider response bodies or clinical data.
        raise HTTPException(503, 'Workspace service unavailable. Ask the administrator to check deployment and database settings.') from None


@app.exception_handler(HTTPException)
async def error_reply(request: Request, error: HTTPException):
    return JSONResponse(status_code=error.status_code, content={'text': str(error.detail)})
