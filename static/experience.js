"use strict";
window.vdsExperience=(()=>{
  const palettes={decision:{label:"Teal & gold",colors:["#146659","#a66b16","#6d5f94","#346b96"]},ocean:{label:"Ocean",colors:["#155f99","#008578","#b35b26","#78499a"]},plum:{label:"Plum & amber",colors:["#79417f","#b56a00","#147a72","#446da0"]},accessible:{label:"Blue & orange",colors:["#0072b2","#d55e00","#009e73","#8b4b8a"]}};
  const LIBRARY='/static/vendor/plotly-cartesian-4.2.0.min.js', LICENSE='/static/vendor/plotly-4.2.0-LICENSE.txt';
  let loading;
  const clean=value=>String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  function loadPlotly(){
    if(window.Plotly)return Promise.resolve(window.Plotly);
    if(!loading)loading=new Promise((resolve,reject)=>{
      const script=document.createElement('script');script.src=LIBRARY;script.async=true;
      script.onload=()=>window.Plotly ? resolve(window.Plotly):reject(new Error('Chart engine did not load.'));
      script.onerror=()=>{script.remove();loading=null;reject(new Error('Chart engine unavailable. Reload to retry.'));};document.head.append(script);
    });
    return loading;
  }
  function figures(result){
    if(result.visuals?.length)return result.visuals;
    if(!result.series?.length)return [];
    const trace=(name,rows)=>({type:'scatter',mode:'lines+markers',name,x:rows.map(r=>r.month),y:rows.map(r=>r.value)});
    const data=[trace('Observed',result.series)];
    if(result.forecast?.length)data.push({...trace('Forecast',[result.series.at(-1),...result.forecast]),line:{dash:'dash'}});
    return [{id:'history',title:'Monthly history',purpose:'Observed values and saved forecast.',figure:{data,layout:{yaxis:{title:result.chart?.units || 'Source units'}}}}];
  }
  function values(array,numeric=false){
    if(!Array.isArray(array)||array.length>1200||array.some(v=>numeric ? !Number.isFinite(v):!((typeof v==='string'&&v.length<=200)||Number.isFinite(v))))throw new Error('Invalid figure data.');
    return array.map(v=>typeof v==='string' ? clean(v):v);
  }
  function styled(visual,palette='decision'){
    const source=visual.figure;if(!Array.isArray(source?.data)||source.data.length>30)throw new Error('Invalid figure.');
    const colors=(palettes[palette]||palettes.decision).colors;
    const data=source.data.map((t,i)=>{
      if(!['scatter','bar','heatmap','box','histogram'].includes(t.type))throw new Error('Unsupported chart type.');
      const trace={type:t.type,name:clean(t.name),marker:{color:colors[i%colors.length],size:6}};
      if(t.type==='heatmap'){
        trace.x=values(t.x);trace.y=values(t.y);
        if(trace.x.length>50||trace.y.length>50||!Array.isArray(t.z)||t.z.length!==trace.y.length||t.z.some(row=>!Array.isArray(row)||row.length!==trace.x.length||row.some(v=>!Number.isFinite(v))))throw new Error('Invalid heatmap evidence.');
        trace.z=t.z.map(row=>row.slice());trace.colorscale='Viridis';trace.showscale=true;delete trace.marker;
        trace.hovertemplate='%{y} / %{x}<br>%{z:,.3f}<extra></extra>';
      }else{
        trace.y=values(t.y,true);
        if(t.x!==undefined){trace.x=values(t.x);if(trace.x.length!==trace.y.length)throw new Error('Invalid figure data.');}
        if(t.type==='scatter'||t.type==='bar'){
          if(!trace.x)throw new Error('Figure x values are missing.');
          if(t.type==='scatter'){trace.mode=['markers','lines','lines+markers'].includes(t.mode)?t.mode:'lines+markers';trace.line={color:colors[i%colors.length],width:2.5,dash:['dash','dot','dashdot'].includes(t.line?.dash)?t.line.dash:'solid'};trace.connectgaps=false;}
        }
        trace.hovertemplate='%{x}<br>%{y:,.3f}<extra>%{fullData.name}</extra>';
      }
      return trace;
    });
    const layout={autosize:true,height:350,margin:{l:68,r:32,t:35,b:80},paper_bgcolor:'#ffffff',plot_bgcolor:'#ffffff',colorway:colors,
      font:{family:'system-ui, sans-serif',color:'#263b33'},legend:{orientation:'h',y:-.22},uirevision:visual.id,
      hovermode:data.some(t=>t.type==='scatter'&&t.mode!=='markers')?'x unified':'closest'};
    for(const key of ['xaxis','yaxis']){
      const axis=source.layout?.[key]||{},title=typeof axis.title==='object'?axis.title?.text:axis.title;
      layout[key]={automargin:true,gridcolor:'#e6ece8',title:{text:clean(title || '')}};
      if(['category','date','linear','log'].includes(axis.type))layout[key].type=axis.type;
      if(Array.isArray(axis.range)&&axis.range.length===2&&axis.range.every(Number.isFinite))layout[key].range=axis.range.slice();
    }
    return {data,layout};
  }
  const config={responsive:true,displaylogo:false,scrollZoom:false,modeBarButtonsToRemove:['toImage']};
  async function render(visual,palette,element){
    const epoch=element.vdsEpoch=(element.vdsEpoch || 0)+1,fig=styled(visual,palette),Plotly=await loadPlotly();
    if(element.vdsEpoch!==epoch||element.isConnected===false)return;
    await Plotly.react(element,fig.data,fig.layout,config);
    if(element.vdsEpoch!==epoch||element.isConnected===false){Plotly.purge(element);return;}
    element.setAttribute('role','img');element.setAttribute('aria-label',`${visual.title}. ${visual.purpose || ''} Exact values follow this figure.`);
    if(!element.vdsResize){element.vdsResize=new ResizeObserver(()=>{if(element.isConnected)Plotly.Plots.resize(element);});element.vdsResize.observe(element);}
    return element;
  }
  function dispose(element){element.vdsEpoch=(element.vdsEpoch||0)+1;element.vdsResize?.disconnect();delete element.vdsResize;if(window.Plotly&&element.data)window.Plotly.purge(element);}
  function save(name,body,type='text/plain'){
    const url=URL.createObjectURL(new Blob([body],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function workflow(run,element){if(window.vdsWorkflow)window.vdsWorkflow.render(run,element);else if(element)element.textContent='Recorded activity is available in the timeline.';}
  function disposeWorkflow(element){window.vdsWorkflow?.dispose(element);}
  async function exportFigure(visual,palette,kind,element){
    const fig=styled(visual,palette),name=visual.id.replace(/[^a-z0-9_-]/gi,'_');
    if(kind==='svg'||kind==='png'){
      const Plotly=await loadPlotly();if(!element?.data)throw new Error('Open this figure before exporting.');
      const url=await Plotly.toImage(element,{format:kind,width:1400,height:700});const a=document.createElement('a');a.href=url;a.download=name+'.'+kind;a.click();return;
    }
    if(kind==='json')return save(name+'.plotly.json',JSON.stringify(fig,null,2),'application/json');
    if(kind==='javascript')return save(name+'.js',`// Figure recreation. Use the full analysis bundle to train and evaluate models.\n// npm install plotly.js-cartesian-dist-min@4.2.0\nimport Plotly from 'plotly.js-cartesian-dist-min';\nconst figure=${JSON.stringify(fig,null,2)};\nPlotly.newPlot(document.getElementById('chart'),figure.data,figure.layout,{responsive:true,displaylogo:false});\n`);
    if(kind==='python')return save(name+'.py',`# Figure recreation. The full analysis notebook contains model fitting and evaluation.\nimport json\nimport plotly.graph_objects as go\n\nfigure=go.Figure(json.loads(${JSON.stringify(JSON.stringify(fig))}))\nfigure.write_html('${name}.html',include_plotlyjs=True)\nfigure.show()\n`);
    if(kind==='html'){
      const [libraryResponse,licenseResponse]=await Promise.all([fetch(LIBRARY),fetch(LICENSE)]);
      if(!libraryResponse.ok||!licenseResponse.ok)throw new Error('Offline figure resources unavailable.');
      const library=(await libraryResponse.text()).replace(/<\/script/gi,'<\\/script'),license=(await licenseResponse.text()).replaceAll('--','- -');
      const payload=JSON.stringify(fig).replaceAll('<','\\u003c');
      save(name+'.html',`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Saved analytical figure</title><div id="chart" style="width:100%;min-height:450px;height:85vh"></div><script>${library}</script><script>const figure=${payload};Plotly.newPlot('chart',figure.data,figure.layout,{responsive:true,displaylogo:false});</script><!-- Plotly MIT license\n${license}\n--></html>`,'text/html');
    }
  }
  return {palettes,figures,styled,render,dispose,workflow,disposeWorkflow,save,exportFigure,loadPlotly};
})();
