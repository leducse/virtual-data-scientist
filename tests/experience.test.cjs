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

test('Plotly figures preserve sparse dates, numeric axes and scatter markers',()=>{
  const visual={id:'test',figure:{data:[{type:'scatter',mode:'markers',name:'Actual',x:[1,2],y:[1.1,2.1]}],layout:{xaxis:{title:'Actual'}}}};
  const fig=ui.styled(visual,'accessible');
  assert.deepEqual(Array.from(fig.data[0].x),[1,2]);assert.equal(fig.data[0].mode,'markers');
  assert.equal(fig.layout.xaxis.title.text,'Actual');assert.equal(fig.layout.hovermode,'closest');
});
test('heatmaps validate matrix dimensions and discard executable/remote layout properties',()=>{
  const visual={id:'confusion',figure:{data:[{type:'heatmap',x:['a','b'],y:['a','b'],z:[[2,1],[0,3]]}],layout:{images:[{source:'https://untrusted.invalid'}],updatemenus:[{}]}}};
  const fig=ui.styled(visual);assert.equal(fig.data[0].z[1][1],3);assert.equal(fig.layout.images,undefined);assert.equal(fig.layout.updatemenus,undefined);
  visual.figure.data[0].z=[[1]];assert.throws(()=>ui.styled(visual));
});

test('run details identify actual source, estimators, partitions and recorded cloud duration',()=>{
  const dataset={name:'wine.csv',profile:{rows:178},sha256:'source',parquet_sha256:'prepared',public_dataset:{title:'Wine cultivars',synthetic:false}};
  const run={result:{task:'classification',candidates:{dummy:.33,linear:.95,tree:.92},split:{train:Array(106),validation:Array(36),test:Array(36)},execution:'agentcore_code_interpreter',evidence:{source_sha256:'source',parquet_sha256:'prepared'},timing_ms:{end_to_end:11369.12}}};
  const receipt=ui.receipt(run,dataset);
  assert.equal(receipt.sourceKind,'Public dataset');assert.equal(receipt.rows,178);assert.equal(receipt.seconds,11.36912);
  assert.deepEqual(Array.from(receipt.models),['DummyClassifier baseline','LogisticRegression','RandomForestClassifier']);
  assert.equal(receipt.partition,'Training 106 / validation 36 / test 36');assert.equal(receipt.hashesMatch,true);
  dataset.parquet_sha256='another-input';assert.equal(ui.receipt(run,dataset).hashesMatch,false);
});

test('run details distinguish synthetic gallery examples, arbitrary uploads and missing evidence',()=>{
  const run={result:{}};
  assert.equal(ui.receipt(run,{public_dataset:{synthetic:true}}).sourceKind,'Synthetic teaching example');
  assert.equal(ui.receipt(run,{name:'synthetic-in-name.csv'}).sourceKind,'Uploaded file');
  const missing=ui.receipt(run);
  assert.equal(missing.sourceKind,'Source not recorded');assert.equal(missing.execution,'Execution not recorded');
  assert.equal(missing.hashesMatch,null);assert.equal(missing.seconds,null);assert.equal(missing.models.length,0);
});

test('cluster settings are not described as unrelated fitted classifiers',()=>{
  const receipt=ui.receipt({result:{task:'clustering',candidates:{2:.8,3:.9,4:.7},projection:{},selected_method:'kmeans'}},{profile:{rows:178}});
  assert.equal(receipt.comparison,'3 cluster settings compared');assert.equal(receipt.models.length,2);
  assert.equal(receipt.models[0],'KMeans (k = 2, 3, 4)');assert.equal(receipt.models[1],'PCA for the chart projection');
  assert.equal(receipt.partition,'Exploratory fit on all usable input rows; no predictive holdout');
});
