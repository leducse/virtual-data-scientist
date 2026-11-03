const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const context={window:{},Float32Array,Uint8Array,DataView,Math,Error};
vm.runInNewContext(fs.readFileSync('static/speech.js','utf8'),context);
test('microphone PCM conversion downsamples, clips and uses little-endian 16-bit samples',()=>{
  const pcm=context.window.vdsSpeech.pcm16([new Float32Array([1,1,1,-1,-1,-1,0,0,0])],48000);
  const view=new DataView(pcm.buffer);
  assert.equal(pcm.length,6);assert.equal(view.getInt16(0,true),32767);assert.equal(view.getInt16(2,true),-32768);assert.equal(view.getInt16(4,true),0);
  assert.throws(()=>context.window.vdsSpeech.pcm16([],8000),/sample rate/);
  assert.equal(context.window.vdsSpeech.pcm16([new Float32Array(960000)],16000).length,640000);
});
