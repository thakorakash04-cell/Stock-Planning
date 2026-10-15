import {selectDetails} from './detail-rules';
import {segmentIndex,filterSegments} from './segments';
import type {ModelTable} from './model-data';
type Args={version?:string;data?:Record<string,any>|null;tables?:ModelTable[]|null;user:string;role:string;permissions?:Record<string,boolean>;response?:{id:string;body:any;error?:string}};
let state:Args|null=null,parentOrigin='*',lastHeight=0,lastActivity=Date.now()/1000;
for(const name of ['pointerdown','keydown','touchstart'])window.addEventListener(name,()=>{lastActivity=Date.now()/1000},{passive:true});
function fitFrame(){let height=window.screen.availHeight-140;try{height=window.parent.innerHeight}catch{}height=Math.max(240,height);if(height!==lastHeight){lastHeight=height;send('streamlit:setFrameHeight',{height})}}
const waiting=new Map<string,{resolve:(v:any)=>void;reject:(v:Error)=>void}>();
let queue:Promise<any>=Promise.resolve();let readyListener:((args:Args)=>void)|null=null;
const send=(type:string,extra:Record<string,unknown>)=>window.parent.postMessage({isStreamlitMessage:true,type,...extra},parentOrigin);
export const isAdmin=()=>state?.role==='admin';
export const can=(permission:string)=>isAdmin()||state?.permissions?.[permission]===true;
export async function authorizeExport(){try{await rpc('export');return true}catch(e){alert(e instanceof Error?e.message:String(e));return false}}
export function rpc(action:string,payload:Record<string,unknown>={}):Promise<any>{const work=()=>new Promise((resolve,reject)=>{const id=crypto.randomUUID();waiting.set(id,{resolve,reject});send('streamlit:setComponentValue',{value:{id,action,activity:lastActivity,...payload},dataType:'json'});setTimeout(()=>{if(waiting.has(id)){waiting.delete(id);reject(new Error('Request timed out. Please retry.'))}},120000)});const result=queue.then(work);queue=result.catch(()=>{});return result;}
export async function uploadWorkbook(file:File){const bytes=new Uint8Array(await file.arrayBuffer());let raw='';for(let i=0;i<bytes.length;i+=32768)raw+=String.fromCharCode(...bytes.subarray(i,i+32768));return rpc('upload',{filename:file.name,content:btoa(raw)})}
export function startBridge(onReady:(args:Args)=>void){
 readyListener=onReady;
 window.addEventListener('message',event=>{
  if(event.source!==window.parent||event.data?.type!=='streamlit:render')return;
  parentOrigin=event.origin;
  const args=event.data.args as Args;if(!args?.user)return;
  const changed=Boolean(args.data)&&(!state?.data||args.version!==state.version);
  state={...state,...args,data:changed?args.data:state?.data,tables:changed?args.tables:state?.tables};
  if(changed)window.dispatchEvent(new Event('stock-data-updated'));
  if(args.response){const pending=waiting.get(args.response.id);if(pending){waiting.delete(args.response.id);args.response.error?pending.reject(new Error(args.response.error)):pending.resolve(args.response.body)}}
  if(state?.data)readyListener?.(state);
  fitFrame();
 });
 window.addEventListener('resize',fitFrame);
 send('streamlit:componentReady',{apiVersion:1});
 setInterval(()=>{if(state?.data&&!waiting.size)rpc('heartbeat').catch(()=>{})},60000);
}
const originalFetch=window.fetch.bind(window);
window.fetch=async(input:RequestInfo|URL,init?:RequestInit)=>{const path=typeof input==='string'?input:input instanceof URL?input.pathname:input.url;if(path==='/api/data'){if(!state?.data)return Response.json({error:'Loading data'},{status:503});return Response.json(state.data)}if(path==='/api/details'){if(!state?.tables?.length)return Response.json({available:false,message:'Upload a workbook containing an embedded Power Pivot model to see its source records.'});const body=JSON.parse(String(init?.body||'{}'));const index=segmentIndex(state.tables);const sets=filterSegments(selectDetails(state.tables,body.tab,body.row,body.col,body.scope==='all'),index,body.segment||'all');if(body.exportTables)return Response.json({tables:sets});const table=sets.find(t=>t.name===body.table)||sets.find(t=>t.rows.length)||sets[0];const q=String(body.q||'').toLowerCase();const rows=table?.rows.filter(r=>!q||r.some(v=>String(v??'').toLowerCase().includes(q)))||[];return Response.json({available:true,tables:sets.map(t=>({name:t.name,count:t.rows.length})),segments:[...new Set(Object.values(index).flat())].sort(),table:table?.name,headers:table?.headers||[],rows:body.exportAll?rows:rows.slice((body.page||0)*50,(body.page||0)*50+50),total:rows.length,totalRelated:sets.reduce((n,t)=>n+t.rows.length,0)})}return originalFetch(input,init)};
