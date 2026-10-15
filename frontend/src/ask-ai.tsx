import {useEffect,useRef,useState} from 'react';
import {rpc,can} from './bridge';
import {answerText} from './answer-text';
import {X,Send,MessageCircle} from 'lucide-react';
export type AIContext={table:string;row:(string|number|null)[];column:string};
type Evidence={citation:string;table:string;matched_records:number;result_rows:number;shown_rows:number;query:unknown;records:Record<string,unknown>[]};
type Message={role:'user'|'assistant';text:string;evidence?:Evidence[]};
type Status={configured:boolean;version:string;model:string;filename:string;tables:number};
const chats=new Map<string,Message[]>();
let chatsVersion='';
export default function AskAI({context,close}:{context?:AIContext;close?:()=>void}){
 const chatKey=JSON.stringify(context??null),[messages,setMessages]=useState<Message[]>(chats.get(chatKey)||[]),[question,setQuestion]=useState(''),[consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[status,setStatus]=useState<Status|null>(null),[error,setError]=useState('');
 const end=useRef<HTMLDivElement>(null),input=useRef<HTMLTextAreaElement>(null);
 useEffect(()=>{let live=true;rpc('ai_status').then(result=>{if(live){if(chatsVersion!==result.version){chats.clear();chatsVersion=result.version;setMessages([])}setStatus(result)}}).catch(e=>{if(live)setError(String(e.message||e))});return()=>{live=false}},[]);
 useEffect(()=>{end.current?.scrollIntoView({block:'nearest'})},[messages,busy]);
 useEffect(()=>{const changed=()=>{setMessages([]);chats.clear();setError('Workbook updated. Start a new question using the current data.');rpc('ai_status').then(setStatus).catch(e=>setError(String(e.message||e)))};window.addEventListener('stock-data-updated',changed);return()=>window.removeEventListener('stock-data-updated',changed)},[]);
 useEffect(()=>{input.current?.focus()},[status]);
 async function send(){if(!question.trim()||busy||!consent||!status?.configured)return;const q=question.trim();setBusy(true);setError('');try{const result=await rpc('ask_ai',{question:q,context:context??null,version:status.version,consent});const next=[...messages,{role:'user' as const,text:q},{role:'assistant' as const,text:result.answer,evidence:result.evidence}].slice(-12);setMessages(next);chats.set(chatKey,next);while(chats.size>10)chats.delete(chats.keys().next().value!);setQuestion('')}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 return <section className={'aichat'+(close?' aiwindow':'')} role={close?'dialog':undefined} aria-label={context?'Ask AI about selected value':'Ask AI'} onKeyDown={e=>{if(e.key==='Escape'&&close){e.stopPropagation();close()}}}>
  <div className="aiheading"><div><h2><MessageCircle size={19}/> Ask AI</h2><p>{context?context.table+' · '+context.column:'Questions about your loaded workbook'}</p></div>{close&&<button className="secondary" onClick={close} aria-label="Close Ask AI"><X size={18}/></button>}</div>
  {context&&<details className="aicontext"><summary>Selected record · {context.column}</summary><p>{context.row.map(v=>String(v??'—')).join(' · ')}</p></details>}
  <p className="ainote">{status?status.filename+' · '+status.model:'Checking Gemini settings…'} · Answers use the saved snapshot. Verify AI explanations against the calculations and source records below each answer.</p>
  {status&&!status.configured&&<div className="error">Add GEMINI_API_KEY in Streamlit Secrets, save and reboot. Optional: ASK_AI_MODEL = "gemini-3.5-flash-lite".</div>}
  {status?.tables===0&&<p className="error">Upload a workbook before asking questions.</p>}
  <label className="aiconsent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> Allow sending questions and relevant loaded records to Google Gemini</label>
  <div className="aimessages" aria-live="polite">{!messages.length&&<div className="aiwelcome"><strong>Explore the data in your own words</strong><p>{context?'Ask what this value means, or compare this record with other loaded tables.':'Try “Which materials have zero stock?” or “Show the largest pending quantities in forecast product totals.”'}</p><small>Table headings, a small sample, query results and recent chat are shared after consent. Answers cannot establish production feasibility without the necessary data.</small></div>}{messages.map((m,i)=><article className={'aimessage '+m.role} key={i}><strong>{m.role==='user'?'You':'AI assistant'}</strong><div className="aitext">{m.role==='assistant'?answerText(m.text):m.text}</div>{m.evidence?.map(e=><details className="aievidence" key={e.citation}><summary>[{e.citation}] {e.table} · {e.matched_records.toLocaleString()} matching records</summary><p>Showing {e.shown_rows} of {e.result_rows} result rows. Calculations include all matching records. Row references belong to this workbook snapshot.</p><pre>{JSON.stringify(e.query,null,2)}</pre><div className="aievidencetable"><table><thead><tr>{Object.keys(e.records[0]||{}).map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{e.records.map((r,j)=><tr key={j}>{Object.entries(r).map(([k,v])=><td key={k}>{String(v??'—')}</td>)}</tr>)}</tbody></table></div></details>)}</article>)}{busy&&<p role="status">Checking loaded records and preparing an answer…</p>}<div ref={end}/></div>
  {error&&<p className="error" role="alert">{error}</p>}
  <form className="aicomposer" onSubmit={e=>{e.preventDefault();send()}}><textarea ref={input} aria-label="Question for Ask AI" placeholder="Ask a question about the loaded data…" maxLength={2000} rows={2} value={question} onChange={e=>setQuestion(e.target.value)} disabled={busy||!status?.configured||!can('use_tools')} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}}}/><button className="primary" type="submit" disabled={busy||!consent||!question.trim()||!status?.configured||!status.tables}><Send size={16}/> Ask</button></form>
  <button className="textbutton" disabled={busy} onClick={async()=>{setBusy(true);try{await rpc('ai_clear',{context:context??null,version:status?.version});setMessages([]);chats.delete(chatKey);setError('')}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}}>Clear chat</button>
 </section>
}
