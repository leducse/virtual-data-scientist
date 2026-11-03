"use strict";
// Per-tab draft text, with the optional file in IndexedDB (never tokens).
window.vdsDrafts=(()=>{
  const key="vds_chat_draft",lifetime=2*60*60*1000;
  let queue=Promise.resolve();
  function read(){try{const draft=JSON.parse(sessionStorage.getItem(key)||"null");return draft && Date.now()-draft.created<lifetime ? draft : null;}catch{return null;}}
  function write(draft){sessionStorage.setItem(key,JSON.stringify({...draft,created:draft.created || Date.now()}));}
  function fileStore(action,value,id){
    return new Promise((resolve,reject)=>{
      const request=indexedDB.open("vds-drafts",1);
      request.onupgradeneeded=()=>request.result.createObjectStore("files");
      request.onerror=()=>reject(new Error("The attached file could not be saved for sign-in. Enable browser storage and try again."));
      request.onsuccess=()=>{
        const db=request.result,tx=db.transaction("files",action==="get" ? "readonly":"readwrite"),store=tx.objectStore("files");
        // Expire abandoned blobs without depending on a later successful login.
        if(action!=="get"){const cursor=store.openCursor();cursor.onsuccess=()=>{const c=cursor.result;if(c){if(c.value.created<Date.now()-lifetime)c.delete();c.continue();}};}
        const operation=action==="get" ? store.get(id) : action==="put" ? store.put({file:value,created:Date.now()},id) : store.delete(id);
        operation.onsuccess=()=>{const result=operation.result;tx.oncomplete=()=>{db.close();resolve(result?.file || null);};};
        tx.onerror=()=>{db.close();reject(new Error("Your draft file could not be saved. Please try again."));};
      };
    });
  }
  async function save(draft,file){
    const task=async()=>{
      const previous=read(),id=draft.file_id || previous?.file_id || crypto.randomUUID();
      if(file)await fileStore("put",file,id);
      const next={...draft,...(file || draft.file_id ? {file_id:id}:{}),created:Date.now()};write(next);return next;
    };
    queue=queue.catch(()=>{}).then(task);return queue;
  }
  async function clear(){await queue.catch(()=>{});const old=read();sessionStorage.removeItem(key);if(old?.file_id)await fileStore("delete",null,old.file_id);}
  return {read,write,save,clear,file:async draft=>draft?.file_id ? fileStore("get",null,draft.file_id):null,
    canResume:(draft,identity)=>!!draft?.pending && (!draft.identity_id || draft.identity_id===identity)};
})();
