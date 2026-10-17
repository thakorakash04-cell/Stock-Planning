const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),{JSDOM}=require('jsdom');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,n)=>m._compile(ts.transpileModule(fs.readFileSync(n,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,n);
const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'https://workspace.test'});
Object.assign(global,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});
const pending=[],prefs={'production:groups':{ongoing:2,qc:-1,upcoming:-1}};
require.cache[require.resolve('../src/bridge.ts')]={id:'bridge',filename:require.resolve('../src/bridge.ts'),loaded:true,exports:{can:()=>false,readViewPreference:key=>prefs[key],saveViewPreference:(key,value)=>prefs[key]=value,rpc:action=>action==='production_status'?new Promise(resolve=>pending.push(resolve)):Promise.resolve({})}};
const React=require('react'),{act}=React,{createRoot}=require('react-dom/client'),root=createRoot(document.getElementById('root')),Production=require('../src/production.tsx').default;
const tick=()=>new Promise(r=>setImmediate(r));
function report(code){return {version:code,referenceDate:'2026-10-17',ongoingHeaders:['Order','Type','Material'],ongoing:[{id:code,revision:0,row:[1,'ZFGS',code]}],qc:{headers:['Material'],rows:[[code]]},upcomingHeaders:['Material'],upcoming:[{id:code,revision:1,row:[code]}]}}
(async()=>{
 await act(async()=>{root.render(React.createElement(Production,{revision:'v1'},'Completed'));await tick()});assert.equal(pending.length,1,'New production tables load automatically');
 await act(async()=>{root.render(React.createElement(Production,{revision:'v2'},'Completed'));await tick()});assert.equal(pending.length,2,'New workbook version automatically reloads all production sources');
 await act(async()=>{pending[1](report('NEW'));await tick()});assert.ok(document.body.textContent.includes('NEW'));
 await act(async()=>{pending[0](report('OLD'));await tick()});assert.ok(!document.body.textContent.includes('OLD'),'Slow old-file response cannot overwrite new data');
 assert.equal(document.querySelector('[aria-label="Group ongoing records"]').value,'2','User grouping survives new workbook');
 assert.equal(document.querySelectorAll('.production-section[open]').length,4,'Production windows start expanded');
 await act(async()=>root.unmount());console.log('Passed: predefined production loading, automatic version refresh, stale response protection and retained view settings.');
})().catch(async e=>{await act(async()=>root.unmount());console.error(e);process.exitCode=1});
