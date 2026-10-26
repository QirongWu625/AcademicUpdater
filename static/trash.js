'use strict';
const T={kind:'items',query:'',rows:[],request:0};
Object.assign(COPY,{
  trash:['Trash','回收站'],rebuildTimeline:['Update timeline','更新发展时间线'],listLimit:['Showing up to 300 matching items. Exports include all active library records, excluding trash.','最多显示 300 条匹配结果。导出包含全部正常资料库条目，不含回收站。'],deleteRecord:['Delete','删除'],moveToTrash:['Move to trash','移至回收站'],
  cancelRemoval:['Cancel','取消'],restoreRecord:['Restore','恢复'],movedToTrash:['Moved to trash. You can restore it there.','已移至回收站，可在回收站恢复。'],
  restoredRecord:['Restored.','已恢复。'],emptyTrash:['Trash is empty','回收站为空'],
  deleteHistoryHint:['This search and its results will be hidden. Papers in your library will remain. You can restore the search, its results and its progress from the history trash.','此检索及其结果将被隐藏，资料库中的论文不会删除。可从历史检索回收站恢复检索、结果和进度。'],
  deletePaperHint:['This record will be hidden from your library, Today and historical results. Collection will not add it back automatically. Saved notes and analyses are kept for restoration.','此条目将从资料库、今日更新和历史检索结果中隐藏，采集时不会自动加回。已保存的笔记与分析会保留，供恢复使用。'],
  discardUnsaved:['Unsaved edits to this record will be discarded.','此条目尚未保存的编辑将被丢弃。'],
  paperTrashHint:['Removed records stay here until you restore them. Saved notes and analyses are retained. Exports contain active records; a database backup includes the trash.','删除的条目会保留在这里，直到你恢复。已保存笔记与分析会保留。导出仅包含正常条目，数据库备份包含回收站。'],
  historyTrash:['Research history · Trash','研究发展史 · 回收站'],
  historyTrashHint:['Restore a search with its saved results and progress. Deleting a search does not delete library records.','可恢复检索及已保存的结果和进度。删除检索不会删除资料库条目。'],
  backToHistories:['Back to research history','返回研究发展史'],
  trashSub:['Deleted library records and historical searches, together in one place. Restore them whenever needed.','集中管理已删除的资料条目和历史检索，可随时恢复。'],
  trashItems:['Library records','资料条目'],trashHistories:['Historical searches','历史检索'],
  trashSearch:['Search deleted records','搜索已删除的条目'],backToLibrary:['Back to library','返回资料库'],trashLimit:['Up to 300 matching library records are shown. Use search to find a specific record.','最多显示 300 条匹配资料，可搜索查找特定条目。'],
  reportRemovedEvidence:['The saved timeline cites papers now in the trash, so it is hidden. Restore those papers to show the original timeline, or run this search again to synthesize the remaining evidence.','已保存的时间线引用了回收站中的论文，因此暂时隐藏。恢复这些论文可查看原时间线，或再次运行此检索，基于剩余证据生成概述。']
});
Object.assign(ERRORS,{
  pause_before_delete:['Pause the current task and wait for it to stop before deleting or restoring records.','请先暂停当前任务，等待任务停止后再删除或恢复条目。'],
  item_in_trash:['This record is in the library trash. Restore it there before importing or analyzing it.','此条目已在资料库回收站中。请先恢复，再导入或分析。']
});
function deleteButton(kind,id){return `<button type="button" class="danger-link" data-action="${kind}-delete" data-id="${id}">${esc(t('deleteRecord'))}</button>`}
function confirmRemoval(kind,title,unsaved=false){
  return new Promise(resolve=>{
    const dialog=document.createElement('dialog');dialog.className='remove-dialog';
    dialog.setAttribute('aria-labelledby','remove-title');dialog.setAttribute('aria-describedby','remove-description');
    dialog.innerHTML=`<h2 id="remove-title">${esc(t('moveToTrash'))}</h2><p class="remove-name">${esc(title)}</p><p id="remove-description">${esc(t(kind==='history'?'deleteHistoryHint':'deletePaperHint'))}</p>${unsaved?`<p class="warning">${esc(t('discardUnsaved'))}</p>`:''}<div class="toolbar"><button type="button" data-cancel>${esc(t('cancelRemoval'))}</button><button type="button" class="danger" data-confirm>${esc(t('moveToTrash'))}</button></div>`;
    document.body.append(dialog);dialog.returnValue='cancel';
    dialog.querySelector('[data-cancel]').onclick=()=>dialog.close('cancel');
    dialog.querySelector('[data-confirm]').onclick=()=>dialog.close('confirm');
    dialog.addEventListener('close',()=>{const confirmed=dialog.returnValue==='confirm';dialog.remove();resolve(confirmed)},{once:true});
    dialog.showModal();dialog.querySelector('[data-cancel]').focus();
  });
}
async function manageRecord(action,id){
  const [kind,operation]=action.split('-'),deleted=operation==='delete';id=Number(id);
  const record=kind==='history'?S.boot.histories.find(h=>h.id===id):S.items.find(i=>i.id===id)||S.detail;
  const title=record?(kind==='history'?historyTitle(record):record.title):'#'+id;
  const unsaved=kind==='history'?H.id===id&&H.dirty:Object.hasOwn(S.noteDrafts,id);
  if(deleted&&!await confirmRemoval(kind,title,unsaved))return;
  await api(`/api/${kind==='history'?'histories':'items'}/${id}/${operation}`,{});
  if(kind==='history'&&deleted&&H.id===id){
    H.id=null;H.detail=null;H.draft=null;H.dirty=false;H.filter=null;H.papers=null;H.offset=0;H.query='';H.request++;
    history.replaceState(null,'','#history');
  }
  if(kind==='item'){
    delete S.noteDrafts[id];
    if(S.detail?.id===id){$('#detail').close();S.detail=null}
  }
  await bootstrap();await render();notify(t(deleted?'movedToTrash':'restoredRecord'));
}
function trashItemCard(i){return `<article class="item trash-item" data-item="${i.id}"><div class="item-top"><span class="badge">${esc(t('trash'))}</span><span>${esc(displayDate(i.deleted_at))}</span></div><h3>${esc(i.title)}</h3>${bibliographyHTML(i)}<p class="small muted">${esc(t('paperTrashHint'))}</p><div class="actions">${btn('item-restore','restoreRecord',false,`data-id="${i.id}"`)}</div></article>`}
function historyTrashRows(rows){return rows.length?rows.map(h=>`<article class="panel"><h2>${esc(historyTitle(h))}</h2><p class="small muted">${esc(h.prompt)}</p><p class="small">${h.count} ${esc(t('papersCount'))} · ${esc(displayDate(h.deleted_at))}</p>${btn('history-restore','restoreRecord',false,`data-id="${h.id}"`)}</article>`).join(''):`<div class="empty"><h2>${esc(t(T.query?'noResults':'emptyTrash'))}</h2></div>`}
async function loadTrash(){
  const request=++T.request,kind=T.kind,query=T.query;
  let rows=await api(kind==='items'?'/api/items?deleted=1&q='+encodeURIComponent(query):'/api/histories?deleted=1');
  if(kind==='histories'&&query.trim())rows=rows.filter(h=>[h.prompt,h.scope?.field_en,h.scope?.field_zh].join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  if(request!==T.request||kind!==T.kind||query!==T.query)return false;
  T.rows=rows;return true;
}
function trashRows(){return T.kind==='histories'?historyTrashRows(T.rows):T.rows.length?T.rows.map(trashItemCard).join(''):`<div class="empty"><h2>${esc(t(T.query?'noResults':'emptyTrash'))}</h2></div>`}
async function trashPage(){
  await loadTrash();const items=T.kind==='items';
  return header('trash','trashSub',`<a href="${items?'#library':'#history'}">${esc(t(items?'backToLibrary':'backToHistories'))}</a>`)+`<div class="profile-tabs" role="navigation" aria-label="${esc(t('trash'))}">${['items','histories'].map(k=>`<a href="#trash/${k}" ${T.kind===k?'class="active" aria-current="page"':''}>${esc(t(k==='items'?'trashItems':'trashHistories'))}</a>`).join('')}</div><label>${esc(t('trashSearch'))}<input id="trash-search" value="${esc(T.query)}" placeholder="${esc(t('trashSearch'))}"></label><p class="small muted">${esc(t(items?'paperTrashHint':'historyTrashHint'))}</p>${items?`<p class="tiny muted">${esc(t('trashLimit'))}</p>`:''}<div id="trash-results">${trashRows()}</div>`;
}
async function refreshTrash(){if(S.page==='trash'&&await loadTrash()&&S.page==='trash'&&$('#trash-results'))$('#trash-results').innerHTML=trashRows()}
let trashSearchTimer;
document.addEventListener('input',e=>{if(e.target.id==='trash-search'){T.query=e.target.value;clearTimeout(trashSearchTimer);trashSearchTimer=setTimeout(()=>refreshTrash().catch(fail),250)}});
