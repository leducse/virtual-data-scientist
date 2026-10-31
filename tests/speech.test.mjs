import {test} from 'node:test';
import assert from 'node:assert/strict';
import {speechEvents} from '../aws_backend/streaming/speech.mjs';

test('bounded speech consumes a purpose-specific ticket and streams editable text',async()=>{
  const chunks=[],out={write:c=>chunks.push(c),end(){this.ended=true;}};
  const event={requestContext:{http:{method:'POST'}},body:JSON.stringify({ticket:'a'.repeat(43),audio:Buffer.alloc(64000).toString('base64')})};
  let audioBytes=0;
  await speechEvents(event,out,{consume:async()=>({kind:'speech'})},async function*(audio){
    for await(const item of audio)audioBytes+=item.AudioEvent.AudioChunk.length;
    yield {TranscriptEvent:{Transcript:{Results:[{ResultId:'1',IsPartial:true,Alternatives:[{Transcript:'Show monthly'}]}]}}};
    yield {TranscriptEvent:{Transcript:{Results:[{ResultId:'1',IsPartial:false,Alternatives:[{Transcript:'Show monthly revenue.'}]}]}}};
  });
  assert.equal(audioBytes,64000);assert.ok(chunks.join('').includes('Show monthly revenue.'));assert.ok(chunks.join('').includes('finished'));assert.equal(out.ended,true);
});
test('oversized audio and analysis tickets cannot start transcription',async()=>{
  let calls=0;const out={write(){},end(){}},store={consume:async()=>({kind:'analysis'})};
  const event={requestContext:{http:{method:'POST'}},body:JSON.stringify({ticket:'a'.repeat(43),audio:Buffer.alloc(640002).toString('base64')})};
  await assert.rejects(speechEvents(event,out,store,()=>{calls++;}),/invalid_audio/);
  event.body=JSON.stringify({ticket:'a'.repeat(43),audio:Buffer.alloc(64000).toString('base64')});
  await assert.rejects(speechEvents(event,out,store,()=>{calls++;}),/unauthenticated/);assert.equal(calls,0);
});
