const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),{JSDOM}=require('jsdom');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,n)=>m._compile(ts.transpileModule(fs.readFileSync(n,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,n);
const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'https://workspace.test'});
Object.assign(global,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});
let edit=false;const calls=[];
const report={segments:['Wound'],segmentMap:{A:['Wound']},version:'v1',referenceDate:'2026-10-10',referenceBasis:'Worksheet date',ongoingHeaders:['Order','Type','Material','Description','Batch','Qty','Start','Expected end','Expected FG','Basis','Saved by','Saved at'],ongoing:[{id:'order1',revision:0,row:[1,'ZFGS','A','Item','B1',100,'2026-10-01','2026-10-25',85,'History',null,null]}],qc:{headers:['Material','Batch','Latest 101'],rows:[['A','B2','2026-10-04']]},upcomingHeaders:['Product','Description','Batch','Qty','Start','End'],upcoming:[]};
require.cache[require.resolve('../src/bridge.ts')]={id:'bridge',filename:require.resolve('../src/bridge.ts'),loaded:true,exports:{can:p=>edit&&p.startsWith('edit_'),isAdmin:()=>false,rpc:async(action,payload)=>{calls.push({action,payload});return report}}};
const React=require('react'),{act}=React,{createRoot}=require('react-dom/client'),root=createRoot(document.getElementById('root')),Production=require('../src/production.tsx').default;
const tick=()=>new Promise(r=>setImmediate(r));
async function change(key,value){await act(async()=>{const el=document.querySelector('[aria-label="'+key+'"]');Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new window.Event('input',{bubbles:true}));await tick()})}
(async()=>{
 await act(async()=>{root.render(React.createElement(Production,{revision:'v1'},React.createElement('p',null,'Completed table')));await tick()});
 assert.equal(document.querySelectorAll('.production-section').length,4);assert.ok([...document.querySelectorAll('.production-section')].every(d=>d.tagName==='DETAILS'));
 assert.ok(!document.body.textContent.includes('Add upcoming batch'));
 assert.equal(document.querySelectorAll('.production-section select[aria-label^="Group "]').length,3,'Each new table has a grouping selector');
 await act(async()=>{const select=document.querySelector('[aria-label="Group ongoing records"]');select.value='2';select.dispatchEvent(new window.Event('change',{bubbles:true}));await tick()});
 assert.ok(document.querySelector('.production-section:nth-of-type(2) .group'),'Grouping displays collapsible record groups');
 assert.equal(document.querySelectorAll('select[aria-label^="Filter "][aria-label$=" by segment"]').length,3,'Each new table has a segment filter');
 await act(async()=>{const select=document.querySelector('[aria-label="Filter qc by segment"]');select.value='unassigned';select.dispatchEvent(new window.Event('change',{bubbles:true}));await tick()});
 assert.ok(document.querySelector('.production-section:nth-of-type(3)').textContent.includes('No records match these filters.'));


 edit=true;await act(async()=>{root.render(React.createElement(Production,{revision:'v1'},'Completed table'));await tick()});
 await act(async()=>{[...document.querySelectorAll('button')].find(b=>b.textContent==='Add upcoming batch').click();await tick()});
 for(const [k,v] of Object.entries({product:'Product A',description:'Size A',batch:'NEXT',quantity:'100',startDate:'2026-11-01',endDate:'2026-11-10'}))await change(k,v);
 await act(async()=>{document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));await tick()});
 const saved=calls.find(c=>c.action==='production_save');assert.equal(saved.payload.value.quantity,100);assert.equal(saved.payload.version,'v1');assert.equal(saved.payload.kind,'upcoming');
 await act(async()=>{[...document.querySelectorAll('button')].find(b=>b.textContent.startsWith('Edit order')).click();await tick()});
 assert.equal(document.querySelectorAll('.production-form input').length,2,'Only expected quantity and end date may be edited');
 await act(async()=>{[...document.querySelectorAll('button')].find(b=>b.textContent==='Cancel').click();await tick()});
 const Dashboard=require('../src/dashboard.tsx').default;
 global.fetch=async()=>Response.json({accessibleTabs:[3],filename:'master.xlsx',updatedAt:'2026-10-10',sheets:Array.from({length:7},(_,i)=>({name:'Sheet '+i,headers:['Material','Qty'],rows:[['A',5]]}))});
 await act(async()=>{root.render(React.createElement(Dashboard,{user:'viewer'}));await tick()});
 assert.deepEqual([...document.querySelectorAll('nav button')].map(b=>b.textContent),['Production']);
 assert.ok(document.querySelector('.production-workspace'));
 await act(async()=>root.unmount());console.log('Passed: four collapsible production tables, admin-controlled editor, shared save payload and restricted sidebar.');
})().catch(async e=>{await act(async()=>root.unmount());console.error(e);process.exitCode=1});
