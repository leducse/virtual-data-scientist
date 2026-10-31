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

test('ECharts adapter preserves sparse dates and isolates categorical validation from linked time views',()=>{
  const history={id:'test',figure:{data:[{type:'scatter',name:'Observed',x:['2025-01','2025-03'],y:[1,3]},{type:'scatter',name:'Forecast',x:['2025-04'],y:[4],line:{dash:'dash'}}],layout:{}}};
  const option=ui.option(history,'accessible');
  assert.equal(option.xAxis.type,'time');
  assert.deepEqual(Array.from(option.series[0].data,p=>p[1]),[1,3]);
  assert.equal(option.series[1].lineStyle.type,'dashed');
  assert.equal(option.tooltip.renderMode,'richText');
  assert.equal(option.aria.enabled,true);
  assert.equal(ui.option({id:'validation',figure:{data:[{type:'bar',name:'MAE',x:['naive','holt'],y:[2,1]}],layout:{}}}).xAxis.type,'category');
});
