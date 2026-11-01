import {test} from 'node:test';
import assert from 'node:assert/strict';
import {graphFor,duration,outerBranchPath} from '../frontend/workflow/model.mjs';

test('an undecided route shows only the orchestrator without inventing downstream progress',()=>{
  const graph=graphFor({status:'running',events:[{stage:'planner',status:'started',sequence:1,timestamp:123}]});
  assert.equal(graph.route,'planning');assert.equal(graph.nodes.length,1);assert.equal(graph.edges.length,0);
  assert.equal(graph.working,'planner');assert.equal(graph.nodes[0].data.finishedAt,null);
});
test('quick routes omit deep agents and use only recorded completion/duration',()=>{
  const graph=graphFor({plan:{tier:'quick'},status:'running',events:[{stage:'planner',status:'completed',duration_ms:2500,sequence:2},{stage:'query',status:'started',sequence:3,timestamp:123}]});
  assert.deepEqual(graph.nodes.map(n=>n.id),['planner','query','numerical_checks','publication']);
  assert.equal(graph.nodes[0].data.planningDuration,'2.5s');assert.equal(graph.nodes[0].data.status,'coordinating');assert.equal(graph.nodes[2].data.status,'queued');
  assert.equal(graph.edges.filter(e=>e.animated).length,1);
  assert.equal(graph.edges.find(e=>e.animated).target,'query');
});
test('deep repair attempts respect sequence ordering and keep the latest stage state',()=>{
  const graph=graphFor({plan:{tier:'deep'},status:'running',events:[
    {stage:'analyst',status:'started',attempt:2,sequence:6,timestamp:130},
    {stage:'analyst',status:'completed',attempt:1,sequence:4,duration_ms:500},
    {stage:'analyst',status:'started',attempt:1,sequence:3,timestamp:120}
  ]});
  assert.equal(graph.nodes.length,6);
  const analyst=graph.nodes.find(n=>n.id==='analyst').data;
  assert.equal(analyst.status,'started');assert.equal(analyst.attempt,2);assert.equal(analyst.startedAt,130);assert.equal(analyst.duration,null);
});
test('terminal runs stop stale working highlights without completing untouched steps',()=>{
  for(const status of ['cancelled','failed','interrupted']){
    const graph=graphFor({plan:{tier:'deep'},status,events:[{stage:'interpreter',status:'started',sequence:5}]});
    assert.equal(graph.working,null);assert.equal(graph.edges.some(e=>e.animated),false);
    assert.equal(graph.nodes.find(n=>n.id==='interpreter').data.status,'interrupted');
    assert.equal(graph.nodes.find(n=>n.id==='reviewer').data.status,'unrecorded');
  }
});
test('legacy routes can be recovered from evidence; invalid durations are not fabricated',()=>{
  assert.equal(graphFor({status:'succeeded',events:[{stage:'query',status:'completed'}]}).route,'quick');
  assert.equal(graphFor({status:'succeeded',events:[{stage:'interpreter',status:'completed'}]}).route,'deep');
  for(const value of [null,undefined,NaN,-1])assert.equal(duration(value),null);
  assert.equal(duration(0),'0s');
});


test('every selected role or tool is a child of the orchestrator, on wide and compact maps',()=>{
  for(const route of ['quick','deep'])for(const compact of [true,false]){
    const graph=graphFor({plan:{tier:route},status:'running',events:[]},{compact});
    const root=graph.nodes.find(n=>n.id==='planner'),children=graph.nodes.filter(n=>n.id!=='planner');
    assert.equal(graph.edges.length,children.length);
    for(const child of children){
      const inbound=graph.edges.filter(e=>e.target===child.id);
      assert.equal(inbound.length,1);assert.equal(inbound[0].source,'planner');
      assert.ok(child.position.y>root.position.y);
      assert.equal(child.targetPosition,'top');assert.equal(child.data.coordinator,'Orchestrator');
      assert.equal(child.data.hasOutput,false);
      assert.equal(child.data.step,undefined);
    }
    assert.equal(root.sourcePosition,'bottom');assert.equal(root.data.hasInput,false);
    if(compact)assert.ok(Math.max(...graph.nodes.map(n=>n.position.x+n.style.width))<500);
  }
});

test('planning completion does not complete the coordinator while a child is working',()=>{
  const run={plan:{tier:'deep'},status:'running',created_at:100,events:[
    {stage:'planner',status:'completed',sequence:2,duration_ms:2500},
    {stage:'interpreter',status:'started',sequence:5,timestamp:105}
  ]};
  const graph=graphFor(run),root=graph.nodes[0].data;
  assert.equal(root.status,'coordinating');assert.equal(root.planningStatus,'Complete');assert.equal(root.duration,null);
  assert.equal(graph.working,'interpreter');
  assert.deepEqual(graph.edges.filter(e=>e.animated).map(e=>[e.source,e.target]),[['planner','interpreter']]);
  run.status='succeeded';run.events.push({stage:'analysis',status:'completed',sequence:14,duration_ms:12000,timestamp:112});
  const completed=graphFor(run).nodes[0].data;
  assert.equal(completed.status,'completed');assert.equal(completed.duration,'12s');assert.equal(completed.planningDuration,'2.5s');
});

test('outer parent branches remain finite and terminate at the child handle',()=>{
  for(const rail of [-34,730]){
    const path=outerBranchPath(348,100,rail<0 ? 98:598,380,rail);
    assert.ok(path.startsWith('M 348 100'));assert.ok(path.endsWith(`L ${rail<0 ? 98:598} 380`));
    assert.ok(!/NaN|Infinity/.test(path));
    assert.ok(path.includes(String(rail)));
  }
});


test('persistent mini map keeps every child on one compact row and preserves parent edges',()=>{
  for(const compact of [true,false]){
    const graph=graphFor({plan:{tier:'deep'},status:'running',events:[{stage:'interpreter',status:'started',sequence:1}]},{compact,mini:true});
    assert.equal(graph.nodes[0].position.y,0);
    assert.ok(graph.nodes.slice(1).every(n=>n.position.y===60&&n.style.width<=108));
    assert.ok(graph.edges.every(e=>e.source==='planner'&&e.data.railX===null));
    assert.equal(graph.edges.find(e=>e.animated).target,'interpreter');
    const width=Math.max(...graph.nodes.map(n=>n.position.x+n.style.width));assert.ok(width<=(compact?342:604));
  }
});
