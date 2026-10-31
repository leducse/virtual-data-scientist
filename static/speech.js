"use strict";
window.vdsSpeech=(()=>{
  function pcm16(chunks,inputRate){
    if(inputRate<16000 || inputRate>192000)throw new Error('Unsupported microphone sample rate.');
    const length=chunks.reduce((n,c)=>n+c.length,0), samples=new Float32Array(length);let offset=0;
    for(const chunk of chunks){samples.set(chunk,offset);offset+=chunk.length;}
    const ratio=inputRate/16000, count=Math.min(320000,Math.floor(length/ratio)), bytes=new Uint8Array(count*2), view=new DataView(bytes.buffer);
    for(let i=0;i<count;i++){
      const start=Math.floor(i*ratio),end=Math.max(start+1,Math.min(length,Math.floor((i+1)*ratio)));let total=0;
      for(let j=start;j<end;j++)total+=samples[j];
      const value=Math.max(-1,Math.min(1,total/(end-start)));
      view.setInt16(i*2,Math.round(value*(value<0 ? 32768 : 32767)),true);
    }
    samples.fill(0);return bytes;
  }
  function base64(bytes){let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(text);}
  let enabled=false,recording=null,api,notice;
  const el=id=>document.querySelector('#'+id);
  function buttons(busy,transcribing=false){
    el('speech-record').disabled=busy;
    el('speech-stop').hidden=!busy || transcribing;
    el('speech-cancel').hidden=!busy;
  }
  async function release(session){
    clearTimeout(session.timer);session.stream?.getTracks().forEach(t=>t.stop());session.node?.disconnect();
    if(session.context && session.context.state!=='closed')await session.context.close();
  }
  async function stop(){
    const session=recording;if(!session || session.transcribing)return;
    session.transcribing=true;buttons(true,true);await release(session);
    el('speech-status').textContent='Transcribing with Amazon Transcribe…';
    let reader;
    try{
      const bytes=pcm16(session.chunks,session.rate);session.chunks.length=0;
      if(bytes.length<32000)throw new Error('Record at least one second, or type your question.');
      const {ticket}=await api('speech-tickets',{});
      if(session.cancelled)return;
      const response=await window.vdsAuth.request('speech/transcribe',{ticket,audio:base64(bytes)},session.controller.signal);bytes.fill(0);
      if(!response.ok || !response.body)throw new Error('Transcription could not start. You can type instead.');
      reader=response.body.getReader();const decoder=new TextDecoder(),finals=new Map();let pending='',complete=false;
      while(true){
        const {done,value}=await reader.read();if(done)break;pending+=decoder.decode(value,{stream:true});
        if(pending.length>65536)throw new Error('Transcription response exceeded its limit.');
        let boundary;
        while((boundary=pending.indexOf('\n\n'))>=0){
          const block=pending.slice(0,boundary);pending=pending.slice(boundary+2);
          const kind=block.split('\n').find(l=>l.startsWith('event: '))?.slice(7), data=block.split('\n').find(l=>l.startsWith('data: '))?.slice(6);
          if(!kind || !data)continue;const event=JSON.parse(data);
          if(kind==='unavailable')throw new Error('Transcription did not complete. You can type or try again.');
          if(kind==='transcript'){
            if(!event.partial)finals.set(event.id,event.text);
            const transcript=[...finals.values(),...(event.partial ? [event.text] : [])].join(' ');
            el('question').value=[session.base,transcript].filter(Boolean).join(' ').slice(0,2000);
          }
          if(kind==='finished')complete=true;
        }
      }
      if(!complete || !finals.size)throw new Error('No complete speech was detected. Review the draft or type your question.');
      el('speech-status').textContent='Transcript ready. Edit your question, then press Run analysis.';el('question').focus();
    }catch(error){if(error.name!=='AbortError'){el('speech-status').textContent=error.message;notice(error.message,true);}}
    finally{reader?.releaseLock();session.chunks.length=0;if(recording===session){recording=null;buttons(false);}}
  }
  function init(request,showNotice){
    api=request;notice=showNotice;
    el('speech-record').addEventListener('click',async()=>{
      if(!enabled || recording)return;
      const session={chunks:[],base:el('question').value.trim(),controller:new AbortController()};recording=session;buttons(true);
      try{
        session.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true},video:false});
        if(session.cancelled){await release(session);return;}
        session.context=new AudioContext();session.rate=session.context.sampleRate;
        await session.context.audioWorklet.addModule('/static/pcm-worklet.js');
        session.node=new AudioWorkletNode(session.context,'vds-recorder');
        session.node.port.onmessage=e=>{if(e.data.limit){stop();return;}if(!session.transcribing && !session.cancelled)session.chunks.push(e.data);};
        const source=session.context.createMediaStreamSource(session.stream), silent=session.context.createGain();silent.gain.value=0;
        source.connect(session.node).connect(silent).connect(session.context.destination);
        await session.context.resume();el('speech-status').textContent='Recording · up to 20 seconds. Stop to transcribe. Audio is not saved by the app.';
        session.timer=setTimeout(stop,20000);
      }catch(error){await release(session);recording=null;buttons(false);el('speech-status').textContent='Microphone unavailable. You can type your question.';}
    });
    el('speech-stop').addEventListener('click',stop);
    el('speech-cancel').addEventListener('click',async()=>{
      const session=recording;if(!session)return;session.cancelled=true;session.controller.abort();await release(session);session.chunks.length=0;
      el('question').value=session.base;recording=null;buttons(false);el('speech-status').textContent='Dictation cancelled.';
    });
  }
  return {init,pcm16,available(value){enabled=value;el('speech-controls').hidden=!value;}};
})();
