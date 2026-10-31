// Pure projection of persisted analysis events; no backend actions or timers.
const ACTIVE=new Set(['queued','running','reviewing']);
export const STEPS={
  planner:{title:'Orchestrator',kind:'Agent',icon:'orchestrator',description:'Reads the prepared profile and your question, then chooses the analytical path.'},
  query:{title:'Data query',kind:'Tool',icon:'query',description:'Queries the prepared data with a reviewed DuckDB aggregation.'},
  analyst:{title:'Analyst',kind:'Agent',icon:'analyst',description:'Prepares a bounded Python program for the approved analysis recipe.'},
  interpreter:{title:'Code Interpreter',kind:'Tool',icon:'interpreter',description:'Runs the approved program in a fresh, isolated AgentCore session.'},
  numerical_checks:{title:'Numerical checks',kind:'Check',icon:'checks',description:'Checks source totals, data splits, predictions and reported metrics.'},
  reviewer:{title:'Independent reviewer',kind:'Agent',icon:'reviewer',description:'Reviews the checked evidence and the limitations before publication.'},
  publication:{title:'Saved evidence',kind:'Output',icon:'publication',description:'Saves the checked result, visualizations and reproducible analysis artifacts.'}
};
export const STATUS={started:'Working',completed:'Complete',failed:'Failed',cancelled:'Cancelled',skipped:'Skipped',queued:'Waiting',unrecorded:'Not recorded',interrupted:'Stopped'};
export function duration(ms){return Number.isFinite(ms) && ms>=0 ? `${(ms/1000).toLocaleString('en-US',{maximumFractionDigits:1})}s`:null;}
export function graphFor(run,{compact=false}={}){
  const events=(run.events || []).filter(e=>e && typeof e.stage==='string').map((e,i)=>({...e,order:i})).sort((a,b)=>(a.sequence || a.order)-(b.sequence || b.order));
  const latest=new Map(events.map(e=>[e.stage,e]));
  let route=run.plan?.tier;
  if(!['quick','deep'].includes(route))route=latest.has('query') ? 'quick':events.some(e=>['analyst','interpreter','reviewer'].includes(e.stage)) ? 'deep':null;
  const keys=route==='quick' ? ['planner','query','numerical_checks','publication']:route==='deep' ? ['planner','analyst','interpreter','numerical_checks','reviewer','publication']:['planner'];
  const positions=compact ? [[0,0],[210,0],[210,160],[0,160],[0,320],[210,320]]:keys.length===4 ? [[0,0],[300,0],[300,180],[0,180]]:[[0,0],[250,0],[500,0],[500,180],[250,180],[0,180]];
  const nodes=keys.map((id,index)=>{
    const event=latest.get(id),history=events.filter(e=>e.stage===id);
    let status=event?.status || (ACTIVE.has(run.status) ? 'queued':'unrecorded');
    if(!STATUS[status])status=ACTIVE.has(run.status) ? 'queued':'unrecorded';
    if(status==='started' && !ACTIVE.has(run.status))status='interrupted';
    const starts=history.filter(e=>e.status==='started'),lastStart=starts.at(-1);
    const attempt=Number.isInteger(event?.attempt) && event.attempt>0 ? event.attempt:lastStart?.attempt || 1;
    const data={...STEPS[id],status,statusLabel:STATUS[status],duration:duration(event?.duration_ms),
      attempt,startedAt:Number.isFinite(lastStart?.timestamp) ? lastStart.timestamp:null,
      finishedAt:event && event.status!=='started' && Number.isFinite(event.timestamp) ? event.timestamp:null,
      events:history.map(({order,...e})=>e),step:index+1,hasInput:index>0,hasOutput:index<keys.length-1};
    const source=compact ? ['right','bottom','left','bottom','right','right'][index]:index===keys.length/2-1 ? 'bottom':index>=keys.length/2 ? 'left':'right';
    const target=compact ? ['left','left','top','right','top','left'][index]:index===keys.length/2 ? 'top':index>=keys.length/2 ? 'right':'left';
    return {id,type:'activity',style:{width:compact ? 164:196},position:{x:positions[index][0],y:positions[index][1]},data,
      sourcePosition:source,targetPosition:target};
  });
  const edges=nodes.slice(1).map((target,i)=>{
    const source=nodes[i],working=source.data.status==='completed' && target.data.status==='started';
    return {id:source.id+'-'+target.id,source:source.id,target:target.id,type:'smoothstep',animated:working,
      className:working ? 'vds-edge-working':source.data.status==='completed' && target.data.status==='completed' ? 'vds-edge-complete':'vds-edge-waiting',
      style:{stroke:working ? '#146659':source.data.status==='completed' && target.data.status==='completed' ? '#609482':'#c3cfca',strokeWidth:working ? 2.6:1.8},
      pathOptions:{borderRadius:22},markerEnd:{type:'arrowclosed',color:working ? '#146659':'#9eb6aa'},selectable:false};
  });
  return {route:route || 'planning',nodes,edges,working:nodes.find(n=>n.data.status==='started')?.id || null,
    complete:run.status==='succeeded',active:ACTIVE.has(run.status)};
}
