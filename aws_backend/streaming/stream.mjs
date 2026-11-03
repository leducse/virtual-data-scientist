import {createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

export async function streamEvents(event, out, store, {now=Date.now,pause=delay,duration=25000}={}) {
  const body=JSON.parse(event.isBase64Encoded ? Buffer.from(event.body || '', 'base64').toString() : event.body || '{}');
  if(event.requestContext?.http?.method!=='POST' || !/^[A-Za-z0-9_-]{43}$/.test(body.ticket || '') || !Number.isInteger(body.after ?? 0) || (body.after ?? 0)<0)throw new Error('invalid_request');
  const hash=createHash('sha256').update(body.ticket).digest('hex');
  // Single-use opaque ticket: owner and run never come from client parameters.
  const ticket=await store.consume(hash,Math.floor(now()/1000));
  if(!ticket || (ticket.kind && ticket.kind!=='analysis') || ticket.expires_at<Math.floor(now()/1000))throw new Error('unauthenticated');
  let sequence=body.after || 0;
  const began=now();
  const send=(kind,data,id)=>out.write(`${id ? `id: ${id}\n` : ''}event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`);
  send('connected',{reconnect_after_ms:1000});
  while(now()-began<duration && !out.destroyed){
    const dataset=await store.dataset(ticket.owner,ticket.dataset_id);
    if(!dataset || dataset.deleted){send('unavailable',{code:'not_found'});break;}
    const run=await store.run(ticket.owner,ticket.run_id);
    if(!run || run.dataset_id!==ticket.dataset_id){send('unavailable',{code:'not_found'});break;}
    for(const item of run.events || []){
      if(item.sequence>sequence){send('stage',item,item.id);sequence=item.sequence;}
    }
    if(!['queued','running','reviewing'].includes(run.status)){
      if(run.status==='succeeded' && run.result_key){
        const result=await store.result(ticket.owner,run.result_key);
        const current=await store.dataset(ticket.owner,ticket.dataset_id);
        if(!current || current.deleted){send('unavailable',{code:'not_found'});break;}
        send('checked_result',{run_id:run.id,summary:result.summary,visuals:result.visuals,methodology:result.methodology});
      }
      send('finished',{run_id:run.id,status:run.status});
      break;
    }
    out.write(': heartbeat\n\n');
    await pause(1000);
  }
  out.end();
}
