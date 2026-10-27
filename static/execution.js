'use strict';
Object.assign(COPY,{
  viewCollection:['View collection progress','查看采集进度'],
  collectionAlreadyRunning:['Collection is already running. Showing the existing task.','采集已在运行，已为你显示现有任务进度。'],
  collectionAssessing:['Collection is assessing papers','采集正在评估论文'],
  appUpdateAvailable:['The application was updated. Save any unfinished edits, then refresh this page to load the new interface.','应用已更新。请先保存尚未提交的编辑，再刷新页面加载新版界面。'],
  reloadApp:['Refresh page','刷新页面'],
  executionTitle:['Automatic work & parallel assessment','自动运行与并行评估'],
  aiConcurrency:['Concurrent AI requests','AI 同时请求数'],
  parallelSettings:['Set parallelism','设置并发数量'],
  parallelTitle:['Parallel paper analysis','论文并行分析'],
  parallelApply:['Apply now','立即应用'],
  parallelCancel:['Cancel','取消'],
  parallelSaved:['Parallel limit saved. Running tasks use it immediately.','并发上限已保存，正在运行的任务立即采用新设置。'],
  parallelHelp:['Choose 1–8 simultaneous AI requests, shared across all tasks. Raising this starts more queued work without restarting. Lowering it lets requests already in progress finish.','可设置 1–8 个同时进行的 AI 请求，所有任务共享。调高后会直接增加并行处理，无需重启；调低时，已开始的请求会先完成。'],
  parallelSpeed:['Results appear as each request finishes. Daily analysis handles one paper per request; history handles up to 10. Model response time and service limits also affect speed.','结果在各个请求完成后陆续显示。日常分析每个请求处理 1 篇，历史分析每个请求最多处理 10 篇。速度还取决于模型响应时间和服务方限制。'],
  parallelWaiting:['Waiting for an AI slot','等待 AI 请求名额'],
  parallelHistoryBatch:['Up to 10 papers per request','每个请求最多 10 篇'],
  concurrencyHelp:['Shared across daily updates and history searches. History assesses up to 10 papers per request. Higher reasoning effort can still take longer; provider and daily limits apply.','每日更新与历史检索共享此上限；历史评估每次最多 10 篇。更高推理档位仍可能耗时较长，并受服务方及每日请求额度限制。'],
  autoResume:['Automatically recover interrupted tasks','自动恢复意外中断的任务'],
  autoResumeHelp:['Network failures retry with backoff. Daily-budget pauses resume after the local day changes. Manual pauses stay paused; sign-in and configuration errors need attention.','网络故障退避重试；每日额度用尽后在当地次日继续。手动暂停不会自动恢复，登录和配置问题需要处理。'],
  adaptSaved:['Refine my research field from saved papers before collection','采集前根据收藏论文调整研究领域'],
  adaptSavedHelp:['Saving, unsaving, deleting or restoring saved papers updates the evidence set. Your original prompt and exclusions remain the constraints. Unchanged saves use no AI.','收藏、取消收藏，以及删除或恢复已收藏论文会更新学习依据。保留原始提示词和排除条件；收藏集合不变时不调用 AI。'],
  loginStartup:['Start in the background when I sign in to Windows','登录 Windows 后在后台启动'],
  startupHelp:['A missed daily update runs after startup once its scheduled time has passed. The computer must be awake and connected; closing this page does not stop the app.','若已过计划时间，启动后会补跑当天更新。电脑需保持唤醒并联网；关闭网页不会停止后台程序。'],
  startupSaved:['Windows startup preference saved.','已保存 Windows 自启设置。'],
  schedulerChecked:['Last scheduler check','最近调度检查'],
  scheduledDay:['Latest scheduled update','最近定时更新日期'],
  activeRequests:['AI requests in progress','正在执行的 AI 请求'],
  taskEvents:['Interruption and recovery log','中断与恢复记录'],
  retryAt:['Automatic retry at','自动重试时间'],
  requestRetryAt:['Next request attempt','下一次请求尝试'],
  profile_learning:['Updating research field from saves','正在根据收藏调整研究领域'],
  profileUpdated:['Research field updated from saved papers','已根据收藏更新研究领域'],
  learningPending:['Saved papers changed; the next collection will refresh the research field.','收藏已变化，下次采集前将更新研究领域。'],
  learningCurrent:['Saved-paper preferences are up to date.','收藏偏好已同步。'],
  learningEmpty:['No saved papers yet; the original research field is used.','尚无收藏论文，使用原研究领域。'],
  learningEvidence:['Saved papers / sampled papers','当前收藏 / 用于学习的抽样论文'],
  learningDeferred:['Research-field learning was deferred; collection used the existing field.','研究领域学习暂缓，本次采集使用已有领域。'],
  event_interrupted:['Process stopped before completion','进程在完成前停止'],event_stopped:['Task stopped','任务停止'],
  event_retry:['Retrying connection','重试连接'],event_resumed:['Resumed from checkpoint','从已保存进度继续'],
  event_pause_requested:['Manual pause requested','已请求手动暂停'],event_profile_updated:['Saved-paper learning applied','已应用收藏学习'],
  event_profile_deferred:['Saved-paper learning deferred','收藏学习暂缓'],
  scheduleHint:['Runs in the background while the computer is awake. Missed schedules catch up after startup. Independent history searches can run at the same time.','电脑唤醒时在后台运行；错过时间会在启动后补跑。可与独立的历史检索同时执行。']
});
Object.assign(ERRORS,{
  job_already_running:['This same task is already running. Other independent tasks can run alongside it.','同一任务已在运行，其他独立任务仍可同时启动。'],
  too_many_jobs:['Eight tasks are already active. Wait for one to finish or pause one.','已有 8 个任务运行，请等待完成或暂停其中一个。'],
  startup_unavailable:['Automatic Windows login startup is unavailable on this system.','当前系统不支持 Windows 登录自启。'],
  saved_scope_changed:['Saved papers or the applied field changed during learning; it will be retried at the next collection.','学习期间收藏或已应用领域发生变化，将在下次采集重试。'],
  application_stopped:['The application stopped; saved progress can be resumed automatically.','应用已停止，已保存进度可自动恢复。'],
  process_exit_or_shutdown:['The previous process ended unexpectedly or the computer shut down. The exact cause is not available.','上次进程意外结束或电脑关机；无法确定更具体的原因。']
  ,saved_set_changed:['The current saved-paper set changed.','当前收藏论文集合发生变化。']
});

