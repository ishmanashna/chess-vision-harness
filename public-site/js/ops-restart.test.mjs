import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = fs.readFileSync(new URL("ops-restart.js", import.meta.url), "utf8");
const flush = () => new Promise(resolve => setImmediate(resolve));
function page(request) {
  let listener, tick;
  const button = {disabled:false, addEventListener(_event, fn) {this.click=fn;}};
  const status = {textContent:""};
  const other = [{disabled:false},{disabled:false}];
  const context = {window:{CVH:{opsRequest:request}},Date,Promise,
    document:{querySelector:sel=>sel==='[data-ops-restart]'?button:status,
      querySelectorAll:()=>[button,...other],addEventListener(_event,fn){listener=fn;}},
    setTimeout(fn){tick=fn;return 1;},clearTimeout(){}};
  vm.runInNewContext(source,context);
  listener();
  return {button,status,other,context,tick:()=>tick()};
}

test("restart reconnects through downtime and verifies the new process",async()=>{
  let phase=0;
  const p=page(async(_key,_url,_timeout,options)=>{
    if(options?.method==='POST'){phase=1;return {operation_id:'op'};}
    if(phase===1){phase=2;throw Error('connection refused');}
    if(phase===2)return {operation_id:'op',status:'ready',new_pid:23,server_pid:23,old_instance:'old',instance:'new'};
    return {supported:true,status:'idle'};
  });
  await flush(); p.button.click(); await flush();
  assert.ok(p.button.disabled && p.other.every(b=>b.disabled));
  p.tick(); await flush();
  assert.match(p.status.textContent,/reconnecting/);
  p.tick(); await flush();
  assert.match(p.status.textContent,/successfully/);
  assert.equal(p.context.window.CVH.restartPending,false);
});

test("refusal displays the server reason and leaves controls usable",async()=>{
  const p=page(async(_key,_url,_timeout,options)=>{
    if(options?.method==='POST')throw Error('Restart refused: games are running');
    return {supported:true,status:'idle'};
  });
  await flush();p.button.click();await flush();
  assert.match(p.status.textContent,/games are running/);
  assert.equal(p.button.disabled,false);
});

test("old backend displays the one-time activation message",async()=>{
  const p=page(async()=>{throw Object.assign(Error('HTTP 404'),{status:404});});
  await flush();
  assert.equal(p.button.disabled,true);
  assert.match(p.status.textContent,/manual server restart/);
});
