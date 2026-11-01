// Pure projection of persisted analysis events; no backend actions or timers.
const ACTIVE=new Set(['queued','running','reviewing']);
export const STEPS={
  planner:{title:'Orchestrator',kind:'Coordinator',icon:'orchestrator',description:'Plans the request and coordinates the selected agents, tools, checks and saved evidence. The application workflow invokes the selected roles.'},
  query:{title:'Data query',kind:'Tool',icon:'query',description:'Queries the prepared data with a reviewed DuckDB aggregation.'},
  analyst:{title:'Analyst',kind:'Agent',icon:'analyst',description:'Analyzes the approved plan and writes its bounded Python program. Code writing is currently part of this analyst role.'},
  interpreter:{title:'Code Interpreter',kind:'Tool',icon:'interpreter',description:'Runs the approved program in a fresh, isolated AgentCore session.'},
  numerical_checks:{title:'Numerical checks',kind:'Check',icon:'checks',description:'Checks source totals, data splits, predictions and reported metrics.'},
  reviewer:{title:'Independent reviewer',kind:'Agent',icon:'reviewer',description:'Reviews the checked evidence and the limitations before publication.'},
  publication:{title:'Saved evidence',kind:'Output',icon:'publication',description:'Saves the checked result, visualizations and reproducible analysis artifacts.'}
};
export const STATUS={coordinating:'Coordinating',started:'Working',completed:'Complete',failed:'Failed',cancelled:'Cancelled',skipped:'Skipped',queued:'Waiting',unrecorded:'Not recorded',interrupted:'Stopped'};
export function duration(ms){return Number.isFinite(ms) && ms>=0 ? `${(ms/1000).toLocaleString('en-US',{maximumFractionDigits:1})}s`:null;}
export function graphFor(run,{compact=false}={}){
  const events=(run.events || []).filter(e=>e && typeof e.stage==='string').map((e,i)=>({...e,order:i})).sort((a,b)=>(a.sequence || a.order)-(b.sequence || b.order));
  const latest=new Map(events.map(e=>[e.stage,e]));
  let route=run.plan?.tier;
  if(!['quick','deep'].includes(route))route=latest.has('query') ? 'quick':events.some(e=>['analyst','interpreter','reviewer'].includes(e.stage)) ? 'deep':null;
  const keys=route==='quick' ? ['planner','query','numerical_checks','publication']:route==='deep' ? ['planner','analyst','interpreter','numerical_checks','reviewer','publication']:['planner'];
  const positions=compact ? [[105,0],[0,180],[210,180],[0,350],[210,350],[105,520]]:
    [[250,0],[0,190],[250,190],[500,190],[0,380],[500,380]];
  const jobEnd=latest.get('analysis'),planning=latest.get('planner');
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
      events:history.map(({order,...e})=>e),hasInput:index>0,hasOutput:index===0 && keys.length>1,coordinator:index===0 ? null:'Orchestrator'};
    if(id==='planner'){
      data.planningStatus=planning ? STATUS[planning.status] || 'Not recorded':'Not recorded';
      data.planningDuration=duration(planning?.duration_ms);
      data.status=run.status==='succeeded' ? 'completed':run.status==='failed' ? 'failed':run.status==='cancelled' ? 'cancelled':
        !ACTIVE.has(run.status) ? 'interrupted':planning?.status==='completed' || (planning?.status!=='started' && (run.status==='running' || run.status==='reviewing')) ? 'coordinating':status;
      data.statusLabel=data.status==='started' ? 'Planning':STATUS[data.status];
      data.duration=duration(jobEnd?.duration_ms);
      data.startedAt=Number.isFinite(run.created_at) ? run.created_at:data.startedAt;
      data.finishedAt=!ACTIVE.has(run.status) && Number.isFinite(jobEnd?.timestamp) ? jobEnd.timestamp:null;
    }
    return {id,type:'activity',style:{width:compact ? 164:196},position:{x:positions[index][0],y:positions[index][1]},data,
      sourcePosition:'bottom',targetPosition:'top'};
  });
  const edges=nodes.slice(1).map((target,i)=>{
    const working=target.data.status==='started',completed=target.data.status==='completed';
    // Lower-row branches go around the outer columns, preserving a visible
    // parent relationship without drawing through another child's card.
    const outer=compact ? i>=2 && i<4:i>=3;
    const railX=outer ? target.position.x===0 ? (compact ? -28:-34):(compact ? 402:730):null;
    return {id:'planner-'+target.id,source:'planner',target:target.id,type:'coordination',animated:working,
      data:{railX},className:working ? 'vds-edge-working':completed ? 'vds-edge-complete':'vds-edge-waiting',
      style:{stroke:working ? '#146659':completed ? '#609482':'#c3cfca',strokeWidth:working ? 2.6:1.8},
      markerEnd:{type:'arrowclosed',color:working ? '#146659':'#9eb6aa'},selectable:false};
  });
  return {route:route || 'planning',nodes,edges,working:nodes.slice(1).find(n=>n.data.status==='started')?.id || (nodes[0].data.status==='started' ? 'planner':null),coordinating:nodes[0].data.status==='coordinating',
    complete:run.status==='succeeded',active:ACTIVE.has(run.status)};
}

// Rounded outer branch, using measured handle coordinates from React Flow.
export function outerBranchPath(sourceX,sourceY,targetX,targetY,railX){
  const points=[[sourceX,sourceY],[sourceX,sourceY+30],[railX,sourceY+30],[railX,targetY-28],[targetX,targetY-28],[targetX,targetY]];
  let path=`M ${points[0][0]} ${points[0][1]}`;
  for(let i=1;i<points.length-1;i++){
    const a=points[i-1],b=points[i],c=points[i+1],before=Math.hypot(b[0]-a[0],b[1]-a[1]),after=Math.hypot(c[0]-b[0],c[1]-b[1]);
    const radius=Math.min(16,before/2,after/2);
    path+=` L ${b[0]-(b[0]-a[0])*radius/before} ${b[1]-(b[1]-a[1])*radius/before} Q ${b[0]} ${b[1]} ${b[0]+(c[0]-b[0])*radius/after} ${b[1]+(c[1]-b[1])*radius/after}`;
  }
  return path+` L ${targetX} ${targetY}`;
}
