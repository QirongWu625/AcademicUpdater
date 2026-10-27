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
for(const name of ['history.js','trash.js','execution.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'..','static',name),'utf8'),context);
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
  vm.runInContext(`
    const displayDate=x=>x||'',errorText=x=>x,lang=()=> 'en';
    S.boot={settings:{auto_resume:true},execution:{active:3,limit:3},jobs:[
      {id:1,kind:'collect',status:'running',argument:{input:null},progress:{phase:'analysis'},queue:{total:9,completed:3}},
      {id:2,kind:'history_search',status:'running',argument:{input:7},progress:{history_collected:100,history_analyzed:20}},
      {id:3,kind:'analyze',status:'paused',argument:{},progress:{pause_requested:true},error:'paused_by_user'}
    ]};
  `,context);
  assert.equal(vm.runInContext('runningJobs().length',context),2);
  assert.equal(vm.runInContext('historyBusy(7)',context),true);
  assert.equal(vm.runInContext('historyBusy(8)',context),false);
  html=vm.runInContext('jobBanner()',context);
  assert.match(html,/collectJob #1/);assert.match(html,/historyPage #2/);assert.match(html,/analyzeJob #3/);
  assert.match(html,/3 \/ 3/);assert.equal((html.match(/pauseJob/g)||[]).length,2);
  console.log('UI state regression checks passed (filters, empty states, trash navigation).');
})().catch(error=>{console.error(error);process.exitCode=1});
