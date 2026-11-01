"use strict";
const $ = (s) => document.querySelector(s);
const escape = (v) => String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");
const state = {datasets:[],runs:[],selected:localStorage.getItem("vds_dataset"),timer:null,busy:false,focusRun:null,draftFile:null,palette:localStorage.getItem("vds_palette") || "decision"};
const experience=window.vdsExperience, drafts=window.vdsDrafts;
let intent=drafts.read();
if(intent)$("#question").value=intent.question || "";
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
  state.focusRun=null;
  render();
}
function disposeRun(node){
  node.querySelectorAll('.plot').forEach(experience.dispose);
  node.querySelectorAll('.workflow-map').forEach(experience.disposeWorkflow);
}
function render() {
  const d=selected();
  if(d && !state.drawerInitialized){$(".data-drawer").open=false;state.drawerInitialized=true;}
  $("#dataset-count").textContent=`${state.datasets.length} versions`;
  $("#datasets").innerHTML=state.datasets.map(d=>`<div class="dataset"><button type="button" class="${d.id===state.selected ? "selected" : ""}" data-select="${d.id}" aria-pressed="${d.id===state.selected}">${escape(d.name)}<small>${d.profile.rows.toLocaleString()} rows · ${d.profile.columns.length} columns · ${d.id.slice(0,8)}</small></button><button type="button" class="delete" data-delete="${d.id}" aria-label="Delete ${escape(d.name)} and its analyses">×</button></div>`).join("");
  const date = d?.profile.columns.find(c=>c.role==="time");
  $("#profile").innerHTML=d ? `<strong>${escape(d.name)}</strong> · ${d.profile.rows.toLocaleString()} records ready for analysis<p class="muted" style="margin-top:8px">${date?.min ? `Observed dates: ${escape(date.min)} to ${escape(date.max)}. ` : ""}Data preparation and field detection completed automatically.</p><details><summary>Data preparation notes</summary><div class="chips">${d.profile.columns.map(c=>`<span class="chip">${escape(c.name)} · ${escape(c.type)}${c.missing ? ` · ${c.missing} missing` : ""}</span>`).join("")}</div><p class="muted" style="margin-top:8px">Version ${d.id.slice(0,8)} · source preserved · preparation ${format(d.timing_ms.ingestion)} ms</p></details>` : "<p>Upload a business dataset and ask your question. Its structure will be detected automatically.</p>";
  const suggestions=d?.experience;
  $("#recommendations").hidden=!suggestions;
  $("#recommendations").innerHTML=suggestions ? `<details ${state.runs.some(r=>r.dataset_id===state.selected) ? "":"open"}><summary>Suggested analyses for this data</summary><h2 style="margin-top:14px">Good questions for this data</h2><p class="muted">Based on the profile. Choose a question to edit it; analysis starts only when you press Send.</p><div class="suggestion-grid">${suggestions.suggestions.map(s=>`<article><span class="eyebrow">${escape(s.effort)}</span><h3>${escape(s.question)}</h3><p>${escape(s.why)}</p><button class="secondary" type="button" data-suggestion="${escape(s.id)}">Use this question →</button>${learning(s.methods)}</article>`).join("")}</div>${suggestions.notes.map(n=>`<p class="warning">${escape(n)}</p>`).join("")}</details>` : "";
  $("#analyze").disabled=state.busy || (!d && !state.draftFile && !$("#file").files[0] && !(state.selected && !window.vdsAuth.authenticated())) || (window.vdsAuth.authenticated() && state.allowance?.can_submit===false);
  const history=state.runs.filter(r=>r.dataset_id===state.selected);
  if($("#preview-status")){
    $("#preview-status").hidden=state.allowance?.can_submit!==false;
    $("#preview-status").textContent="Your remaining preview allowance cannot cover another analysis. Saved results and downloads remain available.";
  }
  renderConversation(history);
  const runs=history.filter(r=>r.id===(state.focusRun || history[0]?.id));
  const container=$("#runs");
  if(!runs.length){container.querySelectorAll("article.run").forEach(disposeRun);container.innerHTML='<p class="muted">Your results, methods, and checks will appear here.</p>';}
  else {
    if(!container.querySelector("article"))container.replaceChildren();
    const ids=new Set(runs.map(r=>r.id));
    container.querySelectorAll("article.run").forEach(node=>{if(!ids.has(node.dataset.run)){disposeRun(node);node.remove();}});
    for(const [index,r] of runs.entries()){
      const html=renderRun(r), old=container.querySelector(`[data-run="${r.id}"]`);
      if(old?.dataset.rendered===html)continue;
      const holder=document.createElement("div");holder.innerHTML=html;const node=holder.firstElementChild;node.dataset.rendered=html;
      if(old){
        const previousFlow=old.querySelector('.workflow-map'),nextFlow=node.querySelector('.workflow-map');
        if(previousFlow && nextFlow)nextFlow.replaceWith(previousFlow);
        disposeRun(old);old.replaceWith(node);
      }else container.insertBefore(node,container.children[index] || null);
      renderPlots(r,node);
    }
  }
  const monitored=state.runs.find(active) || runs[0];
  $('#agent-monitor').hidden=!monitored;
  if(monitored){$('#agent-monitor-title').textContent=monitored.question;experience.workflow(monitored,$('#agent-map'));}
  else experience.disposeWorkflow($('#agent-map'));
  updateRoute();
}
function renderConversation(history){
  const conversation=$("#conversation"),nearBottom=conversation.scrollHeight-conversation.scrollTop-conversation.clientHeight<80;
  const content=history.slice().reverse().map(r=>`<article class="chat-turn ${r.id===(state.focusRun || history[0]?.id) ? "current":""}"><p class="chat-user">${escape(r.question)}</p><div class="chat-assistant"><strong>Data scientist · ${escape(r.status)}</strong><p>${escape(r.result?.summary || r.error?.message || r.stage || "Planning your analysis…")}</p><button type="button" class="secondary" data-result="${r.id}">${r.result ? "Explore visuals & evidence":"View agent activity"} →</button></div></article>`).join("") || '<p class="chat-welcome">Upload a table, ask a question, then build on the result. I’ll prepare the data and check the analysis.</p>';
  if(conversation.dataset.rendered!==content){conversation.innerHTML=content;conversation.dataset.rendered=content;if(nearBottom)conversation.scrollTop=conversation.scrollHeight;}
  $("#attachment-note").textContent=state.draftFile ? `Attached: ${state.draftFile.name} · saved through sign-in` : selected() ? `Using ${selected().name} · follow up in your own words` : "Attach a file or choose a prepared dataset. Fields are detected automatically.";
}
function learning(methods) {
  if(!methods?.length)return "";
  return `<details class="learning"><summary>How this works · learn the methods</summary>${methods.map(m=>`<section><h4>${escape(m.title)}</h4>${m.disposition ? `<p class="method-choice">${escape(m.disposition)}</p>` : ""}<p>${escape(m.what)}</p><dl><dt>When to use</dt><dd>${escape(m.when)}</dd><dt>Limitations</dt><dd>${escape(m.avoid)}</dd><dt>How we check it</dt><dd>${escape(m.checks)}</dd></dl><p class="muted">${escape(m.example)}</p><a href="${escape(m.reference)}" target="_blank" rel="noopener noreferrer">Technical reference ↗</a></section>`).join("")}</details>`;
}
function chart(result,id) {
  const visuals=experience.figures(result);
  return visuals.map((v,i)=>`<section class="visual"><h4>${escape(v.title)}</h4><p class="muted">${escape(v.purpose)}${v.split ? ` · ${escape(v.split)} data` : ""}</p><div class="plot" id="plot-${id}-${i}" aria-label="${escape(v.title)}"></div><div class="figure-actions">${["png","svg","html","json","javascript","python"].map(kind=>`<button class="secondary" data-figure-run="${id}" data-figure-index="${i}" data-figure-kind="${kind}" type="button">${{png:"PNG",svg:"SVG",html:"Interactive HTML",json:"Chart JSON",javascript:"Figure JavaScript",python:"Figure Python"}[kind]}</button>`).join("")}</div><details><summary>Exact chart values</summary><div class="table-wrap"><table><thead><tr><th>Series</th><th>Period / method</th><th>Value</th></tr></thead><tbody>${v.figure.data.flatMap(t=>t.type==='heatmap' ? t.y.flatMap((y,j)=>t.x.map((x,k)=>`<tr><td>${escape(t.name)} · ${escape(y)}</td><td>${escape(x)}</td><td>${escape(format(t.z[j][k]))}</td></tr>`)) : (t.x || t.y.map((_,j)=>j+1)).map((x,j)=>`<tr><td>${escape(t.name)}</td><td>${escape(x)}</td><td>${escape(format(t.y[j]))}</td></tr>`)).join("")}</tbody></table></div></details></section>`).join("");
}
async function renderPlots(run,node) {
  if(!run.result || !node)return;
  try{
    for(const [i,v] of experience.figures(run.result).entries()){
      const element=node.querySelector(`#plot-${run.id}-${i}`);
      await experience.render(v,state.palette,element,"run-"+run.id);
    }
  }catch(error){notice("A chart could not render. Its exact values and evidence remain available.",true);}
}
function activity(run) {
  const events=run.events || [];
  return `<div class="activity" aria-label="Analysis activity"><details><summary>Activity timeline</summary><ol class="timeline">${events.map(e=>`<li>${new Date(e.timestamp*1000).toLocaleTimeString()} · ${escape(e.stage.replaceAll("_"," "))} · ${escape(e.status)}${e.attempt>1 ? ` · attempt ${e.attempt}` : ""}</li>`).join("")}</ol></details></div>`;
}
function renderRun(r) {
  const result=r.result;
  return `<article class="run" data-run="${r.id}"><div class="run-heading"><h3>${escape(r.question)}</h3><span class="status ${escape(r.status)}">${escape(r.status)}</span></div><p class="meta">${escape(r.plan?.tier || "planning")} · version ${r.dataset_id.slice(0,8)} · ${new Date(r.created_at*1000).toLocaleString()} · trace ${r.id.slice(0,8)}</p>${activity(r)}${result ? `<p>${escape(result.summary)}</p>${result.independent_review ? `<p class="muted">Independent review: ${result.independent_review.decision === "accept" ? "accepted the checked result" : escape(result.independent_review.decision)}.</p>` : ""}${chart(result,r.id)}${learning(result.methodology)}<p class="muted">${escape(result.execution)} · ${escape(format(result.timing_ms?.end_to_end))} ms end to end · numerical review ${result.review?.passed ? "passed" : "pending"}</p>${(result.warnings || []).map(w=>`<p class="warning">${escape(w)}</p>`).join("")}<div class="evidence-actions"><button class="secondary" data-download="${r.id}">Full evidence JSON</button>${r.bundle_key ? `<button class="secondary" data-bundle="${r.id}">Full analysis notebook, code & tables ↓</button><button class="secondary" data-prepared="${r.id}">Prepared data (Parquet)</button>` : ""}</div><details><summary>Plan, methods & numerical checks</summary><pre>${escape(JSON.stringify({plan:r.plan,review:result.review,independent_review:result.independent_review,candidates:result.candidates,test:result.test,sql:result.sql,versions:result.versions},null,2))}</pre></details>` : `<p>${escape(r.error?.message || r.stage)}</p>${r.result_available ? `<button class="secondary" data-open="${r.id}">Open saved result</button>` : ""}${active(r) ? `<button class="secondary" data-cancel="${r.id}">Cancel job</button>` : ""}`}</article>`;
}
function updateRoute(){$("#route-note").textContent=state.cloud ? "AgentCore chooses and executes the analysis" : "Automatically inferred from your data and question";}
async function refresh(initial=false){
  const previous=new Map(state.runs.map(r=>[r.id,r.status]));
  const result=await api("workspace"); state.datasets=result.datasets; state.runs=result.runs; state.cloud=result.cloud_enabled; state.streaming=result.streaming_enabled;
  state.allowance=result.allowance;

  window.vdsSpeech.available(result.speech_enabled===true);
  $("#allowance").className="token-meter";
  $("#allowance").innerHTML=state.allowance ? `<span>${format(state.allowance.tokens_remaining)} / ${format(state.allowance.token_limit)} tokens available</span><progress value="${state.allowance.tokens_committed}" max="${state.allowance.token_limit}" aria-label="Preview tokens committed"></progress><small>${format(state.allowance.tokens_measured)} used · ${format(state.allowance.tokens_reserved)} reserved · ${state.allowance.remaining} analyses left</small>` : "";
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
async function remember(pending=false,action="send"){
  const question=$("#question").value.trim(),file=$("#file").files[0] || state.draftFile;
  const same=intent && intent.question===question && intent.dataset_id===state.selected && (!file || intent.file_name===file.name);
  intent=await drafts.save({...intent,question,dataset_id:state.selected,file_name:file?.name || intent?.file_name,
    request_key:same && intent.request_key ? intent.request_key:crypto.randomUUID(),pending,action,
    identity_id:intent?.identity_id || window.vdsAuth.identity()},file);
  return intent;
}
window.vdsBeforeLogin=()=>remember(intent?.pending===true,intent?.action || "send");
window.vdsClearDraft=()=>drafts.clear();
async function prepareFile(){
  if(intent?.dataset_id && state.datasets.some(d=>d.id===intent.dataset_id) && !intent.file_id){choose(intent.dataset_id);return;}
  const file=state.draftFile || $("#file").files[0];if(!file)throw new Error("Attach a dataset before sending this question.");
  if(file.size>10*1024*1024)throw new Error("Choose a file up to 10 MiB.");
  let result;
  if(window.vdsAuth.hosted()){
    if(!intent.upload_id){
      const upload=await api("uploads",{name:file.name,size:file.size});
      const form=new FormData();Object.entries(upload.post.fields).forEach(([key,value])=>form.append(key,value));form.append("file",file);
      const stored=await fetch(upload.post.url,{method:"POST",body:form});if(!stored.ok)throw new Error("The file upload did not complete. Try again.");
      intent.upload_id=upload.upload_id;drafts.write(intent);
    }
    result=await api("datasets",{upload_id:intent.upload_id,name:file.name,question:intent.question});
  }else{
    const bytes=new Uint8Array(await file.arrayBuffer());let binary="";for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
    result=await api("datasets",{name:file.name,content_base64:btoa(binary),question:intent.question});
  }
  intent.dataset_id=result.dataset.id;intent.prepared=true;drafts.write(intent);
  await refresh();choose(result.dataset.id);
}
async function sendPending(){
  if(state.busy || !intent?.pending)return;
  state.busy=true;$("#question").disabled=true;$("#upload").disabled=true;render();
  try{
    if(!window.vdsAuth.authenticated()){await window.vdsAuth.login();return;}
    if(!drafts.canResume(intent,window.vdsAuth.identity())){intent.pending=false;drafts.write(intent);notice("You signed in to a different account. Review the saved draft and press Send to use it here.",true);return;}
    if(intent.action==='sample'){
      const loaded=await api('public-datasets',{sample_id:intent.sample_id});
      await refresh();choose(loaded.dataset.id);
      $('#question').value=loaded.dataset.public_dataset.question;
      await drafts.clear();intent=null;await remember(false);
      notice('Sample prepared. Review the suggested question, then Send to run it.');return;
    }
    notice(intent.action==="profile" ? "Profiling your data…":"Preparing your message and analysis…");
    if(!intent.prepared && (intent.file_id || !intent.dataset_id))await prepareFile();
    if(intent.action!=="profile"){
      const result=await api("runs",{dataset_id:intent.dataset_id,request_key:intent.request_key,question:intent.question});
      state.focusRun=result.run.id;$("#question").value="";
      notice(result.run.status==="failed" ? result.run.error.message:(state.cloud ? "Message sent. Your analysis continues in AgentCore.":"Message sent. Analysis is running."),result.run.status==="failed");
    }else notice("Your data is prepared. Suggested analyses are ready on the right.");
    await drafts.clear();intent=null;state.draftFile=null;$("#file").value="";
    await refresh();
  }catch(error){
    if(error.code==="unauthenticated"){notice("Your message is saved. Continuing through sign-in…");await window.vdsAuth.login();}
    else notice(error.message+" Your draft is saved; Send retries the same request.",true);
  }finally{state.busy=false;$("#question").disabled=false;$("#upload").disabled=false;render();}
}
async function submit(action){
  if(state.busy)return;
  try{
    await initialization;
    await remember(true,action);intent.identity_id=window.vdsAuth.identity();drafts.write(intent);await sendPending();
  }catch(error){notice(error.message,true);}
}
$("#upload-form").addEventListener("submit",e=>{e.preventDefault();submit("profile");});
$("#analysis-form").addEventListener("submit",e=>{e.preventDefault();submit("send");});
$("#question").addEventListener("input",()=>{if(!state.busy){intent={...intent,question:$("#question").value,dataset_id:state.selected,identity_id:window.vdsAuth.identity(),pending:false};drafts.write(intent);}});
$("#file").addEventListener("change",async()=>{
  try{const file=$("#file").files[0];if(file && file.size>10*1024*1024)throw new Error("Choose a file up to 10 MiB.");
    await drafts.clear();intent=null;state.draftFile=file || null;await remember(false);render();
  }catch(error){$("#file").value="";state.draftFile=null;notice(error.message,true);render();}
});
$("#conversation").addEventListener("click",e=>{const button=e.target.closest("[data-result]");if(button){state.focusRun=button.dataset.result;render();if(innerWidth<761)$("#runs").scrollIntoView({behavior:"smooth"});}});
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
async function restore(signedIn){
  intent=drafts.read();
  if(intent){$("#question").value=intent.question || "";state.draftFile=await drafts.file(intent);if(intent.dataset_id)state.selected=intent.dataset_id;}
  if(signedIn){await refresh(true);if(intent?.pending){
    if(drafts.canResume(intent,window.vdsAuth.identity()))await sendPending();
    else {intent.pending=false;drafts.write(intent);notice("This is a different account. Review your saved draft before pressing Send.",true);}
  }}else {
    state.datasets=[];state.runs=[];state.allowance=null;$("#allowance").textContent="";
    for(const controller of streams.values())controller.abort();clearTimeout(state.timer);render();
  }
}
const initialization=window.vdsAuth.ready.then(restore).catch(e=>notice(e.message,true));
window.addEventListener("vds-auth-change",()=>restore(window.vdsAuth.authenticated()).catch(e=>notice(e.message,true)));

function renderSamples(){
  const query=$('#sample-search').value.toLowerCase();
  $('#sample-gallery').innerHTML=(state.samples || []).filter(d=>[d.title,d.task,d.provider || '',d.synthetic?'synthetic':'public'].join(' ').toLowerCase().includes(query)).map(d=>`<article class="sample-card"><strong>${escape(d.title)}</strong><small>${escape(d.task.replaceAll('_',' '))} · ${format(d.rows)} rows · ${d.synthetic?'Synthetic':d.provider==='OpenML'?'OpenML import':'Public snapshot'}</small><p>${escape(d.question)}</p><small>${escape(d.license)} · version ${escape(d.version)}</small><div><button type="button" class="secondary" data-sample="${escape(d.id)}">Load & profile</button> <a href="${escape(d.source.startsWith('https://')?d.source:'#')}" target="_blank" rel="noopener noreferrer">Source ↗</a></div></article>`).join('') || '<p class="muted">No reviewed example matches this search.</p>';
}
$('#sample-search').addEventListener('input',renderSamples);
$('#sample-gallery').addEventListener('click',async event=>{
  const button=event.target.closest('[data-sample]');if(!button || state.busy)return;
  state.busy=true;button.disabled=true;
  try{
    await window.vdsAuth.ready;
    if(!window.vdsAuth.authenticated()){
      const sample=state.samples.find(d=>d.id===button.dataset.sample);
      $('#question').value=sample.question;state.draftFile=null;$('#file').value='';
      intent=await drafts.save({question:sample.question,sample_id:sample.id,pending:true,action:'sample',identity_id:null,request_key:crypto.randomUUID()});
      await window.vdsAuth.login();return;
    }
    notice('Loading and profiling the teaching dataset…');
    const result=await api('public-datasets',{sample_id:button.dataset.sample});
    await refresh();choose(result.dataset.id);
    $('#question').value=result.dataset.public_dataset.question;
    intent=null;await remember(false);notice('Sample prepared. Review the suggested question, then Send to run it.');
  }catch(error){notice(error.message,true);}finally{state.busy=false;button.disabled=false;render();}
});

(async()=>{try{const response=await fetch('/static/dataset-catalog.json');if(!response.ok)throw new Error('Unavailable');state.samples=await response.json();renderSamples();}catch{$('#sample-gallery').textContent='The dataset gallery is unavailable. Upload a file to continue.';}})();
