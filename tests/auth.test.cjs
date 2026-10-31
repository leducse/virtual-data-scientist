const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {webcrypto} = require("node:crypto");
const source = fs.readFileSync("static/auth.js", "utf8");

function context({search="", transaction=null, local=false, guest=false}={}) {
  const elements = new Map(), stored = new Map(transaction ? [["vds_pkce", JSON.stringify(transaction)]] : []), requests = [];
  const element = (selector) => {
    if (!elements.has(selector)) elements.set(selector, {hidden:false, inert:false, disabled:false, listeners:{}, addEventListener(name,callback){this.listeners[name]=callback;}});
    return elements.get(selector);
  };
  const location = {hostname:local ? "127.0.0.1" : "app.example.test", origin:"https://app.example.test", search, assign(url){this.assigned=url;}};
  const globals = {
    window:{}, document:{querySelector:element}, location, history:{replaceState(){}},
    crypto:webcrypto, btoa, Uint8Array, TextEncoder, URLSearchParams, Date,
    sessionStorage:{getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value),removeItem:key=>stored.delete(key)},
    localStorage:{removeItem(){}},
    fetch:async (url,options={}) => {
      requests.push({url,options});
      return {ok:true,status:200,json:async()=>url==="/config.json" ? {domain:"https://vds-example.auth.us-east-1.amazoncognito.com",client_id:"client123",guest_enabled:guest} : {access_token:"synthetic-test-token",expires_in:900}};
    }
  };
  vm.runInNewContext(source, globals);
  return {auth:globals.window.vdsAuth, element, stored, requests, location};
}

test("local verification does not contact identity provider",async()=>{
  const c=context({local:true}); assert.equal(await c.auth.ready,true); assert.equal(c.requests.length,0);
});

test("hosted sign-in uses state, S256 and no persistent access token",async()=>{
  const c=context(); assert.equal(await c.auth.ready,false); assert.equal(c.element(".layout").inert,true);
  await c.element("#sign-in").listeners.click();
  const url=new URL(c.location.assigned), transaction=JSON.parse(c.stored.get("vds_pkce"));
  assert.equal(url.searchParams.get("response_type"),"code");
  assert.equal(url.searchParams.get("code_challenge_method"),"S256");
  assert.equal(url.searchParams.get("state"),transaction.state);
  const hash=Buffer.from(await webcrypto.subtle.digest("SHA-256",new TextEncoder().encode(transaction.verifier))).toString("base64url");
  assert.equal(url.searchParams.get("code_challenge"),hash);
  assert.deepEqual([...c.stored.keys()],["vds_pkce"]);
});

test("wrong or expired callback state never exchanges code",async()=>{
  for(const transaction of [{state:"wrong",verifier:"secret",created:Date.now()},{state:"match",verifier:"secret",created:Date.now()-700000}]){
    const c=context({search:"?code=test-code&state=match",transaction}); assert.equal(await c.auth.ready,false);
    assert.equal(c.requests.length,1); assert.equal(c.stored.has("vds_pkce"),false);
  }
});

test("valid callback uses memory token and body hash, logout clears access",async()=>{
  const c=context({search:"?code=test-code&state=match",transaction:{state:"match",verifier:"test-verifier",created:Date.now()}});
  assert.equal(await c.auth.ready,true); assert.equal(c.stored.size,0);
  assert.equal(c.requests[1].options.body.get("code_verifier"),"test-verifier");
  await c.auth.request("runs",{question:"Show monthly revenue"});
  const request=c.requests.at(-1);assert.equal(request.options.headers["x-vds-token"],"synthetic-test-token");
  assert.equal(request.options.headers["x-amz-content-sha256"].length,64);
  c.element("#sign-out").listeners.click();
  await assert.rejects(c.auth.request("workspace"),/Sign in/);
  assert.equal(new URL(c.location.assigned).pathname,"/logout");
});

test("guest mode uses the server cookie and never invents a client owner",async()=>{
  const c=context({guest:true});assert.equal(await c.auth.ready,true);assert.equal(c.auth.isGuest(),true);
  assert.equal(c.requests[1].url,'/api/v2/session');
  await c.auth.request('workspace');
  assert.equal(c.requests.at(-1).options.headers['x-vds-token'],undefined);
  assert.equal(c.stored.size,0);
});
