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
for(const name of ['history.js','trash.js','execution.js','scispace.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'..','static',name),'utf8'),context);
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
    S.boot={local_day:'2026-10-27',version:'1.6.1',settings:{auto_resume:true,ai_concurrency:3},execution:{active:3,limit:3,by_job:{1:1,2:2},waiting:3},jobs:[
      {id:1,kind:'collect',status:'running',argument:{input:{day:'2026-10-27'}},progress:{phase:'analysis'},queue:{total:9,completed:3}},
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
  assert.match(html,/Set parallelism/);assert.match(html,/Waiting for an AI slot: 3/);
  assert.match(vm.runInContext('jobParallelInfo(S.boot.jobs[0])',context),/1 AI requests in progress/);
  assert.match(vm.runInContext('jobParallelInfo(S.boot.jobs[1])',context),/2 AI requests in progress/);
  assert.match(vm.runInContext('jobParallelInfo(S.boot.jobs[1])',context),/Up to 10 papers per request/);
  vm.runInContext("COPY.effort_medium=['Medium','中等'];COPY.effort_max=['Max','最高'];S.boot.jobs[0].ai_state={next:{model:'new-model',reasoning_effort:'medium'},active:[{model:'old-model',reasoning_effort:'max',count:1}]}",context);
  html=vm.runInContext('jobAIInfo(S.boot.jobs[0])',context);
  assert.match(html,/Next requests: new-model · Medium/);assert.match(html,/In-flight requests: old-model · Max × 1/);
  vm.runInContext("S.boot.jobs[0].ai_state.active=[]",context);
  assert.doesNotMatch(vm.runInContext('jobAIInfo(S.boot.jobs[0])',context),/In-flight requests/);
  assert.match(vm.runInContext("jobAIInfo({status:'complete',progress:{model:'old-model',reasoning_effort:'max'}})",context),/old-model · Max/);
  assert.equal(vm.runInContext('activeCollection().id',context),1);
  assert.match(vm.runInContext('collectionButton()',context),/View collection progress/);
  const button={outerHTML:''};context.document.querySelectorAll=()=>[button];
  vm.runInContext('syncCollectionButtons()',context);assert.match(button.outerHTML,/View collection progress/);
  let notice='',scrolled=false;context.notify=text=>{notice=text};
  controls['#job-card-1']={scrollIntoView(){scrolled=true}};
  vm.runInContext('focusCollection(1)',context);assert.match(notice,/3 \/ 9/);assert.equal(scrolled,true);
  vm.runInContext("S.boot.jobs[0].status='complete';syncCollectionButtons()",context);
  assert.equal(vm.runInContext('activeCollection()',context),undefined);assert.doesNotMatch(button.outerHTML,/View collection progress/);
  vm.runInContext("S.boot.jobs[0].status='running';S.boot.jobs[0].argument.input.day='2026-10-26'",context);
  assert.equal(vm.runInContext('activeCollection()',context),undefined);assert.equal(vm.runInContext('historyBusy(7)',context),true);
  controls['meta[name="academic-version"]']={content:'1.6.0'};
  assert.match(vm.runInContext('versionNotice()',context),/Save any unfinished edits/);
  controls['meta[name="academic-version"]'].content='1.6.1';
  assert.doesNotMatch(vm.runInContext('versionNotice()',context),/Save any unfinished edits/);
  vm.runInContext(`const textInput=(name,label,value,type,attrs)=>'<input name="'+name+'" value="'+value+'" '+attrs+'>';`,context);
  html=vm.runInContext('concurrencyForm()',context);assert.match(html,/min="1" max="8"/);assert.match(html,/Apply now/);
  let closed=false,refreshed=false,saved;
  controls['#concurrency-dialog']={close(){closed=true}};
  controls['#schedule-form [name=ai_concurrency]']={value:'3'};
  context.api=async(path,body)=>{saved={path,body};return {ai_concurrency:Number(body.ai_concurrency)}};
  context.refreshVisible=async()=>{refreshed=true};
  await vm.runInContext("saveConcurrency({ai_concurrency:'6'})",context);
  assert.equal(saved.path,'/api/settings');assert.deepEqual(Object.keys(saved.body),['ai_concurrency']);
  assert.equal(saved.body.ai_concurrency,'6');assert.equal(closed,true);assert.equal(refreshed,true);
  assert.equal(controls['#schedule-form [name=ai_concurrency]'].value,6);
  closed=false;refreshed=false;context.api=async()=>{throw new Error('offline')};
  await assert.rejects(vm.runInContext("saveConcurrency({ai_concurrency:'8'})",context),/offline/);
  assert.equal(closed,false);assert.equal(refreshed,false);assert.equal(vm.runInContext('S.boot.settings.ai_concurrency',context),6);
  // A late question response must not overwrite the user's edits or target.
  controls['#ss-target']={value:'1'};controls['#ss-question']={value:'my question'};
  controls['#ss-preview']={innerHTML:'old preview'};controls['#ss-import']={disabled:false};controls['#scispace-dialog']={open:true};
  let resolveQuestion;context.api=()=>new Promise(resolve=>{resolveQuestion=resolve});
  const questionLoad=vm.runInContext('scispaceContext()',context);
  vm.runInContext('invalidateSciSpace()',context);controls['#ss-question'].value='My edited question';
  resolveQuestion({question:'stale generated question'});await questionLoad;
  assert.equal(controls['#ss-question'].value,'My edited question');assert.equal(controls['#ss-import'].disabled,true);
  // Repeated clicks while an import is active must not submit a second write.
  let writes=0;context.api=async()=>{writes++};
  vm.runInContext("SS.busy=true;SS.preview={content:'data'}",context);
  await vm.runInContext('importSciSpace()',context);assert.equal(writes,0);
  html=vm.runInContext('scispacePanel()',context);assert.match(html,/Manual import/);assert.match(html,/does not provide an API/);
  console.log('UI state regression checks passed (filters, trash, parallel jobs, collection progress, SciSpace drafts and duplicate submissions).');
})().catch(error=>{console.error(error);process.exitCode=1});