let jobStates=new Map(),jobPollActive=false,profileViewChanged=false;
function runningJobs(){return (S.boot?.jobs||[]).filter(r=>r.status==='running')}
function activeCollection(){return runningJobs().find(r=>r.kind==='collect'&&r.argument?.input?.day===S.boot.local_day)}
function collectionButton(){const r=activeCollection();return r?btn('view-collection','viewCollection',true,`data-id="${r.id}"`):btn('collect','collect',true)}
function syncCollectionButtons(){document.querySelectorAll('[data-action="collect"],[data-action="view-collection"]').forEach(el=>{el.outerHTML=collectionButton()})}
function versionNotice(){const loaded=$('meta[name="academic-version"]')?.content;return `<div id="app-update">${loaded&&S.boot?.version&&loaded!==S.boot.version?`<div class="warning">${esc(t('appUpdateAvailable'))} ${btn('reload-app','reloadApp')}</div>`:''}</div>`}
function focusCollection(id){
  const r=(S.boot.jobs||[]).find(r=>r.id===id);
  if(!r||r.status!=='running'){notify(t('jobFinished'));return}
  const q=r.queue||{};
  notify(r.progress?.phase==='analysis'?`${t('collectionAssessing')}: ${q.completed||0} / ${q.total||0}`:t('collectionAlreadyRunning'));
  $('#job-card-'+id)?.scrollIntoView({behavior:'smooth',block:'center'});
}
async function viewCollection(id){await refreshVisible();focusCollection(id)}
function concurrencyForm(){return `<h2 id="parallel-title">${esc(t('parallelTitle'))}</h2><p class="small muted">${esc(t('parallelHelp'))}</p><form id="concurrency-form">${textInput('ai_concurrency','aiConcurrency',S.boot.settings.ai_concurrency||3,'number','min="1" max="8" step="1" required')}<p class="small muted">${esc(t('parallelSpeed'))}</p><div class="toolbar"><button type="button" data-action="close-concurrency">${esc(t('parallelCancel'))}</button><button class="primary" type="submit">${esc(t('parallelApply'))}</button></div></form>`}
function showConcurrency(){
  let dialog=$('#concurrency-dialog');
  if(!dialog){dialog=document.createElement('dialog');dialog.id='concurrency-dialog';dialog.className='concurrency-dialog';dialog.setAttribute('aria-labelledby','parallel-title');document.body.append(dialog)}
  dialog.innerHTML=concurrencyForm();dialog.showModal();
}
async function saveConcurrency(data){
  S.boot.settings=await api('/api/settings',{ai_concurrency:data.ai_concurrency});
  const schedule=$('#schedule-form [name=ai_concurrency]');if(schedule)schedule.value=S.boot.settings.ai_concurrency;
  $('#concurrency-dialog').close();notify(t('parallelSaved'));await refreshVisible();
}
function jobParallelInfo(r){const n=S.boot.execution?.by_job?.[r.id]||0;return r.status==='running'?`<div class="tiny muted job-parallel"><strong>${n} ${esc(t('activeRequests'))}</strong>${r.kind==='history_search'?' · '+esc(t('parallelHistoryBatch')):''}</div>`:''}
function historyBusy(id){return runningJobs().some(r=>r.kind.startsWith('history_')&&r.argument?.input===id)}
function jobName(r){return t(({collect:'collectJob',analyze:'analyzeJob',interpret:'interpretJob',item_analysis:'itemAnalysisJob',import:'importJob',history_plan:'historyInterpret',history_search:'historyPage'})[r.kind]||r.kind)+' #'+r.id}
function syncJobs(){
  const version=S.boot.profile?.active?.version;
  if(S.lastActiveVersion!==undefined&&S.lastActiveVersion!==version&&!S.dirty&&!S.scopeEdited&&!S.manual){S.scope=structuredClone(S.boot.profile.understanding);profileViewChanged=true}
  S.lastActiveVersion=version;
  for(const r of S.boot.jobs||[]){
    const old=jobStates.get(r.id);
    if(old==='running'&&r.status!=='running'){
      if(r.kind==='interpret'&&r.status==='complete'&&!S.dirty&&!S.scopeEdited){S.scope=structuredClone(S.boot.profile.understanding);profileViewChanged=true}
      notify(jobName(r)+' · '+(r.kind==='history_plan'&&r.status==='complete'?t('historyPlanReady'):t(r.status)),r.status==='failed');
    }
    jobStates.set(r.id,r.status);
  }
  syncCollectionButtons();const notice=$('#app-update');if(notice)notice.outerHTML=versionNotice();
  if(runningJobs().length)poll();
}
async function job(path,body={},kind){
  const result=await api(path,body);jobStates.set(result.job_id,'running');
  if(!result.already_running)notify(t('jobWorking'));
  await bootstrap();await render();if(result.already_running)focusCollection(result.job_id);poll();
}
function poll(){
  if(jobPollActive)return;jobPollActive=true;
  pollTimer=setTimeout(async()=>{
    try{await refreshVisible();if(profileViewChanged&&S.page==='research'&&!S.dirty&&!S.scopeEdited){profileViewChanged=false;await render()}}
    catch(e){fail(e)}
    finally{jobPollActive=false;if(runningJobs().length)poll()}
  },2000);
}
function resumable(r){return ['collect','analyze','history_plan','history_search','item_analysis','interpret'].includes(r.kind)&&(['paused','interrupted','failed'].includes(r.status)||(r.status==='partial'&&(r.result?.errors?.length||r.result?.analysis?.errors?.length)))}
function jobControls(r){const p=r.progress||{};return r.status==='running'?btn('pause-job','pauseJob',false,`data-id="${r.id}" ${p.pause_requested?'disabled':''}`):resumable(r)?btn('resume-job','resumeJob',false,`data-id="${r.id}" data-kind="${r.kind}"`):''}
function jobInfo(r){
  const p=r.progress||{},q=r.queue||{};
  return r.kind.startsWith('history_')?`${p.history_collected||0} ${t('historyCollected')} · ${p.history_analyzed||0} ${t('historyAnalyzed')}`:q.total?`${q.completed||0} / ${q.total}`:t(p.phase||r.status);
}
function jobReason(r){const p=r.progress||{};return `${r.error?`<p class="small warning">${esc(errorText(r.error.split(':')[0],r.error.split(':').slice(1).join(':').trim()))}</p>`:''}${p.pause_requested&&r.status==='running'?`<p class="small">${esc(t('pauseWaiting'))}</p>`:''}${p.retry_at&&r.status!=='running'&&S.boot.settings.auto_resume?`<p class="small">${esc(t('retryAt'))}: ${esc(displayDate(p.retry_at))} · ${esc(new Date(p.retry_at).toLocaleTimeString(lang()))}</p>`:''}${p.next_attempt_at?`<p class="small">${esc(t('requestRetryAt'))}: ${esc(new Date(p.next_attempt_at).toLocaleTimeString(lang()))}</p>`:''}${p.profile_learning?.status==='deferred'?`<p class="small warning">${esc(t('learningDeferred'))} ${esc(errorText(p.profile_learning.error))}</p>`:''}`}
function jobBanner(){
  const all=S.boot?.jobs||[],group=r=>r.kind+':'+(r.kind.startsWith('history_')||r.kind==='item_analysis'?r.argument?.input:'');
  const jobs=all.filter(r=>r.status==='running'||(resumable(r)&&!all.some(other=>other.id>r.id&&group(other)===group(r))));
  if(!jobs.length)return '<div id="job-status"></div>';
  const x=S.boot.execution||{};
  return `<section id="job-status" class="job-stack" aria-label="${esc(t('runs'))}"><div class="section-label"><strong>${esc(t('runs'))}</strong><div class="toolbar"><span class="small muted">${x.active||0} / ${x.limit||3} ${esc(t('activeRequests'))}${x.waiting?' · '+esc(t('parallelWaiting'))+': '+x.waiting:''}</span>${btn('concurrency-settings','parallelSettings')}</div></div>${jobs.map(r=>`<div class="job-banner" id="job-card-${r.id}"><div><strong>${r.status==='running'?'<span class="busy"></span>':''}${esc(jobName(r))}</strong> · ${esc(t(r.status))}<div class="small">${esc(jobInfo(r))}</div>${jobParallelInfo(r)}${r.progress?.model?`<div class="tiny muted">${esc(r.progress.model)} · ${esc(t('effort_'+(r.progress.reasoning_effort||'default')))}</div>`:''}${jobReason(r)}</div><div class="toolbar">${jobControls(r)}</div></div>`).join('')}</section>`;
}
function jobEvents(r){return r.events?.length?`<details class="job-events"><summary>${esc(t('taskEvents'))}</summary>${r.events.map(e=>`<p class="tiny"><time>${esc(displayDate(e.at))} ${esc(new Date(e.at).toLocaleTimeString(lang()))}</time> · ${esc(t('event_'+e.event))}<br>${esc(errorText(e.detail.split(':')[0],e.detail.split(':').slice(1).join(':').trim()))}</p>`).join('')}</details>`:''}
function runHTML(r){
  const data=typeof r.result==='string'?JSON.parse(r.result):r.result||{};
  return `<details class="run"><summary>${esc(jobName(r))} <span class="badge">${esc(t(r.status))}</span> <span class="tiny muted">${esc(displayDate(r.started_at))}</span></summary><p class="small">${esc(jobInfo(r))}</p>${jobReason(r)}${jobControls(r)}${data.errors?.length?`<pre>${esc(data.errors.join('\n'))}</pre>`:''}${data.truncated?.length?`<p class="warning">${esc(t('limitedHelp'))}</p>`:''}${jobEvents(r)}</details>`;
}
function automationControls(){const s=S.boot.settings;return `<hr><h3>${esc(t('executionTitle'))}</h3>${textInput('ai_concurrency','aiConcurrency',s.ai_concurrency||3,'number','min="1" max="8" required')}<p class="small muted">${esc(t('concurrencyHelp'))}</p><label class="check"><input name="auto_resume" type="checkbox" ${s.auto_resume?'checked':''}>${esc(t('autoResume'))}</label><p class="small muted">${esc(t('autoResumeHelp'))}</p><label class="check"><input name="adapt_saved" type="checkbox" ${s.adapt_saved?'checked':''}>${esc(t('adaptSaved'))}</label><p class="small muted">${esc(t('adaptSavedHelp'))}</p>`}
function automationStatus(){return `<div class="automation-status">${S.boot.startup?.supported?`<label class="check"><input id="login-startup" type="checkbox" ${S.boot.startup.enabled?'checked':''}>${esc(t('loginStartup'))}</label>`:''}<p class="small muted">${esc(t('startupHelp'))}</p><p class="tiny muted">${esc(t('scheduledDay'))}: ${esc(S.boot.scheduled_day||'—')}<br>${esc(t('schedulerChecked'))}: ${esc(displayDate(S.boot.scheduler?.checked_at))}</p>${S.boot.scheduler?.error?`<p class="warning">${esc(errorText(S.boot.scheduler.error))}</p>`:''}</div>`}
function learningStatus(){const active=S.boot.profile.active,l=active?.saved_learning,state=S.boot.saved_learning;if(!active)return '';return `<section id="learning-status" class="strip"><strong>${esc(t('adaptSaved'))}</strong><p class="small">${esc(t(!state?.count&&!l?.count?'learningEmpty':state?.pending?'learningPending':'learningCurrent'))}</p>${l?`<p class="tiny muted">${esc(t('learningEvidence'))}: ${l.count} / ${l.sample_count} · ${esc(displayDate(l.updated_at))}</p>`:''}${active.origin==='saved_feedback'?`<p class="small"><strong>${esc(translated(active.understanding,'field'))}</strong><br>${esc(translated(active.understanding,'rationale'))}</p>`:''}</section>`}
document.addEventListener('change',async e=>{if(e.target.id!=='login-startup')return;const enabled=e.target.checked;try{S.boot.startup=await api('/api/startup',{enabled});notify(t('startupSaved'))}catch(err){e.target.checked=!enabled;fail(err)}});
