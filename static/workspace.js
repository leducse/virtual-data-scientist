"use strict";
const $ = (s) => document.querySelector(s);
const escape = (v) => String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");
const state = {datasets:[],runs:[],selected:localStorage.getItem("vds_dataset"),timer:null,busy:false};
const active = (r) => ["queued","running","reviewing"].includes(r.status);
const format = (v) => typeof v === "number" ? new Intl.NumberFormat("en-US",{maximumFractionDigits:3}).format(v) : String(v ?? "");
async function api(path, body) {
  const response = await window.vdsAuth.request(path,body);
  const result = await response.json();
  if (!response.ok) {const e = new Error(result.error?.message || "Request failed."); e.details = result.error?.details; throw e;}
  return result;
}
function notice(text,error=false) {$("#notice").innerHTML = text ? `<p class="notice ${error ? "error" : ""}">${escape(text)}</p>` : "";}
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
  $("#analyze").disabled=!d || state.busy;
  const runs=state.runs.filter(r=>r.dataset_id===state.selected);
  $("#runs").innerHTML=runs.length ? runs.map(renderRun).join("") : '<p class="muted">Your results, methods, and checks will appear here.</p>';
  updateRoute();
}
function chart(result,id) {
  if(!result.series?.length) return "";
  const historical=result.series, future=result.forecast || [];
  const all=[...historical,...future];
  const values=all.map(r=>r.value), lo=Math.min(0,...values), hi=Math.max(...values), range=hi-lo || 1;
  const x=(i)=>65+i*625/Math.max(1,all.length-1), y=(v)=>218-(v-lo)*178/range;
  const points=(rows,offset)=>rows.map((r,i)=>`${x(i+offset).toFixed(2)},${y(r.value).toFixed(2)}`).join(" ");
  const forecast=future.length ? [historical.at(-1),...future] : [];
  const labels=[...new Set([0,Math.floor((all.length-1)/2),all.length-1])];
  return `<svg class="chart" viewBox="0 0 720 265" role="img" aria-labelledby="chart-${id}"><title id="chart-${id}">Monthly ${escape(result.chart?.units)}. Solid line: observed values. Dashed line: forecast. Exact values in the table below.</title>${[0,.5,1].map(f=>{const v=lo+f*range;return `<line x1="65" x2="690" y1="${y(v)}" y2="${y(v)}" stroke="#e8eee6"/><text x="55" y="${y(v)+4}" text-anchor="end" font-size="10" fill="#617366">${escape(format(v))}</text>`;}).join("")}<polyline points="${points(historical,0)}" fill="none" stroke="#146659" stroke-width="2.5"/>${forecast.length ? `<polyline points="${points(forecast,historical.length-1)}" fill="none" stroke="#be8635" stroke-width="2.5" stroke-dasharray="6 4"/>` : ""}${all.map((r,i)=>`<circle cx="${x(i)}" cy="${y(r.value)}" r="3" fill="${i<historical.length ? "#146659" : "#be8635"}"><title>${escape(r.month)}: ${escape(format(r.value))}</title></circle>`).join("")}${labels.map(i=>`<text x="${x(i)}" y="245" text-anchor="middle" font-size="10" fill="#617366">${escape(all[i].month)}</text>`).join("")}</svg><div class="legend"><span>Observed</span>${future.length ? '<span class="forecast">Forecast · no calibrated interval</span>' : ""}</div><details><summary>Exact values</summary><div class="table-wrap"><table><thead><tr><th scope="col">Month</th><th scope="col">Value</th><th scope="col">Kind</th></tr></thead><tbody>${all.map((r,i)=>`<tr><td>${escape(r.month)}</td><td>${escape(format(r.value))}</td><td>${i<historical.length ? "Observed" : "Forecast"}</td></tr>`).join("")}</tbody></table></div></details>`;
}
function renderRun(r) {
  const result=r.result;
  return `<article class="run"><div class="run-heading"><h3>${escape(r.question)}</h3><span class="status ${escape(r.status)}">${escape(r.status)}</span></div><p class="meta">${escape(r.plan?.tier || "planning")} · version ${r.dataset_id.slice(0,8)} · ${new Date(r.created_at*1000).toLocaleString()} · trace ${r.id.slice(0,8)}</p>${result ? `<p>${escape(result.summary)}</p>${result.independent_review ? `<p class="muted">Independent review: ${result.independent_review.decision === "accept" ? "accepted the checked result" : escape(result.independent_review.decision)}.</p>` : ""}${chart(result,r.id)}<p class="muted">${escape(result.execution)} · ${escape(format(result.timing_ms?.end_to_end))} ms end to end · numerical review ${result.review?.passed ? "passed" : "pending"}</p>${(result.warnings || []).map(w=>`<p class="warning">${escape(w)}</p>`).join("")}<div class="evidence-actions"><button class="secondary" data-download="${r.id}">Download evidence</button></div><details><summary>Plan, methods & numerical checks</summary><pre>${escape(JSON.stringify({plan:r.plan,review:result.review,independent_review:result.independent_review,candidates:result.candidates,test:result.test,sql:result.sql,versions:result.versions},null,2))}</pre></details>` : `<p>${escape(r.error?.message || r.stage)}</p>${r.result_available ? `<button class="secondary" data-open="${r.id}">Open saved result</button>` : ""}${active(r) ? `<button class="secondary" data-cancel="${r.id}">Cancel job</button>` : ""}`}</article>`;
}
function updateRoute(){$("#route-note").textContent=state.cloud ? "AgentCore chooses and executes the analysis" : "Automatically inferred from your data and question";}
async function refresh(initial=false){
  const previous=new Map(state.runs.map(r=>[r.id,r.status]));
  const result=await api("workspace"); state.datasets=result.datasets; state.runs=result.runs; state.cloud=result.cloud_enabled;
  $("#execution-badge").textContent=state.cloud ? "AWS AGENTCORE · DEVELOPMENT" : "LOCAL WORKSPACE";
  $("#execution-title").textContent=state.cloud ? "Running on AWS" : "Local verification mode";
  $("#execution-description").textContent=state.cloud ? "Your data and evidence are saved in AWS for seven days in this development environment. The data scientist prepares, analyzes and checks the results." : "This server is in local verification mode. The hosted application uses AgentCore for planning and execution.";
  if(initial || !selected()) choose(selected()?.id || state.datasets[0]?.id || ""); else render();
  const completed=state.runs.find(r=>["queued","running","reviewing"].includes(previous.get(r.id)) && !active(r));
  if(completed) notice(completed.status==="succeeded" ? "Analysis complete. The result and its evidence are saved." : completed.error?.message || completed.stage, completed.status!=="succeeded");
  clearTimeout(state.timer);if(state.runs.some(active)) state.timer=setTimeout(()=>refresh().catch(e=>notice(e.message,true)),1000);
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
  }catch(e){notice(e.message,true);}finally{state.busy=false;$("#analyze").disabled=!selected();}
});
$("#datasets").addEventListener("click",async e=>{
  const select=e.target.closest("[data-select]");if(select){choose(select.dataset.select);return;}
  const del=e.target.closest("[data-delete]");if(!del)return;
  if(!confirm("Delete this dataset version, source, Parquet, and every linked analysis?"))return;
  try{await api(`datasets/${del.dataset.delete}/delete`,{});await refresh(true);notice("Dataset and its linked results deleted.");}catch(e){notice(e.message,true);}
});
$("#runs").addEventListener("click",async e=>{
  const open=e.target.closest("[data-open]");
  if(open){try {const run=(await api(`runs/${open.dataset.open}`)).run;state.runs=state.runs.map(r=>r.id===run.id ? run : r);render();} catch(error){notice(error.message,true);}return;}
  const cancel=e.target.closest("[data-cancel]");
  if(cancel){try{await api(`runs/${cancel.dataset.cancel}/cancel`,{});await refresh();}catch(e){notice(e.message,true);}return;}
  const download=e.target.closest("[data-download]");if(!download)return;
  let run;
  try {run=(await api(`runs/${download.dataset.download}`)).run;} catch(error) {notice(error.message,true);return;}
  const url=URL.createObjectURL(new Blob([JSON.stringify(run,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download=`analysis-${run.id.slice(0,8)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
document.querySelectorAll("[data-question]").forEach(button=>button.addEventListener("click",()=>{$("#question").value=button.dataset.question;$("#question").focus();}));
window.vdsAuth.ready.then(signedIn=>signedIn && refresh(true)).catch(e=>notice(e.message,true));
