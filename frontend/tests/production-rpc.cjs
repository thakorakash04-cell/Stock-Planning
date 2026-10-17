const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
require.extensions['.ts']=(m,n)=>m._compile(ts.transpileModule(fs.readFileSync(n,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText,n);
const sent=[],handlers={};
global.window={addEventListener:(name,handler)=>handlers[name]=handler,parent:{postMessage:p=>sent.push(p)},screen:{availHeight:900},fetch:global.fetch};global.setTimeout=()=>1;global.setInterval=()=>1;
const bridge=require('../src/bridge.ts');bridge.startBridge(()=>{});
const tick=()=>new Promise(r=>setImmediate(r));
function reply(id,body){handlers.message({source:window.parent,origin:'https://workspace.test',data:{type:'streamlit:render',args:{user:'viewer',response:{id,body}}}})}
(async()=>{
 const plan='a'.repeat(32);
 for(const action of ['production_save','production_availability']){
  const request=bridge.rpc(action,{plan_id:plan,id:'must-not-replace-request-id',action:'wrong-action'});await tick();
  const packet=sent.at(-1).value;assert.equal(packet.action,action);assert.equal(packet.plan_id,plan);assert.notEqual(packet.id,plan);assert.notEqual(packet.id,'must-not-replace-request-id');
  reply(packet.id,{ok:true});assert.deepEqual(await request,{ok:true});
 }
 console.log('Passed: production plan IDs remain separate from RPC IDs; save and availability responses resolve.');
})().catch(e=>{console.error(e);process.exitCode=1});
