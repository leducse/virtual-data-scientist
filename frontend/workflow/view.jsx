import React,{memo,useEffect,useId,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ReactFlow,Handle,Position,useNodesInitialized,useReactFlow,useStore,BaseEdge,getBezierPath} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './view.css';
import {graphFor} from './model.mjs';

const paths={orchestrator:'M12 5v5M6 19v-4h12v4M6 15v-2h12v2M12 10v3',analyst:'M4 18h16M5 14l4-4 4 2 6-7',query:'M4 5h16v14H4zM4 10h16M10 5v14',interpreter:'M4 5h16v14H4zM7 9l3 3-3 3M13 15h4',checks:'M12 3l8 4v6c0 4-8 8-8 8s-8-4-8-8V7zM8 12l3 3 5-6',reviewer:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM9 12a3 3 0 106 0 3 3 0 10-6 0',publication:'M5 3h10l4 4v14H5zM14 3v5h5M8 13h8M8 17h6'};
const colors={planner:'#5CC4B4',analyst:'#9B7BD4',interpreter:'#6BA8D4',numerical_checks:'#A4C87A',reviewer:'#D4708A',publication:'#5CC4B4',query:'#6BA8D4'};
const shortNames={planner:'Orch.',analyst:'Analyst',interpreter:'Python',numerical_checks:'Checks',reviewer:'Review',publication:'Save',query:'Query'};
const cardNames={...shortNames,planner:'Orchestrator',query:'Data query'};
const Icon=({name})=><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d={paths[name]} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>{name==='orchestrator' && <><circle cx="12" cy="4" r="2" fill="currentColor"/><circle cx="6" cy="20" r="2" fill="currentColor"/><circle cx="18" cy="20" r="2" fill="currentColor"/></>}</svg>;
function useReducedMotion(){
  const [reduced,setReduced]=useState(()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(()=>{const media=window.matchMedia('(prefers-reduced-motion: reduce)'),update=()=>setReduced(media.matches);media.addEventListener('change',update);return ()=>media.removeEventListener('change',update);},[]);
  return reduced;
}
const StepNode=memo(function StepNode({id,data}){
  return <div className={`vds-org-card is-${data.status} ${id==='planner' ? 'is-root':''} ${data.inspected ? 'is-inspected':''}`} style={{'--role':colors[id]}}>
    {data.hasInput && <Handle type="target" position={Position.Top} isConnectable={false}/>}
    <button type="button" className="vds-node-button nodrag" onClick={data.inspect} title={`${data.title} · ${data.kind}: ${data.statusLabel}${data.duration ? ` · ${data.duration}`:''}`} aria-pressed={data.inspected} aria-label={`${data.title}: ${data.statusLabel}. Inspect details.`}>
      <span className="vds-node-top"><Icon name={data.icon}/><span className="vds-state-dot"/></span>
      <strong>{cardNames[id]}</strong><span className="vds-node-state">{data.statusLabel}</span>
      {data.duration && <span className="vds-node-time">{data.duration}</span>}
    </button>
    {data.hasOutput && <Handle type="source" position={Position.Bottom} isConnectable={false}/>}
  </div>;
});
const nodeTypes={activity:StepNode};
function CoordinationEdge({id,sourceX,sourceY,targetX,targetY,data,markerEnd,style}){
  const [path]=getBezierPath({sourceX,sourceY,targetX,targetY,sourcePosition:Position.Bottom,targetPosition:Position.Top,curvature:.55});
  return <g className={`vds-org-link ${data.working ? 'is-working':''}`} style={{'--role':data.color}}>
    <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style}/>
    {data.working && !data.reduced && <circle r="2.5" className="vds-org-pulse"><animateMotion dur="2.4s" repeatCount="indefinite" path={path}/></circle>}
  </g>;
}
const edgeTypes={coordination:CoordinationEdge};
function FitLayout({geometryKey}){
  const ready=useNodesInitialized(),width=useStore(s=>s.width),height=useStore(s=>s.height),{fitView}=useReactFlow();
  useEffect(()=>{if(ready && width && height)void fitView({padding:.07,maxZoom:1,duration:0});},[ready,width,height,geometryKey,fitView]);
  return null;
}
function StatusPoint({node,selected,inspect,scope}){
  const {id,data}=node,tooltip=scope+'-'+id;
  return <button type="button" className={`vds-status-point is-${data.status}`} data-agent={id} aria-label={`${data.title}: ${data.statusLabel}. Inspect details.`} aria-describedby={tooltip} aria-pressed={selected===id} onClick={()=>inspect(id)}>
    <span className="vds-status-light" aria-hidden="true"/><span className="vds-status-name">{shortNames[id]}</span>
    <span id={tooltip} className="vds-point-tooltip" role="tooltip"><strong>{data.title}</strong><span>{data.kind} · {data.statusLabel}{data.duration ? ` · ${data.duration}`:''}</span></span>
  </button>;
}
function Workflow({run}){
  const host=useRef(null),toggle=useRef(null),scope=useId(),reduced=useReducedMotion();
  const [compact,setCompact]=useState(true),[measurements,setMeasurements]=useState({});
  const [expanded,setExpanded]=useState(false),[selected,setSelected]=useState(null);
  useEffect(()=>{const observer=new ResizeObserver(entries=>setCompact(entries[0].contentRect.width<700));observer.observe(host.current);return ()=>observer.disconnect();},[]);
  const graph=graphFor(run,{compact,mini:true});
  const selectedId=graph.nodes.some(n=>n.id===selected) ? selected:null;
  const inspected=graph.nodes.find(n=>n.id===(selectedId || graph.working || 'planner'));
  const span=Math.max(...graph.nodes.map(n=>n.position.x+n.style.width));
  const nodes=graph.nodes.map((n,i)=>({...n,position:{x:i===0 ? Math.max(0,(span-130)/2):n.position.x,y:i===0 ? 0:116},style:{width:i===0 ? 130:n.style.width},measured:measurements[n.id],data:{...n.data,inspected:n.id===selectedId,inspect:()=>setSelected(n.id)}}));
  const edges=graph.edges.map(edge=>({...edge,data:{working:edge.animated,reduced,color:colors[edge.target]},
    style:{stroke:colors[edge.target],strokeOpacity:edge.animated ? 1:edge.className==='vds-edge-complete' ? .6:.25,strokeWidth:edge.animated ? 2:1.2},
    markerEnd:{type:'arrowclosed',color:colors[edge.target],width:10,height:10}}));
  const geometryKey=nodes.map(n=>`${n.id}:${n.style.width}:${n.measured?.height || 0}`).join('|');
  function recordMeasurements(changes){
    const sizes=changes.filter(c=>c.type==='dimensions' && Number.isFinite(c.dimensions?.width) && Number.isFinite(c.dimensions?.height));
    if(!sizes.length)return;
    setMeasurements(previous=>{
      let next=previous;
      for(const size of sizes){if(previous[size.id]?.width!==size.dimensions.width || previous[size.id]?.height!==size.dimensions.height){if(next===previous)next={...previous};next[size.id]=size.dimensions;}}
      return next;
    });
  }
  const step=inspected.data;
  const status=graph.complete ? 'Complete':graph.active ? graph.working ? `${graph.nodes.find(n=>n.id===graph.working).data.title} working`:graph.coordinating ? 'Coordinating':'Waiting':run.status==='cancelled' ? 'Cancelled':'Stopped';
  function dismiss(event){if(event.key==='Escape' && (expanded || selectedId)){event.preventDefault();setExpanded(false);setSelected(null);toggle.current?.focus();}}
  return <section ref={host} className={`vds-workflow route-${graph.route} ${expanded ? 'is-expanded':'is-status'}`} aria-label="Agent activity status" onKeyDown={dismiss}>
    <div className="vds-status-bar"><div className="vds-status-hierarchy" role="group" aria-label="Orchestrator and its selected capabilities">
      <StatusPoint node={graph.nodes[0]} selected={selectedId} inspect={setSelected} scope={scope}/>
      {graph.nodes.length>1 && <div className="vds-status-children" role="group" aria-label="Coordinated by Orchestrator">{graph.nodes.slice(1).map(node=><StatusPoint key={node.id} node={node} selected={selectedId} inspect={setSelected} scope={scope}/>)}</div>}
    </div><span className="vds-status-announcement" role="status">{status}</span><button ref={toggle} type="button" className="vds-map-toggle" onClick={()=>{if(expanded)setSelected(null);setExpanded(value=>!value);}} aria-expanded={expanded} aria-controls={scope+'-map'} aria-label="Agent map" title={status+' · Toggle agent map'}>Map <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5 6 7.5 9 4.5"/></svg></button></div>
    {expanded && <div id={scope+'-map'} className="vds-org-panel">
      <div className="vds-org-heading"><span>AGENT ACTIVITY</span><span className="vds-org-status">{status}</span></div>
      <div className="vds-flow-canvas" aria-label="Orchestrator and selected agents, tools and checks">
        <ReactFlow nodes={nodes} onNodesChange={recordMeasurements} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={{padding:.07,maxZoom:1}} minZoom={.3} maxZoom={1}
          nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} nodesFocusable={false} edgesFocusable={false}
          deleteKeyCode={null} selectionOnDrag={false} selectNodesOnDrag={false} zoomOnScroll={false} zoomOnDoubleClick={false} zoomOnPinch={false} panOnDrag={false} preventScrolling={false}
          onNodeClick={(_,node)=>setSelected(node.id)}>
          <FitLayout geometryKey={geometryKey}/>
        </ReactFlow>
      </div>
      <p className="vds-coordination-note">{graph.route==='planning' ? 'The orchestrator is selecting the analysis path.':'Arrows show delegation. Moving dots follow recorded work.'}</p>
      <StepDetail step={step} selected={selectedId} follow={()=>setSelected(null)}/>
    </div>}
    {!expanded && selectedId && <div className="vds-status-inspector"><StepDetail step={step} selected={selectedId} follow={()=>setSelected(null)}/></div>}
  </section>;
}
function StepDetail({step,selected,follow}){
  return <div className="vds-flow-detail" aria-label="Selected step details"><div className="vds-detail-heading"><span className="vds-detail-icon"><Icon name={step.icon}/></span><div><strong>{step.title}</strong><span>{step.kind} · {step.statusLabel}{step.duration ? ` · ${step.duration}`:''}{step.attempt>1 ? ` · attempt ${step.attempt}`:''}</span></div>{selected && <button type="button" className="vds-follow" onClick={follow}>Follow activity</button>}</div><p>{step.description}</p>
    {step.planningStatus && <p className="vds-detail-time">Planning: {step.planningStatus}{step.planningDuration ? ` · ${step.planningDuration}`:''}</p>}
    {step.startedAt && <p className="vds-detail-time">Started {new Date(step.startedAt*1000).toLocaleTimeString()}{step.finishedAt ? ` · Last recorded ${new Date(step.finishedAt*1000).toLocaleTimeString()}`:''}</p>}
  </div>;
}
const roots=new WeakMap();
window.vdsWorkflow={
  render(run,element){if(!element)return;let root=roots.get(element);if(!root){root=createRoot(element);roots.set(element,root);}root.render(<Workflow run={run} key={run.id}/>);},
  dispose(element){const root=roots.get(element);if(root){root.unmount();roots.delete(element);}}
};
