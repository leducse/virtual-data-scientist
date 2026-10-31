"use strict";
// Reviewed figure data only; no model-produced JavaScript is evaluated.
window.vdsExperience = (() => {
  const palettes = {
    decision:{name:"Teal & gold",colors:["#146659","#a66b16","#6d5f94","#346b96"]},
    ocean:{name:"Ocean",colors:["#155f99","#008578","#b35b26","#78499a"]},
    plum:{name:"Plum & amber",colors:["#79417f","#b56a00","#147a72","#446da0"]},
    accessible:{name:"Blue & orange",colors:["#0072b2","#d55e00","#009e73","#8b4b8a"]}
  };
  const cleanText = (value) => String(value ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
  function figures(result) {
    if(result.visuals?.length) return result.visuals;
    if(!result.series?.length) return [];
    const rows=result.series, future=result.forecast || [];
    const trace=(name,values)=>({type:"scatter",mode:"lines+markers",name,x:values.map(r=>r.month),y:values.map(r=>r.value)});
    const data=[trace("Observed",rows)];
    if(future.length)data.push({...trace("Forecast",[rows.at(-1),...future]),line:{dash:"dash"}});
    return [{id:"history",title:"Monthly history",purpose:"Observed values and any saved forecast.",figure:{data,layout:{yaxis:{title:result.chart?.units || "Source units"}}}}];
  }
  function styled(visual,palette="decision") {
    const fig=JSON.parse(JSON.stringify(visual.figure));
    const colors=(palettes[palette] || palettes.decision).colors;
    fig.data.forEach((trace,i)=>{
      if(!["scatter","bar"].includes(trace.type))throw new Error("Unsupported chart type.");
      if(!Array.isArray(trace.x) || !Array.isArray(trace.y) || trace.x.length!==trace.y.length || trace.x.length>1200 || trace.y.some(y=>!Number.isFinite(y))) throw new Error("Invalid figure data.");
      trace.name=cleanText(trace.name);
      trace.marker={color:colors[i%colors.length],size:6};
      trace.line={...(trace.line || {}),color:colors[i%colors.length],width:2.5};
      trace.hovertemplate="%{x}<br>%{y:,.3f}<extra>%{fullData.name}</extra>";
    });
    fig.layout={...fig.layout,colorway:colors,autosize:true,height:340,margin:{l:65,r:20,t:24,b:65},
      paper_bgcolor:"#ffffff",plot_bgcolor:"#ffffff",font:{family:"system-ui, sans-serif",color:"#263b33"},
      legend:{orientation:"h",y:-.25},uirevision:visual.id,hovermode:"x unified"};
    for(const axis of ["xaxis","yaxis"]){
      fig.layout[axis]={...(fig.layout[axis] || {}),automargin:true,gridcolor:"#e6ece8"};
      if(fig.layout[axis].title)fig.layout[axis].title=cleanText(fig.layout[axis].title);
    }
    return fig;
  }
  function save(name,body,type="text/plain") {
    const url=URL.createObjectURL(new Blob([body],{type})), a=document.createElement("a");
    a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function option(visual,palette="decision") {
    const fig=styled(visual,palette),temporal=fig.data.every(t=>t.x.every(x=>/^\d{4}-\d{2}(-\d{2})?$/.test(String(x))));
    const categories=[...new Set(fig.data.flatMap(t=>t.x.map(String)))];
    return {useUTC:true,color:(palettes[palette] || palettes.decision).colors,animation:false,
      aria:{enabled:true,decal:{show:true},label:{description:String(visual.title)+". "+String(visual.purpose || "")+". "+fig.data.map(t=>String(t.name)+": "+t.y.length+" values, from "+t.x[0]+" to "+t.x.at(-1)).join(". ")}},backgroundColor:"#ffffff",
      tooltip:{trigger:"axis",renderMode:"richText",confine:true,axisPointer:{type:"cross"}},
      legend:{bottom:0,type:"scroll"},grid:{left:70,right:22,top:28,bottom:95},
      toolbox:{right:12,feature:{dataZoom:{yAxisIndex:"none"},restore:{}}},
      xAxis:{type:temporal ? "time":"category",...(temporal ? {}:{data:categories}),name:"",axisLabel:{hideOverlap:true}},
      yAxis:{type:"value",name:String(visual.figure.layout?.yaxis?.title || "Value"),nameLocation:"middle",nameGap:54,scale:!fig.data.some(t=>t.type==="bar")},
      dataZoom:[{type:"inside",filterMode:"none",zoomOnMouseWheel:"ctrl"},{type:"slider",bottom:32,height:18,filterMode:"none"}],
      series:fig.data.map(t=>({name:String(t.name).replaceAll("&lt;","<").replaceAll("&gt;",">").replaceAll("&amp;","&"),
        type:t.type==="bar" ? "bar":"line",showSymbol:true,symbolSize:6,connectNulls:false,
        lineStyle:{width:2.5,type:t.line?.dash==="dash" ? "dashed":"solid"},
        data:t.x.map((x,i)=>[temporal ? Date.parse(String(x).length===7 ? x+"-01T00:00:00Z":x+"T00:00:00Z") : String(x),t.y[i]])}))};
  }
  function render(visual,palette,element,group){
    const chart=window.echarts.getInstanceByDom(element) || window.echarts.init(element,null,{renderer:"svg"});
    chart.setOption(option(visual,palette),{notMerge:true});
    if(group && chart.getOption().xAxis[0].type==="time"){chart.group=group;window.echarts.connect(group);}
    if(!element.vdsResize){element.vdsResize=new ResizeObserver(()=>chart.resize());element.vdsResize.observe(element);}
    return chart;
  }
  function dispose(element){element.vdsResize?.disconnect();window.echarts?.getInstanceByDom(element)?.dispose();}
  function workflow(run,element){
    if(window.vdsWorkflow)window.vdsWorkflow.render(run,element);
    else if(element)element.textContent='Recorded progress is available in the activity timeline.';
  }
  function disposeWorkflow(element){window.vdsWorkflow?.dispose(element);}
  async function exportFigure(visual,palette,kind,element) {
    const fig=styled(visual,palette),options=option(visual,palette),name=visual.id.replace(/[^a-z0-9_-]/gi,"_");
    if(kind==="svg" || kind==="png"){
      const chart=window.echarts.getInstanceByDom(element);if(!chart)throw new Error("Open this chart before exporting.");
      const svg=chart.renderToSVGString();
      if(kind==="svg")return save(name+".svg",svg,"image/svg+xml");
      const url=URL.createObjectURL(new Blob([svg],{type:"image/svg+xml"}));
      try{const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=url;});
        const canvas=document.createElement("canvas");canvas.width=1800;canvas.height=Math.round(1800*element.clientHeight/element.clientWidth);
        canvas.getContext("2d").drawImage(img,0,0,canvas.width,canvas.height);
        const blob=await new Promise(resolve=>canvas.toBlob(resolve,"image/png"));if(!blob)throw new Error("PNG export unavailable.");return save(name+".png",blob,"image/png");
      }finally{URL.revokeObjectURL(url);}
    }
    if(kind==="json")return save(name+".echarts.json",JSON.stringify(options,null,2),"application/json");
    if(kind==="javascript")return save(name+".js",`// npm install echarts@6.1.0\nimport * as echarts from 'echarts';\nconst option = ${JSON.stringify(options,null,2)};\nconst chart = echarts.init(document.getElementById('chart'), null, {renderer:'svg'});\nchart.setOption(option);\nnew ResizeObserver(() => chart.resize()).observe(chart.getDom());\n`);
    if(kind==="python"){
      const encoded=JSON.stringify(JSON.stringify(fig));
      return save(name+".py",`import json\nimport plotly.graph_objects as go\n\nfigure = go.Figure(json.loads(${encoded}))\nfigure.write_html('${name}.html', include_plotlyjs=True)\nfigure.show()\n`);
    }
    if(kind==="html"){
      const response=await fetch("/static/vendor/echarts-6.1.0.min.js");if(!response.ok)throw new Error("Chart export library unavailable.");
      const licenseResponse=await fetch("/static/vendor/echarts-6.1.0-LICENSE.txt");
      const noticeResponse=await fetch("/static/vendor/echarts-6.1.0-NOTICE.txt");
      if(!licenseResponse.ok || !noticeResponse.ok)throw new Error("Chart export license unavailable.");
      const license=((await licenseResponse.text())+"\n"+(await noticeResponse.text())).replaceAll("--","- -");
      const library=(await response.text()).replace(/<\/script/gi,"<\\/script"),payload=JSON.stringify(options).replaceAll("<","\\u003c");
      save(name+".html",`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Saved analytical figure</title><div id="chart" style="width:100%;height:80vh;min-height:400px"></div><script>${library}</script><script>const chart=echarts.init(document.getElementById('chart'),null,{renderer:'svg'});chart.setOption(${payload});new ResizeObserver(()=>chart.resize()).observe(chart.getDom());</script><!-- Apache ECharts license and NOTICE\n${license}\n--></html>`,"text/html");
    }
  }
  return {palettes,figures,styled,option,render,dispose,workflow,disposeWorkflow,save,exportFigure};
})();
