const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');
require.extensions['.ts']=(module,name)=>module._compile(ts.transpileModule(fs.readFileSync(name,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText,name);
const sent=[];
global.window={addEventListener(){},parent:{postMessage:packet=>sent.push(packet)},fetch:global.fetch};
// Leave the first RPC unresolved and disable its real timeout.
global.setTimeout=()=>1;
const bridge=require('../src/bridge.ts');
(async()=>{
 bridge.rpc('heartbeat');await Promise.resolve();await Promise.resolve();
 assert.equal(sent[0].value.action,'heartbeat');
 bridge.openAccount('open_admin');
 assert.equal(sent[1].value.action,'open_admin');
 bridge.openAccount('open_password');
 assert.equal(sent[2].value.action,'open_password');
 assert.ok(sent.every(message=>message.isStreamlitMessage&&message.value.id));
 console.log('Passed: account navigation is delivered immediately while another dashboard RPC is unresolved.');
})().catch(error=>{console.error(error);process.exitCode=1});
