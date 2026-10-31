import React,{memo,useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ReactFlow,Background,Controls,Handle,Position,useNodesInitialized,useReactFlow,useStore} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './view.css';
import {graphFor} from './model.mjs';

const paths={orchestrator:'M12 5v5M6 19v-4h12v4M6 15v-2h12v2M12 10v3',analyst:'M4 18h16M5 14l4-4 4 2 6-7',query:'M4 5h16v14H4zM4 10h16M10 5v14',interpreter:'M4 5h16v14H4zM7 9l3 3-3 3M13 15h4',checks:'M12 3l8 4v6c0 4-8 8-8 8s-8-4-8-8V7zM8 12l3 3 5-6',reviewer:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM9 12a3 3 0 106 0 3 3 0 10-6 0',publication:'M5 3h10l4 4v14H5zM14 3v5h5M8 13h8M8 17h6'};
const Icon=({name})=><svg viewBox="0 0 24 24" width="21" height="21" aria-hidden="true"><path d={paths[name]} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>{name==='orchestrator' && <><circle cx="12" cy="4" r="2" fill="currentColor"/><circle cx="6" cy="20" r="2" fill="currentColor"/><circle cx="18" cy="20" r="2" fill="currentColor"/></>}</svg>;
const StepNode=memo(function StepNode({data,sourcePosition,targetPosition}){
  return <div className={`vds-flow-card is-${data.status} kind-${data.kind.toLowerCase()} ${data.inspected ? 'is-inspected':''}`}>
    {data.hasInput && <Handle type="target" position={targetPosition || Position.Left} isConnectable={false}/>}
    <button type="button" className="vds-node-button nodrag" onClick={data.inspect} aria-pressed={data.inspected} aria-label={`${data.title}: ${data.statusLabel}. Inspect step ${data.step}.`}>
      <span className="vds-node-top"><span className="vds-node-icon"><Icon name={data.icon}/></span><span className="vds-node-kind">{data.kind}</span><span className="vds-node-number">{String(data.step).padStart(2,'0')}</span></span>
      <strong>{data.title}</strong>
      <span className="vds-node-bottom"><span className="vds-state-dot"/>{data.statusLabel}<span className="vds-node-time">{data.duration || (data.status==='started' ? 'In progress':'')}{data.attempt>1 ? ` · attempt ${data.attempt}`:''}</span></span>
    </button>
    {data.hasOutput && <Handle type="source" position={sourcePosition || Position.Right} isConnectable={false}/>}
  </div>;
});
const nodeTypes={activity:StepNode};
function FitLayout({route,compact}){
  const ready=useNodesInitialized(),width=useStore(s=>s.width),height=useStore(s=>s.height),{fitView}=useReactFlow();
  useEffect(()=>{if(ready && width && height)void fitView({padding:compact ? .18:.12,maxZoom:1,duration:0});},[ready,width,height,route,compact,fitView]);
  return null;
}
function Workflow({run}){
  const host=useRef(null),[compact,setCompact]=useState(()=>window.innerWidth<760);
  useEffect(()=>{const observer=new ResizeObserver(entries=>setCompact(entries[0].contentRect.width<500));observer.observe(host.current);return ()=>observer.disconnect();},[]);
  const graph=graphFor(run,{compact}),[selected,setSelected]=useState(null),[expanded,setExpanded]=useState(false);
  const selectedId=graph.nodes.some(n=>n.id===selected) ? selected:null;
  const inspected=graph.nodes.find(n=>n.id===(selectedId || graph.working || 'planner'));
  const nodes=graph.nodes.map(n=>({...n,data:{...n.data,inspected:n.id===selectedId,inspect:()=>setSelected(n.id)}}));
  const step=inspected?.data;
  return <section ref={host} className={`vds-workflow ${expanded ? 'is-expanded':''}`} aria-label="Agent activity flow">
    <div className="vds-flow-heading"><div><span className="vds-flow-eyebrow">ANALYSIS FLOW</span><h4>Your team at work</h4></div><div className="vds-flow-heading-actions"><span className={`vds-flow-state ${graph.active ? 'is-live':''}`} role="status">{graph.complete ? 'Complete':graph.active ? graph.working ? `${graph.nodes.find(n=>n.id===graph.working).data.title} working`:'Waiting':run.status==='cancelled' ? 'Cancelled':'Stopped'}</span><button type="button" className="secondary vds-expand" onClick={()=>setExpanded(v=>!v)} aria-expanded={expanded}>{expanded ? 'Compact view':'Larger view'}</button></div></div>
    <div className="vds-flow-canvas" aria-label="Pan and zoom the analysis flow">
      <ReactFlow nodes={nodes} edges={graph.edges} nodeTypes={nodeTypes} fitView fitViewOptions={{padding:compact ? .18:.12,maxZoom:1}} minZoom={.3} maxZoom={1.6}
        nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} nodesFocusable={false} edgesFocusable={false}
        deleteKeyCode={null} selectionOnDrag={false} selectNodesOnDrag={false} zoomOnScroll={false} zoomOnDoubleClick={false} preventScrolling={false}
        onNodeClick={(_,node)=>setSelected(node.id)} ariaLabelConfig={{'controls.zoomIn.ariaLabel':'Zoom in on analysis flow','controls.zoomOut.ariaLabel':'Zoom out of analysis flow','controls.fitView.ariaLabel':'Fit analysis flow to view'}}>
        <FitLayout route={graph.route} compact={compact}/>
        <Background gap={22} size={1} color="#c6d3cb"/>
        <Controls showInteractive={false} orientation="horizontal" position="bottom-left"/>
      </ReactFlow>
      {graph.route==='planning' && <p className="vds-route-pending">The orchestrator will reveal the analysis path after planning.</p>}
    </div>
    <div className="vds-flow-detail" aria-label="Selected step details"><div className="vds-detail-heading"><span className={`vds-detail-icon kind-${step.kind.toLowerCase()}`}><Icon name={step.icon}/></span><div><strong>{step.title}</strong><span>{step.kind} · {step.statusLabel}{step.duration ? ` · ${step.duration}`:''}{step.attempt>1 ? ` · attempt ${step.attempt}`:''}</span></div>{selectedId && <button type="button" className="secondary" onClick={()=>setSelected(null)}>Follow activity</button>}</div><p>{step.description}</p>
      {step.startedAt && <p className="vds-detail-time">Started {new Date(step.startedAt*1000).toLocaleTimeString()}{step.finishedAt ? ` · Last recorded ${new Date(step.finishedAt*1000).toLocaleTimeString()}`:''}</p>}
      <p className="vds-flow-hint">Select a step to inspect it. Drag the canvas to explore; use + / − or Fit to change the view.</p>
    </div>
  </section>;
}
const roots=new WeakMap();
window.vdsWorkflow={
  render(run,element){if(!element)return;let root=roots.get(element);if(!root){root=createRoot(element);roots.set(element,root);}root.render(<Workflow run={run}/>);},
  dispose(element){const root=roots.get(element);if(root){root.unmount();roots.delete(element);}}
};
