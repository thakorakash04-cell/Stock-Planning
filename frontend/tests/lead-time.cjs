const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),{JSDOM}=require('jsdom');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,n)=>m._compile(ts.transpileModule(fs.readFileSync(n,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,n);
const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'https://workspace.test'});
Object.assign(global,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});
const prefs={};
require.cache[require.resolve('../src/bridge.ts')]={id:'bridge',filename:require.resolve('../src/bridge.ts'),loaded:true,exports:{can:()=>false,readViewPreference:key=>prefs[key],saveViewPreference:(key,value)=>prefs[key]=value}};
const React=require('react'),{act}=React,{createRoot}=require('react-dom/client'),root=createRoot(document.getElementById('root')),Lead=require('../src/lead-time.tsx').default;
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 const table={headers:['Component','Component(text)','Batch','Purchase Order','PO Date','Inward Date','QC Date','Use Date','Procurement Lead Time','QC Release Days','FG CONVERSION DATE FROM THE INWARD','Material Type','Source.Name'],rows:[['RM','Raw','001','PO','2026-01-01','2026-01-11','2026-01-13','2026-01-16',10,2,5,'ZRAW','Care']]};
 await act(async()=>{root.render(React.createElement(Lead,{table}));await tick()});
 assert.ok(document.body.textContent.includes('Average procurement: 10 days'));
 assert.ok(!document.body.textContent.includes('Download CSV'),'Viewer has no new broad export right');
 await act(async()=>{document.querySelector('tbody td button').click();await tick()});
 assert.ok(document.querySelector('[aria-label="Lead time record"]'));
 assert.ok(document.body.textContent.includes('Procurement = inward'));
 await act(async()=>root.unmount());console.log('Passed: lead-time sidebar averages, batch details and restricted viewer exports.');
})().catch(async e=>{await act(async()=>root.unmount());console.error(e);process.exitCode=1});
