const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),{JSDOM}=require('jsdom');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,n)=>m._compile(ts.transpileModule(fs.readFileSync(n,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,n);
const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'https://workspace.test'});
Object.assign(global,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});
const calls=[];
require.cache[require.resolve('../src/bridge.ts')]={id:'bridge',filename:require.resolve('../src/bridge.ts'),loaded:true,exports:{can:()=>false,isAdmin:()=>false,rpc:async(action,payload)=>{calls.push({action,payload});if(action==='planning_status')return {version:'v1',options:[{code:'A',description:'FG A',unit:'EA',segment:'Wound'},{code:'B',description:'FG B',unit:'BOX',segment:'Wound'}]};return {version:'v1',headers:['Component','Required quantity','Need to order'],rows:[['X',20,8]],materials:1,components:1}}}};
const React=require('react'),{act}=React,{createRoot}=require('react-dom/client'),root=createRoot(document.getElementById('root')),Planning=require('../src/order-planning.tsx').default;
const tick=()=>new Promise(r=>setImmediate(r));
const get=label=>document.querySelector('[aria-label="'+label+'"]');
async function change(el,value){await act(async()=>{const proto=el.tagName==='SELECT'?window.HTMLSelectElement.prototype:window.HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,value);el.dispatchEvent(new window.Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));await tick()})}
(async()=>{
 await act(async()=>{root.render(React.createElement(Planning,{revision:'one'}));await tick()});
 assert.equal(get('FG material').options.length,3);
 await change(get('FG material'),'A');await change(get('Planning quantity'),'10');
 await act(async()=>{document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));await tick()});
 assert.ok(get('Quantity for A'));assert.equal(get('FG material').options.length,2,'Duplicate FG cannot be added');
 const calc=()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Calculate need to order');
 await act(async()=>{calc().click();await tick()});
 assert.deepEqual(calls.at(-1),{action:'planning_calculate',payload:{version:'v1',entries:[{code:'A',quantity:10}]}});
 assert.ok(document.body.textContent.includes('Material requirements'));
 await change(get('Quantity for A'),'12');assert.ok(!document.body.textContent.includes('Material requirements'),'Editing clears stale results');
 await change(get('Quantity for A'),'-2');assert.equal(calc().disabled,true);
 await act(async()=>{root.render(React.createElement(Planning,{revision:'two'}));await tick()});
 assert.equal(get('Quantity for A'),null,'New workbook clears old plan');
 await act(async()=>root.unmount());console.log('Passed: FG inputs, duplicate prevention, versioned calculation, stale results and workbook reset.');
})().catch(e=>{console.error(e);process.exitCode=1});
