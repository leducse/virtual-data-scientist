"use strict";
// Provider tokens exist only during the PKCE exchange. The app uses an opaque,
// HttpOnly cookie with a server-verified expiry for reloads and browser Back.
window.vdsAuth = (() => {
  let config=null, signedIn=false, guest=false, identity=null, expiresAt=0, starting=false;
  const $=s=>document.querySelector(s), transactionKey="vds_pkce";
  const encoded=bytes=>btoa(String.fromCharCode(...bytes)).replaceAll("+","-").replaceAll("/","_").replaceAll("=","");
  const digest=async text=>new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(text)));
  async function raw(path,body,token) {
    const options={headers:{},cache:"no-store",credentials:"same-origin"};
    if(token)options.headers["x-vds-token"]=token;
    if(body!==undefined){options.method="POST";options.body=JSON.stringify(body);options.headers["Content-Type"]="application/json";
      options.headers["x-amz-content-sha256"]=[...await digest(options.body)].map(b=>b.toString(16).padStart(2,"0")).join("");}
    return fetch("/api/v2/"+path,options);
  }
  function view(text="Sign in to start your 100,000-token preview. Your draft stays here.") {
    $(".layout").hidden=false;$(".layout").inert=false;
    $("#auth-panel").hidden=signedIn || guest;$("#auth-message").textContent=text;
    $("#sign-in").disabled=false;$("#sign-out").hidden=!signedIn;
    $("#continue-sign-in").hidden=signedIn;starting=false;
  }
  function gate(text){signedIn=false;guest=false;identity=null;expiresAt=0;view(text);}
  function accept(session){signedIn=session.signed_in===true;identity=session.identity_id || null;expiresAt=(session.expires_at || 0)*1000;view();}
  async function check(){const response=await raw("auth/session");if(!response.ok)throw new Error("Sign-in status is unavailable. Try again.");accept(await response.json());return signedIn;}
  async function login(){
    await ready;if(starting || !config)return;
    starting=true;$("#sign-in").disabled=true;$("#continue-sign-in").disabled=true;
    try{
      if(window.vdsBeforeLogin)await window.vdsBeforeLogin();
      const verifier=encoded(crypto.getRandomValues(new Uint8Array(32))),state=encoded(crypto.getRandomValues(new Uint8Array(32)));
      sessionStorage.setItem(transactionKey,JSON.stringify({verifier,state,created:Date.now()}));
      const params=new URLSearchParams({response_type:"code",client_id:config.client_id,redirect_uri:location.origin+"/",scope:"openid profile",state,
        code_challenge_method:"S256",code_challenge:encoded(await digest(verifier))});
      location.assign(config.domain+"/oauth2/authorize?"+params);
    }catch(error){view(error.message || "Sign-in could not start. Try again.");}
    finally{$("#continue-sign-in").disabled=false;}
  }
  async function logout(){
    await ready;
    const response=await raw("auth/logout",{});if(!response.ok){view("Sign-out did not finish. Please try again.");return;}
    if(window.vdsClearDraft)await window.vdsClearDraft();
    gate();localStorage.removeItem("vds_dataset");sessionStorage.removeItem(transactionKey);
    location.assign(config.domain+"/logout?"+new URLSearchParams({client_id:config.client_id,logout_uri:location.origin+"/"}));
  }
  const ready=(async()=>{
    if(["localhost","127.0.0.1","[::1]"].includes(location.hostname)){signedIn=true;return true;}
    view("Connecting to secure sign-in…");$("#sign-in").disabled=true;
    const response=await fetch("/config.json",{cache:"no-store"});if(!response.ok)throw new Error("Hosted workspace configuration is unavailable.");
    config=await response.json();
    if(!/^https:\/\/[a-z0-9-]+\.auth\.[a-z0-9-]+\.amazoncognito\.com$/.test(config.domain) || !/^[a-z0-9]+$/.test(config.client_id))throw new Error("Hosted sign-in configuration is invalid.");
    $("#studio-link").hidden=true;$("#sign-in").addEventListener("click",login);$("#continue-sign-in").addEventListener("click",login);$("#sign-out").addEventListener("click",logout);
    const params=new URLSearchParams(location.search),code=params.get("code"),oauthError=params.get("error");
    if(code || oauthError){
      const saved=sessionStorage.getItem(transactionKey);sessionStorage.removeItem(transactionKey);history.replaceState(null,"","/");
      try{
        const transaction=JSON.parse(saved || "null"),age=Date.now()-(transaction?.created || 0);
        if(oauthError || !transaction || params.get("state")!==transaction.state || age<0 || age>600000)throw new Error("The sign-in request was cancelled or expired. Your draft is saved. Sign in to continue.");
        const response=await fetch(config.domain+"/oauth2/token",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},
          body:new URLSearchParams({grant_type:"authorization_code",client_id:config.client_id,redirect_uri:location.origin+"/",code_verifier:transaction.verifier,code})});
        if(!response.ok)throw new Error("Sign-in could not finish. Your draft is saved. Try again.");
        const tokens=await response.json();if(!tokens.access_token)throw new Error("Sign-in did not return access.");
        const session=await raw("auth/session",{},tokens.access_token);tokens.access_token=null;tokens.refresh_token=null;tokens.id_token=null;
        const result=await session.json();if(!session.ok)throw new Error(result.error?.message || "Sign-in could not finish.");
        accept(result);return signedIn;
      }catch(error){gate(error.message);return false;}
    }
    if(await check())return true;
    if(config.guest_enabled){const response=await raw("session",{});if(response.ok){guest=true;view();return true;}}
    view();return false;
  })().catch(error=>{gate(error.message);return false;});
  window.addEventListener("pageshow",async event=>{
    if(!event.persisted)return;
    $("#sign-in").disabled=false;$("#continue-sign-in").disabled=false;starting=false;
    await ready;if(config){try{await check();}catch(error){gate(error.message);}window.dispatchEvent(new Event("vds-auth-change"));}
  });
  return {ready,login,hosted:()=>!!config,isGuest:()=>guest,identity:()=>identity,authenticated:()=>signedIn || guest,
    async request(path,body,signal){
      await ready;
      if(config && !guest && (!signedIn || Date.now()>=expiresAt)){
        gate("Your session expired. Sign in to continue; your draft is saved.");
        const error=new Error("Sign in to continue.");error.code="unauthenticated";throw error;
      }
      const options={headers:{},cache:"no-store",credentials:"same-origin",signal};
      if(body!==undefined){options.method="POST";options.body=JSON.stringify(body);options.headers["Content-Type"]="application/json";
        if(config)options.headers["x-amz-content-sha256"]=[...await digest(options.body)].map(b=>b.toString(16).padStart(2,"0")).join("");}
      const response=await fetch("/api/v2/"+path,options);
      if(config && response.status===401)gate("Your session expired. Sign in to continue; your draft is saved.");
      return response;
    }};
})();
