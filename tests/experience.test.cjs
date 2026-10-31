const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const context={window:{},Number,JSON};
vm.runInNewContext(fs.readFileSync('static/experience.js','utf8'),context);
const ui=context.window.vdsExperience;

test('legacy runs still produce a figure and palettes preserve exact values',()=>{
  const result={series:[{month:'2025-01',value:10},{month:'2025-02',value:20}],forecast:[{month:'2025-03',value:25}]};
  const visual=ui.figures(result)[0];
  for(const palette of Object.keys(ui.palettes)){
    const fig=ui.styled(visual,palette);
    assert.deepEqual(Array.from(fig.data[0].y),[10,20]);
    assert.equal(fig.data[1].line.dash,'dash');
    assert.equal(fig.layout.colorway[0],ui.palettes[palette].colors[0]);
  }
  assert.equal(visual.figure.data[0].marker,undefined);
});

test('unknown chart types and invalid numeric evidence are rejected',()=>{
  for(const data of [{type:'html',x:['a'],y:[1]},{type:'scatter',x:['a'],y:[NaN]},{type:'scatter',x:['a'],y:[]}]){
    assert.throws(()=>ui.styled({id:'x',figure:{data:[data],layout:{}}}));
  }
});
