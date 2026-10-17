const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),{JSDOM}=require('jsdom');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,n)=>m._compile(ts.transpileModule(fs.readFileSync(n,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,n);
const dom=new JSDOM('<div id="root"></div>',{url:'https://workspace.test'});Object.assign(global,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,IS_REACT_ACT_ENVIRONMENT:true});
const prefs={};require.cache[require.resolve('../src/bridge.ts')]={loaded:true,exports:{can:()=>false,readViewPreference:k=>prefs[k],saveViewPreference:(k,v)=>prefs[k]=v}};
const React=require('react'),{act}=React,{createRoot}=require('react-dom/client'),Grid=require('../src/data-grid.tsx').default,root=createRoot(document.getElementById('root')),tick=()=>new Promise(r=>setImmediate(r));
const headers=['Code','Qty','Warehouse'],rows=[['B',2,'Y'],['A',10,'Z']];let exported,clicked;
const props=scope=>({headers,rows,storageKey:scope,onCell:(r,i)=>clicked={r,i},matchedExport:async(h,r)=>exported={h,r}});
async function click(label){await act(async()=>{document.querySelector('[aria-label="'+label+'"]').click();await tick()})}
async function select(label,value){await act(async()=>{const el=document.querySelector('[aria-label="'+label+'"]');Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype,'value').set.call(el,value);el.dispatchEvent(new window.Event('change',{bubbles:true}));await tick()})}
(async()=>{
 await act(async()=>{root.render(React.createElement(Grid,props('layout-a')));await tick()});
 await click('Move Warehouse left');await click('Move Warehouse left');
 assert.deepEqual([...document.querySelectorAll('thead .sortheading')].map(e=>e.textContent),['Warehouse','Code','Qty']);
 await select('Sort by column','Qty');await select('Sort direction','-1');
 assert.equal(document.querySelector('tbody td').textContent,'Z');
 await act(async()=>{document.querySelector('tbody td button').click();await tick()});assert.deepEqual(clicked,{r:['A',10,'Z'],i:2},'Reordering must preserve the source-column drill-down index');
 await act(async()=>{[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Download matched records')).click();await tick()});
 assert.deepEqual(exported,{h:['Warehouse','Code','Qty'],r:[['Z','A',10],['Y','B',2]]});
 assert.deepEqual(prefs['grid:layout-a'].order,['Warehouse','Code','Qty']);
 await act(async()=>{root.render(React.createElement(Grid,props('layout-b')));await tick()});assert.equal(document.querySelector('thead .sortheading').textContent,'Code');
 await act(async()=>{root.render(React.createElement(Grid,props('layout-a')));await tick()});assert.equal(document.querySelector('thead .sortheading').textContent,'Warehouse');
 await act(async()=>{[...document.querySelectorAll('button')].find(b=>b.textContent==='Reset table view').click();await tick()});assert.equal(document.querySelector('thead .sortheading').textContent,'Code');
 await act(async()=>root.unmount());console.log('Passed: reordered headers, numeric sorting, original drill-down indices, export layout and independent saved table views.');
})().catch(e=>{console.error(e);process.exit(1)});
