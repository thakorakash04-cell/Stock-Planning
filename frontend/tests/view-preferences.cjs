const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),{JSDOM}=require('jsdom');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,n)=>m._compile(ts.transpileModule(fs.readFileSync(n,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,n);
const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'https://workspace.test'});
Object.assign(global,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,localStorage:dom.window.localStorage,Event:dom.window.Event,IS_REACT_ACT_ENVIRONMENT:true});
window.fetch=global.fetch;const sent=[];window.postMessage=p=>sent.push(p);global.setTimeout=()=>1;global.setInterval=()=>1;
const bridge=require('../src/bridge.ts');bridge.startBridge(()=>{});
const React=require('react'),{act}=React,{createRoot}=require('react-dom/client'),root=createRoot(document.getElementById('root')),Grid=require('../src/data-grid.tsx').default;
const tick=()=>new Promise(r=>setImmediate(r));let user='alice',prefs={};
function receive(response){window.dispatchEvent(new window.MessageEvent('message',{source:window.parent,origin:'https://workspace.test',data:{type:'streamlit:render',args:{user,role:'viewer',version:'v1',data:{filename:'test'},tables:[],preferences:prefs,response}}}))}
const rows=[['A',5],['B',6]],headers=['Material','Qty'];
async function render(scope){await act(async()=>{root.render(React.createElement(Grid,{headers,rows,storageKey:scope}));await tick()})}
(async()=>{
 prefs={'grid:main:A':{filters:{Material:{text:'A'}},hidden:['Qty'],sums:[],sort:{column:'',dir:1}}};receive();await render('main:A');
 assert.equal(document.querySelector('[aria-label="Filter text for Material"]').value,'A');assert.equal(document.querySelector('[aria-label="Filter text for Qty"]'),null);
 await act(async()=>{const el=document.querySelector('[aria-label="Filter text for Material"]');Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(el,'B');el.dispatchEvent(new window.Event('input',{bubbles:true}));await tick();bridge.flushPreferences();await tick()});
 const save=sent.find(p=>p.value?.action==='preferences_save').value;assert.equal(save.scope,'grid:main:A');assert.equal(save.value.filters.Material.text,'B');prefs={...prefs,[save.scope]:save.value};
 await act(async()=>{receive({id:save.id,body:{ok:true}});await tick()});
 await render('main:B');assert.equal(document.querySelector('[aria-label="Filter text for Material"]').value,'');assert.ok(document.querySelector('[aria-label="Filter text for Qty"]'));
 await render('main:A');assert.equal(document.querySelector('[aria-label="Filter text for Material"]').value,'B');
 user='bob';prefs={};await act(async()=>{receive();await tick()});assert.equal(document.querySelector('[aria-label="Filter text for Material"]').value,'');assert.ok(document.querySelector('[aria-label="Filter text for Qty"]'));
 user='alice';prefs={'grid:main:A':save.value};await act(async()=>{receive();await tick()});assert.equal(document.querySelector('[aria-label="Filter text for Material"]').value,'B');
 await act(async()=>{[...document.querySelectorAll('button')].find(b=>b.textContent==='Reset table view').click();await tick()});assert.equal(document.querySelector('[aria-label="Filter text for Material"]').value,'');assert.ok(document.querySelector('[aria-label="Filter text for Qty"]'));
 const count=sent.filter(p=>p.value?.action==='preferences_save').length;
 user='bob';prefs={};await act(async()=>{receive();bridge.flushPreferences();await tick()});
 assert.equal(sent.filter(p=>p.value?.action==='preferences_save').length,count,'Unsaved settings must never be written under the next user');
 await act(async()=>root.unmount());console.log('Passed: private user views, independent table scopes, restored filters/columns and explicit reset.');
})().catch(async e=>{await act(async()=>root.unmount());console.error(e);process.exitCode=1});
