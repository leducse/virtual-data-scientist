import React,{memo,useEffect,useId,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ReactFlow,Background,Controls,Handle,Position,useNodesInitialized,useReactFlow,useStore,BaseEdge,getSmoothStepPath,useUpdateNodeInternals} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './view.css';
import {graphFor,outerBranchPath} from './model.mjs';

const paths={orchestrator:'M12 5v5M6 19v-4h12v4M6 15v-2h12v2M12 10v3',analyst:'M4 18h16M5 14l4-4 4 2 6-7',query:'M4 5h16v14H4zM4 10h16M10 5v14',interpreter:'M4 5h16v14H4zM7 9l3 3-3 3M13 15h4',checks:'M12 3l8 4v6c0 4-8 8-8 8s-8-4-8-8V7zM8 12l3 3 5-6',reviewer:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM9 12a3 3 0 106 0 3 3 0 10-6 0',publication:'M5 3h10l4 4v14H5zM14 3v5h5M8 13h8M8 17h6'};
const Icon=({name})=><svg viewBox="0 0 24 24" width="21" height="21" aria-hidden="true"><path d={paths[name]} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>{name==='orchestrator' && <><circle cx="12" cy="4" r="2" fill="currentColor"/><circle cx="6" cy="20" r="2" fill="currentColor"/><circle cx="18" cy="20" r="2" fill="currentColor"/></>}</svg>;
const StepNode=memo(function StepNode({id,data,sourcePosition,targetPosition}){
  const updateNodeInternals=useUpdateNodeInternals();
  useEffect(()=>{updateNodeInternals(id);},[id,data.hasInput,data.hasOutput,sourcePosition,targetPosition,data.mini,updateNodeInternals]);
  return <div className={`vds-flow-card is-${data.status} kind-${data.kind.toLowerCase()} ${data.inspected ? 'is-inspected':''}`}>
    {data.hasInput && <Handle type="target" position={targetPosition || Position.Left} isConnectable={false}/>}
    <button type="button" className="vds-node-button nodrag" onClick={data.inspect} title={`${data.title}: ${data.statusLabel}${data.duration ? ` · ${data.duration}`:""}`} aria-pressed={data.inspected} aria-label={`${data.title}: ${data.statusLabel}. Inspect details.`}>
      <span className="vds-node-top"><span className="vds-node-icon"><Icon name={data.icon}/></span><span className="vds-node-kind">{data.kind}</span></span>
      <strong>{data.title}</strong>
      <span className="vds-node-bottom"><span className="vds-state-dot"/>{data.statusLabel}<span className="vds-node-time">{data.duration || (data.status==='started' ? 'In progress':data.status==='coordinating' ? 'Active':'')}{data.attempt>1 ? ` · attempt ${data.attempt}`:''}</span></span>
    </button>
    {data.hasOutput && <Handle type="source" position={sourcePosition || Position.Right} isConnectable={false}/>}
  </div>;
});
const nodeTypes={activity:StepNode};
function CoordinationEdge({id,sourceX,sourceY,targetX,targetY,data,markerEnd,style}){
  const path=Number.isFinite(data?.railX) ? outerBranchPath(sourceX,sourceY,targetX,targetY,data.railX):
    getSmoothStepPath({sourceX,sourceY,targetX,targetY,sourcePosition:Position.Bottom,targetPosition:Position.Top,borderRadius:18})[0];
  return <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style}/>;
}
const edgeTypes={coordination:CoordinationEdge};
function FitLayout({route,compact,geometryKey,mini}){
  const ready=useNodesInitialized(),width=useStore(s=>s.width),height=useStore(s=>s.height),{fitView}=useReactFlow();
  useEffect(()=>{if(ready && width && height)void fitView({padding:mini ? .02:compact ? .18:.12,maxZoom:1,duration:0});},[ready,width,height,route,compact,geometryKey,mini,fitView]);
  return null;
}
const shortNames={planner:'Plan',analyst:'Analyst',interpreter:'Python',numerical_checks:'Check',reviewer:'Review',publication:'Save',query:'Query'};
function StatusPoint({node,selected,inspect,scope}){
  const {id,data}=node,tooltip=scope+'-'+id;
  return <button type="button" className={`vds-status-point is-${data.status}`} data-agent={id} aria-label={`${data.title}: ${data.statusLabel}. Inspect details.`} aria-describedby={tooltip} aria-pressed={selected===id} onClick={()=>inspect(id)}>
    <span className="vds-status-light" aria-hidden="true"/><span className="vds-status-name">{shortNames[id]}</span>
    <span id={tooltip} className="vds-point-tooltip" role="tooltip"><strong>{data.title}</strong><span>{data.statusLabel}{data.duration ? ` · ${data.duration}`:''}</span></span>
  </button>;
}
function Workflow({run}){
  const host=useRef(null),toggle=useRef(null),scope=useId(),[compact,setCompact]=useState(()=>window.innerWidth<760);
  useEffect(()=>{const observer=new ResizeObserver(entries=>setCompact(entries[0].contentRect.width<500));observer.observe(host.current);return ()=>observer.disconnect();},[]);
  const [measurements,setMeasurements]=useState({});
  const [expanded,setExpanded]=useState(false),[selected,setSelected]=useState(null);
  useEffect(()=>{
    if(!expanded)return;
    const background=[],previousOverflow=document.body.style.overflow;
    for(let branch=host.current;branch && branch!==document.body;branch=branch.parentElement){
      for(const sibling of branch.parentElement.children){
        if(sibling!==branch && !sibling.inert){background.push(sibling);sibling.inert=true;}
      }
    }
    document.body.style.overflow='hidden';
    toggle.current?.focus();
    function keepFocus(event){if(!host.current.contains(event.target))toggle.current?.focus();}
    function keydown(event){
      if(event.key==='Escape'){event.preventDefault();setExpanded(false);setSelected(null);requestAnimationFrame(()=>toggle.current?.focus());}
      if(event.key==='Tab'){
        const targets=[...host.current.querySelectorAll('button:not([disabled]),a[href],[tabindex="0"]')].filter(n=>n.getClientRects().length);
        const first=targets[0],last=targets.at(-1);
        if(event.shiftKey && document.activeElement===first){event.preventDefault();last?.focus();}
        else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first?.focus();}
      }
    }
    document.addEventListener('keydown',keydown);document.addEventListener('focusin',keepFocus);
    return ()=>{document.removeEventListener('keydown',keydown);document.removeEventListener('focusin',keepFocus);for(const sibling of background)sibling.inert=false;document.body.style.overflow=previousOverflow;};
  },[expanded]);
  const graph=graphFor(run,{compact});
  const selectedId=graph.nodes.some(n=>n.id===selected) ? selected:null;
  const inspected=graph.nodes.find(n=>n.id===(selectedId || graph.working || 'planner'));
  const nodes=graph.nodes.map(n=>({...n,measured:measurements[n.id],data:{...n.data,inspected:n.id===selectedId,inspect:()=>setSelected(n.id)}}));
  // Controlled nodes must retain measured dimensions reported by React Flow.
  // Event-only updates leave this geometry unchanged and preserve user zoom.
  const geometryKey=nodes.map(n=>`${n.id}:${n.measured?.width || 0}:${n.measured?.height || 0}`).join('|');
  function recordMeasurements(changes){
    const sizes=changes.filter(c=>c.type==='dimensions' && Number.isFinite(c.dimensions?.width) && Number.isFinite(c.dimensions?.height));
    if(!sizes.length)return;
    setMeasurements(previous=>{
      let next=previous;
      for(const size of sizes){if(previous[size.id]?.width!==size.dimensions.width || previous[size.id]?.height!==size.dimensions.height){if(next===previous)next={...previous};next[size.id]=size.dimensions;}}
      return next;
    });
  }
  const step=inspected?.data;
  const status=graph.complete ? 'Complete':graph.active ? graph.working ? `${graph.nodes.find(n=>n.id===graph.working).data.title} working`:graph.coordinating ? 'Coordinating':'Waiting':run.status==='cancelled' ? 'Cancelled':'Stopped';
  function collapse(){setExpanded(false);setSelected(null);requestAnimationFrame(()=>toggle.current?.focus());}
  return <section ref={host} className={`vds-workflow route-${graph.route} ${expanded ? 'is-expanded':'is-status'}`} aria-label={expanded ? 'Agent map':'Agent activity status'} role={expanded ? 'dialog':undefined} aria-modal={expanded ? true:undefined}>
    {expanded ? <div className="vds-flow-heading"><div><span className="vds-flow-eyebrow">ORCHESTRATION MAP</span><h4>Orchestrator & specialists</h4></div><div className="vds-flow-heading-actions"><span className={`vds-flow-state ${graph.active ? 'is-live':''}`} role="status">{status}</span><button ref={toggle} type="button" className="secondary vds-expand" onClick={collapse} aria-expanded="true">Close map</button></div></div>:
      null}

    {expanded ? <>
      <p className="vds-coordination-note">{run.question}<br/>Arrows show parent–child coordination. The activity timeline records execution order.</p>
      <div className="vds-flow-canvas" aria-label="Pan and zoom the analysis flow">
        <ReactFlow nodes={nodes} onNodesChange={recordMeasurements} edges={graph.edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={{padding:compact ? .18:.12,maxZoom:1}} minZoom={.3} maxZoom={1.6} panOnDrag zoomOnPinch
          nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} nodesFocusable={false} edgesFocusable={false}
          deleteKeyCode={null} selectionOnDrag={false} selectNodesOnDrag={false} zoomOnScroll={false} zoomOnDoubleClick={false} preventScrolling={false}
          onNodeClick={(_,node)=>setSelected(node.id)} ariaLabelConfig={{'controls.zoomIn.ariaLabel':'Zoom in on analysis flow','controls.zoomOut.ariaLabel':'Zoom out of analysis flow','controls.fitView.ariaLabel':'Fit analysis flow to view'}}>
          <FitLayout route={graph.route} compact={compact} geometryKey={geometryKey}/>
          <Background gap={22} size={1} color="#c6d3cb"/><Controls showInteractive={false} orientation="horizontal" position="top-left"/>
        </ReactFlow>
        {graph.route==='planning' && <p className="vds-route-pending">The orchestrator will reveal the analysis path after planning.</p>}
      </div>
    </>:<div className="vds-status-bar"><div className="vds-status-hierarchy" role="group" aria-label="Orchestrator and its selected capabilities">
      <StatusPoint node={graph.nodes[0]} selected={selectedId} inspect={setSelected} scope={scope}/>
      {graph.nodes.length>1 && <div className="vds-status-children" role="group" aria-label="Coordinated by Orchestrator">{graph.nodes.slice(1).map(node=><StatusPoint key={node.id} node={node} selected={selectedId} inspect={setSelected} scope={scope}/>)}</div>}
    </div><span className="vds-status-announcement" role="status">{status}</span><button ref={toggle} type="button" className="vds-map-toggle" onClick={()=>setExpanded(true)} aria-expanded="false" aria-label="Agent map" title={status+' · Open agent map'}>Map <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5 6 7.5 9 4.5"/></svg></button></div>}
    {(expanded || selectedId) && <div className="vds-flow-detail" aria-label="Selected step details"><div className="vds-detail-heading"><span className={`vds-detail-icon kind-${step.kind.toLowerCase()}`}><Icon name={step.icon}/></span><div><strong>{step.title}</strong><span>{step.kind} · {step.statusLabel}{step.duration ? ` · ${step.duration}`:''}{step.attempt>1 ? ` · attempt ${step.attempt}`:''}</span></div>{selectedId && <button type="button" className="secondary" onClick={()=>setSelected(null)}>Follow activity</button>}</div><p>{step.description}</p>{step.coordinator && <p className="vds-detail-time">Coordinated by {step.coordinator}</p>}{step.planningStatus && <p className="vds-detail-time">Planning: {step.planningStatus}{step.planningDuration ? ` · ${step.planningDuration}`:''}</p>}
      {step.startedAt && <p className="vds-detail-time">Started {new Date(step.startedAt*1000).toLocaleTimeString()}{step.finishedAt ? ` · Last recorded ${new Date(step.finishedAt*1000).toLocaleTimeString()}`:''}</p>}
      <p className="vds-flow-hint">Select a step to inspect it. Open the agent map for parent–child relationships and pan/zoom controls.</p>
    </div>}
  </section>;
}
const roots=new WeakMap();
window.vdsWorkflow={
  render(run,element){if(!element)return;let root=roots.get(element);if(!root){root=createRoot(element);roots.set(element,root);}root.render(<Workflow run={run}/>);},
  dispose(element){const root=roots.get(element);if(root){root.unmount();roots.delete(element);}}
};
