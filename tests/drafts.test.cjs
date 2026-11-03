const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const stored=new Map(),context={window:{},Date,JSON,sessionStorage:{getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)}};
vm.runInNewContext(fs.readFileSync('static/drafts.js','utf8'),context);
const drafts=context.window.vdsDrafts;
test('only an explicitly submitted, unexpired intent can resume for the same account',()=>{
  drafts.write({question:'Keep this question',request_key:'stable-key',identity_id:'account-a',pending:true});
  assert.equal(drafts.read().request_key,'stable-key');
  assert.equal(drafts.canResume(drafts.read(),'account-a'),true);
  assert.equal(drafts.canResume(drafts.read(),'account-b'),false);
  assert.equal(drafts.canResume({pending:false},'account-a'),false);
  drafts.write({created:Date.now()-3*60*60*1000,pending:true});assert.equal(drafts.read(),null);
});
