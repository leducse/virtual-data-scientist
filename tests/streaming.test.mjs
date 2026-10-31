import {test} from 'node:test';
import assert from 'node:assert/strict';
import {streamEvents} from '../aws_backend/streaming/stream.mjs';

function setup({deleted=false,ticket=true}={}){
  const chunks=[];
  const out={write:c=>chunks.push(c),end(){this.ended=true;}};
  const store={consume:async()=>ticket ? {owner:'owner',dataset_id:'dataset',run_id:'run',expires_at:9999999999} : null,
    dataset:async()=>({deleted}),run:async()=>({id:'run',dataset_id:'dataset',status:'succeeded',result_key:'key',events:[{id:'run:1',sequence:1},{id:'run:2',sequence:2}]}),
    result:async()=>({summary:'Checked',visuals:[],executed_code:'private-code',evidence:{internal:true}})};
  return {chunks,out,store,event:{requestContext:{http:{method:'POST'}},body:JSON.stringify({ticket:'a'.repeat(43),after:1,owner:'attacker'})}};
}
test('replays only unseen events and emits checked public fields',async()=>{
  const c=setup();await streamEvents(c.event,c.out,c.store);
  const text=c.chunks.join('');assert.ok(!text.includes('run:1'));assert.ok(text.includes('run:2'));assert.ok(text.includes('checked_result'));assert.ok(text.includes('finished'));
  assert.ok(!text.includes('private-code'));assert.ok(!text.includes('internal'));assert.equal(c.out.ended,true);
});
test('deleted datasets and consumed tickets cannot stream results',async()=>{
  const c=setup({deleted:true});await streamEvents(c.event,c.out,c.store);assert.ok(!c.chunks.join('').includes('checked_result'));
  const invalid=setup({ticket:false});await assert.rejects(streamEvents(invalid.event,invalid.out,invalid.store),/unauthenticated/);
});
