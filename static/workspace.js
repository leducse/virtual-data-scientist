"use strict";
const $ = (s) => document.querySelector(s);
const escape = (v) => String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");
const state = {datasets:[],runs:[],selected:localStorage.getItem("vds_dataset"),timer:null,busy:false,palette:localStorage.getItem("vds_palette") || "decision"};
const experience=window.vdsExperience;
const streams=new Map(), reconnectAt=new Map();
const active = (r) => ["queued","running","reviewing"].includes(r.status);
const format = (v) => typeof v === "number" ? new Intl.NumberFormat("en-US",{maximumFractionDigits:3}).format(v) : String(v ?? "");
async function api(path, body) {
  const response = await window.vdsAuth.request(path,body);
  const result = await response.json();
  if (!response.ok) {const e = new Error(result.error?.message || "Request failed."); e.details = result.error?.details; e.code=result.error?.code; throw e;}
  return result;
}
function notice(text,error=false) {$("#notice").innerHTML = text ? `<p class="notice ${error ? "error" : ""}">${escape(text)}</p>` : "";}
window.vdsSpeech.init(api,notice);
function selected() {return state.datasets.find(d=>d.id===state.selected);}
function choose(id) {
  state.selected=id; localStorage.setItem("vds_dataset",id);
  const previous=state.runs.find(r=>r.dataset_id===id);
  $("#question").value=previous?.question || "";
  render();
}
function render() {
  const d=selected();
  $("#dataset-count").textContent=`${state.datasets.length} versions`;
  $("#datasets").innerHTML=state.datasets.map(d=>`<div class="dataset"><button type="button" class="${d.id===state.selected ? "selected" : ""}" data-select="${d.id}" aria-pressed="${d.id===state.selected}">${escape(d.name)}<small>${d.profile.rows.toLocaleString()} rows · ${d.profile.columns.length} columns · ${d.id.slice(0,8)}</small></button><button type="button" class="delete" data-delete="${d.id}" aria-label="Delete ${escape(d.name)} and its analyses">×</button></div>`).join("");
  const date = d?.profile.columns.find(c=>c.role==="time");
  $("#profile").innerHTML=d ? `<strong>${escape(d.name)}</strong> · ${d.profile.rows.toLocaleString()} records ready for analysis<p class="muted" style="margin-top:8px">${date?.min ? `Observed dates: ${escape(date.min)} to ${escape(date.max)}. ` : ""}Data preparation and field detection completed automatically.</p><details><summary>Data preparation notes</summary><div class="chips">${d.profile.columns.map(c=>`<span class="chip">${escape(c.name)} · ${escape(c.type)}${c.missing ? ` · ${c.missing} missing` : ""}</span>`).join("")}</div><p class="muted" style="margin-top:8px">Version ${d.id.slice(0,8)} · source preserved · preparation ${format(d.timing_ms.ingestion)} ms</p></details>` : "<p>Upload a business dataset and ask your question. Its structure will be detected automatically.</p>";
  const suggestions=d?.experience;
  $("#recommendations").hidden=!suggestions;
  $("#recommendations").innerHTML=suggestions ? `<h2>Good questions for this data</h2><p class="muted">Based on the profile. Choose a question to edit it; analysis starts only when you press Run.</p><div class="suggestion-grid">${suggestions.suggestions.map(s=>`<article><span class="eyebrow">${escape(s.effort)}</span><h3>${escape(s.question)}</h3><p>${escape(s.why)}</p><button class="secondary" type="button" data-suggestion="${escape(s.id)}">Use this question →</button>${learning(s.methods)}</article>`).join("")}</div>${suggestions.notes.map(n=>`<p class="warning">${escape(n)}</p>`).join("")}` : "";
  $("#analyze").disabled=!d || state.busy || state.allowance?.remaining===0;
  const runs=state.runs.filter(r=>r.dataset_id===state.selected);
  const container=$("#runs");
  if(!runs.length)container.innerHTML='<p class="muted">Your results, methods, and checks will appear here.</p>';
  else {
    if(!container.querySelector("article"))container.replaceChildren();
    const ids=new Set(runs.map(r=>r.id));
    container.querySelectorAll("article.run").forEach(node=>{if(!ids.has(node.dataset.run))node.remove();});
    for(const [index,r] of runs.entries()){
      const html=renderRun(r), old=container.querySelector(`[data-run="${r.id}"]`);
      if(old?.dataset.rendered===html)continue;
      const holder=document.createElement("div");holder.innerHTML=html;const node=holder.firstElementChild;node.dataset.rendered=html;
      if(old)old.replaceWith(node);else container.insertBefore(node,container.children[index] || null);
      renderPlots(r,node);
    }
  }
  updateRoute();
}
function learning(methods) {
  if(!methods?.length)return "";
  return `<details class="learning"><summary>How this works · learn the methods</summary>${methods.map(m=>`<section><h4>${escape(m.title)}</h4>${m.disposition ? `<p class="method-choice">${escape(m.disposition)}</p>` : ""}<p>${escape(m.what)}</p><dl><dt>When to use</dt><dd>${escape(m.when)}</dd><dt>Limitations</dt><dd>${escape(m.avoid)}</dd><dt>How we check it</dt><dd>${escape(m.checks)}</dd></dl><p class="muted">${escape(m.example)}</p><a href="${escape(m.reference)}" target="_blank" rel="noopener noreferrer">Technical reference ↗</a></section>`).join("")}</details>`;
}
function chart(result,id) {
  const visuals=experience.figures(result);
  return visuals.map((v,i)=>`<section class="visual"><h4>${escape(v.title)}</h4><p class="muted">${escape(v.purpose)}${v.split ? ` · ${escape(v.split)} data` : ""}</p><div class="plot" id="plot-${id}-${i}" aria-label="${escape(v.title)}"></div><div class="figure-actions">${["png","svg","html","json","python"].map(kind=>`<button class="secondary" data-figure-run="${id}" data-figure-index="${i}" data-figure-kind="${kind}" type="button">${{png:"PNG",svg:"SVG",html:"Interactive HTML",json:"Figure JSON",python:"Python code"}[kind]}</button>`).join("")}</div><details><summary>Exact chart values</summary><div class="table-wrap"><table><thead><tr><th>Series</th><th>Period / method</th><th>Value</th></tr></thead><tbody>${v.figure.data.flatMap(t=>t.x.map((x,j)=>`<tr><td>${escape(t.name)}</td><td>${escape(x)}</td><td>${escape(format(t.y[j]))}</td></tr>`)).join("")}</tbody></table></div></details></section>`).join("");
}
async function renderPlots(run,node) {
  if(!run.result)return;
  try{
    for(const [i,v] of experience.figures(run.result).entries()){
      const fig=experience.styled(v,state.palette), element=node.querySelector(`#plot-${run.id}-${i}`);
      await window.Plotly.react(element,fig.data,fig.layout,{responsive:true,displaylogo:false,scrollZoom:false,toImageButtonOptions:{format:"png",filename:v.id,width:1200,height:650,scale:2}});
    }
  }catch(error){notice("A chart could not render. Its exact values and evidence remain available.",true);}
}
function activity(run) {
  const events=run.events || [];
  if(!events.length)return "";
  const latest=new Map(events.map(e=>[e.stage,e]));
  const stages=run.plan?.tier==="quick" ? [["planner","Orchestrator","agent"],["query","Data query","tool"],["numerical_checks","Numerical checks","check"],["publication","Results","output"]] : [["planner","Orchestrator","agent"],["analyst","Analyst","agent"],["interpreter","Code Interpreter","tool"],["numerical_checks","Numerical checks","check"],["reviewer","Reviewer","agent"],["publication","Results","output"]];
  return `<div class="activity" aria-label="Analysis activity"><ol class="flow-nodes">${stages.map(([key,label,kind])=>{const e=latest.get(key), status=e?.status || (active(run) ? "queued" : "skipped");return `<li class="flow-node ${status}" aria-current="${status==="started" ? "step" : "false"}"><small>${kind}</small><strong>${label}</strong><span>${status==="started" ? "Working" : status}${e?.duration_ms!==undefined ? ` · ${format(e.duration_ms/1000)}s` : ""}</span></li>`;}).join("")}</ol><details><summary>Activity timeline</summary><ol class="timeline">${events.map(e=>`<li>${new Date(e.timestamp*1000).toLocaleTimeString()} · ${escape(e.stage.replaceAll("_"," "))} · ${escape(e.status)}${e.attempt>1 ? ` · attempt ${e.attempt}` : ""}</li>`).join("")}</ol></details></div>`;
}
function renderRun(r) {
  const result=r.result;
  return `<article class="run" data-run="${r.id}"><div class="run-heading"><h3>${escape(r.question)}</h3><span class="status ${escape(r.status)}">${escape(r.status)}</span></div><p class="meta">${escape(r.plan?.tier || "planning")} · version ${r.dataset_id.slice(0,8)} · ${new Date(r.created_at*1000).toLocaleString()} · trace ${r.id.slice(0,8)}</p>${activity(r)}${result ? `<p>${escape(result.summary)}</p>${result.independent_review ? `<p class="muted">Independent review: ${result.independent_review.decision === "accept" ? "accepted the checked result" : escape(result.independent_review.decision)}.</p>` : ""}${chart(result,r.id)}${learning(result.methodology)}<p class="muted">${escape(result.execution)} · ${escape(format(result.timing_ms?.end_to_end))} ms end to end · numerical review ${result.review?.passed ? "passed" : "pending"}</p>${(result.warnings || []).map(w=>`<p class="warning">${escape(w)}</p>`).join("")}<div class="evidence-actions"><button class="secondary" data-download="${r.id}">Full evidence JSON</button>${r.bundle_key ? `<button class="secondary" data-bundle="${r.id}">Download code, notebook & data tables ↓</button><button class="secondary" data-prepared="${r.id}">Prepared data (Parquet)</button>` : ""}</div><details><summary>Plan, methods & numerical checks</summary><pre>${escape(JSON.stringify({plan:r.plan,review:result.review,independent_review:result.independent_review,candidates:result.candidates,test:result.test,sql:result.sql,versions:result.versions},null,2))}</pre></details>` : `<p>${escape(r.error?.message || r.stage)}</p>${r.result_available ? `<button class="secondary" data-open="${r.id}">Open saved result</button>` : ""}${active(r) ? `<button class="secondary" data-cancel="${r.id}">Cancel job</button>` : ""}`}</article>`;
}
function updateRoute(){$("#route-note").textContent=state.cloud ? "AgentCore chooses and executes the analysis" : "Automatically inferred from your data and question";}
async function refresh(initial=false){
  const previous=new Map(state.runs.map(r=>[r.id,r.status]));
  const result=await api("workspace"); state.datasets=result.datasets; state.runs=result.runs; state.cloud=result.cloud_enabled; state.streaming=result.streaming_enabled;
  state.allowance=result.allowance;
  window.vdsSpeech.available(result.speech_enabled===true);
  $("#allowance").textContent=state.allowance ? `${state.allowance.remaining} of ${state.allowance.limit} analyses available${state.allowance.kind==="guest" ? " · guest trial" : ""}` : "";
  if(initial && window.vdsClaimError)notice(window.vdsClaimError,true);
  $("#execution-badge").textContent=state.cloud ? "AWS AGENTCORE · DEVELOPMENT" : "LOCAL WORKSPACE";
  $("#execution-title").textContent=state.cloud ? "Running on AWS" : "Local verification mode";
  $("#execution-description").textContent=state.cloud ? "Your data and evidence are saved in AWS for seven days in this development environment. The data scientist prepares, analyzes and checks the results." : "This server is in local verification mode. The hosted application uses AgentCore for planning and execution.";
  if(initial || !selected()) choose(selected()?.id || state.datasets[0]?.id || ""); else render();
  const completed=state.runs.find(r=>["queued","running","reviewing"].includes(previous.get(r.id)) && !active(r));
  if(completed) notice(completed.status==="succeeded" ? "Analysis complete. The result and its evidence are saved." : completed.error?.message || completed.stage, completed.status!=="succeeded");
  clearTimeout(state.timer);
  if(window.vdsAuth.hosted() && state.streaming){
    for(const r of state.runs.filter(active))if(!streams.has(r.id) && Date.now()>(reconnectAt.get(r.id) || 0))streamRun(r.id);
  }
  if(state.runs.some(r=>active(r) && !streams.has(r.id)))state.timer=setTimeout(()=>refresh().catch(e=>notice(e.message,true)),1500);
}
async function streamRun(runId){
  const controller=new AbortController();streams.set(runId,controller);
  let reader;
  try{
    const {ticket}=await api("stream-tickets",{run_id:runId});
    const run=state.runs.find(r=>r.id===runId), after=run?.events?.at(-1)?.sequence || 0;
    const response=await window.vdsAuth.request("events/stream",{ticket,after},controller.signal);
    if(!response.ok || !response.body)throw new Error("Progress stream unavailable.");
    reader=response.body.getReader();const decoder=new TextDecoder();let pending="";
    while(true){
      const {done,value}=await reader.read();if(done)break;pending+=decoder.decode(value,{stream:true});
      if(pending.length>3*1024*1024)throw new Error("Progress response exceeded its limit.");
      let boundary;
      while((boundary=pending.indexOf("\n\n"))>=0){
        const block=pending.slice(0,boundary);pending=pending.slice(boundary+2);
        const type=block.split("\n").find(l=>l.startsWith("event: "))?.slice(7), data=block.split("\n").find(l=>l.startsWith("data: "))?.slice(6);
        if(!type || !data)continue;const event=JSON.parse(data), current=state.runs.find(r=>r.id===runId);
        if(type==="stage" && current){current.events=current.events || [];if(!current.events.some(e=>e.id===event.id))current.events.push(event);render();}
        if(type==="finished" || type==="unavailable"){await reader.cancel();return;}
      }
    }
  }catch(error){if(error.name!=="AbortError")reconnectAt.set(runId,Date.now()+22000);}
  finally{
    reader?.releaseLock();streams.delete(runId);
    clearTimeout(state.timer);state.timer=setTimeout(()=>refresh().catch(e=>notice(e.message,true)),1000);
  }
}
$("#upload-form").addEventListener("submit",async e=>{
  e.preventDefault();const file=$("#file").files[0];if(!file)return;
  if(file.size>10*1024*1024){notice("Choose a file up to 10 MiB.",true);return;}
  $("#upload").disabled=true;notice("Reading and profiling your dataset…");
  try{
    let result;
    if(window.vdsAuth.hosted()) {
      const upload=await api("uploads",{name:file.name,size:file.size});
      const form=new FormData();Object.entries(upload.post.fields).forEach(([key,value])=>form.append(key,value));form.append("file",file);
      const stored=await fetch(upload.post.url,{method:"POST",body:form});
      if(!stored.ok) throw new Error("The file upload did not complete. Try again.");
      result=await api("datasets",{upload_id:upload.upload_id,name:file.name,question:$("#question").value});
    } else {
      const bytes=new Uint8Array(await file.arrayBuffer());let binary="";for(let i=0;i<bytes.length;i+=8192) binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      result=await api("datasets",{name:file.name,content_base64:btoa(binary),question:$("#question").value});
    }
    await refresh();choose(result.dataset.id);notice("Your data is prepared. Ask your business question.");
  }catch(e){notice(e.message,true);}
  finally{$("#upload").disabled=false;}
});
$("#analysis-form").addEventListener("submit",async e=>{
  e.preventDefault();if(!selected())return;state.busy=true;$("#analyze").disabled=true;notice("Planning your analysis…");
  try{
    const result=await api("runs",{dataset_id:state.selected,request_key:crypto.randomUUID(),question:$("#question").value});
    await refresh();notice(result.run.status==="succeeded" ? "Result saved with its evidence." : result.run.status==="failed" ? result.run.error.message : "Background job started. You can refresh this page and keep the result.",result.run.status==="failed");
  }catch(e){notice(e.message,true);}finally{state.busy=false;$("#analyze").disabled=!selected() || state.allowance?.remaining===0;}
});
$("#datasets").addEventListener("click",async e=>{
  const select=e.target.closest("[data-select]");if(select){choose(select.dataset.select);return;}
  const del=e.target.closest("[data-delete]");if(!del)return;
  if(!confirm("Delete this dataset version, source, Parquet, and every linked analysis?"))return;
  try{await api(`datasets/${del.dataset.delete}/delete`,{});await refresh(true);notice("Dataset and its linked results deleted.");}catch(e){notice(e.message,true);}
});
$("#runs").addEventListener("click",async e=>{
  const figure=e.target.closest("[data-figure-run]");
  if(figure){try{const run=state.runs.find(r=>r.id===figure.dataset.figureRun), i=Number(figure.dataset.figureIndex);await experience.exportFigure(experience.figures(run.result)[i],state.palette,figure.dataset.figureKind,$(`#plot-${run.id}-${i}`));}catch(error){notice(error.message,true);}return;}
  const bundle=e.target.closest("[data-bundle]");
  const prepared=e.target.closest('[data-prepared]');
  if(bundle || prepared){try{const result=await api(prepared ? `runs/${prepared.dataset.prepared}/prepared-data` : `runs/${bundle.dataset.bundle}/artifacts?palette=${encodeURIComponent(state.palette)}`);const a=document.createElement("a");a.href=result.url;a.rel="noreferrer";a.click();}catch(error){notice(error.message,true);}return;}
  const open=e.target.closest("[data-open]");
  if(open){try {const run=(await api(`runs/${open.dataset.open}`)).run;state.runs=state.runs.map(r=>r.id===run.id ? run : r);render();} catch(error){notice(error.message,true);}return;}
  const cancel=e.target.closest("[data-cancel]");
  if(cancel){try{await api(`runs/${cancel.dataset.cancel}/cancel`,{});await refresh();}catch(e){notice(e.message,true);}return;}
  const download=e.target.closest("[data-download]");if(!download)return;
  let run;
  try {run=(await api(`runs/${download.dataset.download}`)).run;} catch(error) {notice(error.message,true);return;}
  const url=URL.createObjectURL(new Blob([JSON.stringify(run,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download=`analysis-${run.id.slice(0,8)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$("#recommendations").addEventListener("click",e=>{const button=e.target.closest("[data-suggestion]");if(!button)return;const suggestion=selected()?.experience?.suggestions.find(s=>s.id===button.dataset.suggestion);if(suggestion){notice('');$("#question").value=suggestion.question;$("#question").focus();}});
$("#palette").value=state.palette in experience.palettes ? state.palette : "decision";
$("#palette").addEventListener("change",async e=>{state.palette=e.target.value;localStorage.setItem("vds_palette",state.palette);for(const r of state.runs.filter(r=>r.dataset_id===state.selected && r.result))await renderPlots(r,$(`[data-run="${r.id}"]`));});
window.vdsAuth.ready.then(signedIn=>signedIn && refresh(true)).catch(e=>notice(e.message,true));
