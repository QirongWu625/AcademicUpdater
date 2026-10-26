'use strict';
// Exercise UI state transitions without a browser, credentials or network.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const controls={
  '[name=history_filter]':{value:'selected'},
  '[name=history_search]':{value:'old query'},
  '#history-paper-results':{innerHTML:''}
};
const context=vm.createContext({
  COPY:{},ERRORS:{},S:{page:'history'},
  document:{addEventListener(){}},$:(selector)=>controls[selector],
  setTimeout,clearTimeout,structuredClone
});
for(const name of ['history.js','trash.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'..','static',name),'utf8'),context);
vm.runInContext("const t=k=>COPY[k]?.[0]||k,esc=v=>String(v??''),btn=(a,l)=>'<button>'+t(l)+'</button>';",context);
(async()=>{
  // A periodic refresh may supersede the click's list request. Controls must
  // still reflect the requested filter instead of showing 'selected' over all rows.
  await vm.runInContext("loadHistoryPapers=async()=>false;historyAction({dataset:{action:'history-show-all'}})",context);
  assert.equal(controls['[name=history_filter]'].value,'all');
  assert.equal(controls['[name=history_search]'].value,'');
  assert.equal(vm.runInContext('H.filter',context),'all');
  vm.runInContext("H.filter='selected';H.query='';H.offset=0;",context);
  let html=vm.runInContext("historyEmptyState({progress:{search_started:true},counts:{total:45,pending:45},status:'paused'})",context);
  assert.match(html,/AI review is still pending/);assert.match(html,/View all candidates/);
  html=vm.runInContext("historyEmptyState({progress:{search_started:true,streams:[{error:'network_error'}]},counts:{total:0},status:'partial'})",context);
  assert.match(html,/not a confirmed zero-result search/);
  html=vm.runInContext("historyEmptyState({progress:{search_started:true,streams:[]},counts:{total:0},status:'complete'})",context);
  assert.match(html,/completed search returned no active records/);
  // An old trash request must not overwrite the newly selected category.
  let finish;
  context.api=()=>new Promise(resolve=>{finish=resolve});
  const pending=vm.runInContext("T.kind='items';T.query='';loadTrash()",context);
  vm.runInContext("T.kind='histories';T.request++;",context);finish([{id:1}]);
  assert.equal(await pending,false);assert.equal(vm.runInContext('T.rows.length',context),0);
  console.log('UI state regression checks passed (filters, empty states, trash navigation).');
})().catch(error=>{console.error(error);process.exitCode=1});
