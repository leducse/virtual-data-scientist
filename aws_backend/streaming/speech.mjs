export async function speechEvents(event,out,store,transcribe) {
  const body=JSON.parse(event.isBase64Encoded ? Buffer.from(event.body || '', 'base64').toString() : event.body || '{}');
  if(event.requestContext?.http?.method!=='POST' || !/^[A-Za-z0-9_-]{43}$/.test(body.ticket || '') ||
     typeof body.audio!=='string' || body.audio.length>860000 || !/^[A-Za-z0-9+/]+={0,2}$/.test(body.audio))throw new Error('invalid_audio');
  const pcm=Buffer.from(body.audio,'base64');
  if(pcm.length<32000 || pcm.length>640000 || pcm.length%2 || pcm.toString('base64')!==body.audio)throw new Error('invalid_audio');
  const {createHash}=await import('node:crypto');
  const ticket=await store.consume(createHash('sha256').update(body.ticket).digest('hex'),Math.floor(Date.now()/1000));
  if(!ticket || ticket.kind!=='speech')throw new Error('unauthenticated');
  const send=(kind,data)=>out.write(`event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`);
  send('connected',{audio_seconds:pcm.length/32000});
  const controller=new AbortController(), deadline=setTimeout(()=>controller.abort(),25000);
  try{
    const source=async function*(){for(let i=0;i<pcm.length;i+=6400)yield {AudioEvent:{AudioChunk:pcm.subarray(i,i+6400)}};};
    for await(const result of transcribe(source(),controller.signal)){
      if(out.destroyed){controller.abort();break;}
      for(const item of result.TranscriptEvent?.Transcript?.Results || []){
        const text=item.Alternatives?.[0]?.Transcript;
        if(typeof text==='string')send('transcript',{id:item.ResultId,partial:!!item.IsPartial,text:text.slice(0,2000)});
      }
    }
    send('finished',{audio_seconds:pcm.length/32000});
  }finally{clearTimeout(deadline);pcm.fill(0);out.end();}
}
