import {test} from 'node:test';
import assert from 'node:assert/strict';
import {graphFor,duration} from '../frontend/workflow/model.mjs';

test('an undecided route shows only the orchestrator without inventing downstream progress',()=>{
  const graph=graphFor({status:'running',events:[{stage:'planner',status:'started',sequence:1,timestamp:123}]});
  assert.equal(graph.route,'planning');assert.equal(graph.nodes.length,1);assert.equal(graph.edges.length,0);
  assert.equal(graph.working,'planner');assert.equal(graph.nodes[0].data.finishedAt,null);
});
test('quick routes omit deep agents and use only recorded completion/duration',()=>{
  const graph=graphFor({plan:{tier:'quick'},status:'running',events:[{stage:'planner',status:'completed',duration_ms:2500,sequence:2},{stage:'query',status:'started',sequence:3,timestamp:123}]});
  assert.deepEqual(graph.nodes.map(n=>n.id),['planner','query','numerical_checks','publication']);
  assert.equal(graph.nodes[0].data.duration,'2.5s');assert.equal(graph.nodes[2].data.status,'queued');
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


test('compact layout keeps two columns and directs every handoff toward the next card',()=>{
  const graph=graphFor({plan:{tier:'deep'},status:'running',events:[]},{compact:true});
  assert.equal(new Set(graph.nodes.map(n=>n.position.x)).size,2);
  assert.ok(Math.max(...graph.nodes.map(n=>n.position.x+n.style.width))<500);
  for(const edge of graph.edges){
    const source=graph.nodes.find(n=>n.id===edge.source),target=graph.nodes.find(n=>n.id===edge.target);
    if(source.position.y===target.position.y){
      const direction=target.position.x>source.position.x ? 'right':'left';
      assert.equal(source.sourcePosition,direction);
      assert.equal(target.targetPosition,direction==='right' ? 'left':'right');
    }else{
      assert.ok(target.position.y>source.position.y);
      assert.equal(source.sourcePosition,'bottom');assert.equal(target.targetPosition,'top');
    }
  }
});
