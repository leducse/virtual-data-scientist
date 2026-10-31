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
  async function exportFigure(visual,palette,kind,element) {
    const fig=styled(visual,palette), name=visual.id;
    if(kind==="png" || kind==="svg")return window.Plotly.downloadImage(element,{format:kind,filename:name,width:1200,height:650,scale:2});
    if(kind==="json")return save(name+".json",JSON.stringify(fig,null,2),"application/json");
    if(kind==="python"){
      const encoded=JSON.stringify(JSON.stringify(fig));
      return save(name+".py",`import json\nimport plotly.graph_objects as go\n\nfigure = go.Figure(json.loads(${encoded}))\nfigure.write_html('${name}.html', include_plotlyjs=True)\nfigure.show()\n`);
    }
    if(kind==="html"){
      const response=await fetch("/static/vendor/plotly-basic-2.32.0.min.js");
      if(!response.ok)throw new Error("Chart export library unavailable.");
      const library=(await response.text()).replaceAll("</script", "<\\/script");
      const payload=JSON.stringify(fig).replaceAll("<","\\u003c");
      save(name+".html",`<!doctype html><meta charset="utf-8"><title>Saved analytical figure</title><div id="chart"></div><script>${library}</script><script>const figure=${payload};Plotly.newPlot('chart',figure.data,figure.layout,{responsive:true,displaylogo:false});</script>`,"text/html");
    }
  }
  return {palettes,figures,styled,save,exportFigure};
})();
