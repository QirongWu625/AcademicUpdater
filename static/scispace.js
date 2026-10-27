'use strict';
Object.assign(COPY,{
  scispace:['SciSpace','SciSpace'],ssTitle:['Search with SciSpace','使用 SciSpace 检索'],ssManual:['Manual import','手动导入'],
  ssIntro:['Copy the research question to SciSpace, export the results, then preview and import them here. A SciSpace website account does not provide an API connection for scheduled searches.','将研究问题复制到 SciSpace，导出结果后在这里预览并导入。SciSpace 网页账号不等于可供定时检索使用的 API 连接。'],
  ssTarget:['Save results to','保存结果到'],ssQuestion:['Research question — editable','研究问题 · 可编辑'],ssCopy:['Copy question','复制问题'],ssOpen:['Open SciSpace ↗','打开 SciSpace ↗'],ssCopied:['Question copied','已复制问题'],ssCopyFallback:['Select and copy the question manually.','请选中并手动复制问题。'],
  ssFile:['Export file (CSV, RIS or JSON)','导出文件（CSV、RIS 或 JSON）'],ssFormat:['Up to 200 papers / 180 KB per import. CSV needs Title and DOI or URL; include Abstract, Authors, Journal and Year when available. JSON accepts a papers array.','每次最多 200 篇 / 180 KB。CSV 需含 Title 及 DOI 或 URL；请尽量包含 Abstract、Authors、Journal 和 Year。JSON 支持 papers 数组。'],
  ssPreview:['Preview import','预览导入'],ssImport:['Import papers','导入论文'],ssReady:['Valid candidates','有效候选论文'],ssSkipped:['Skipped rows','跳过的行'],ssEvidence:['These are candidates, not verified relevant or foundational papers. AI review uses the supplied abstract; missing abstracts mean insufficient evidence. Imported citations are reported metadata, not verified influence evidence.','这些是候选论文，尚未确认相关性或奠基地位。AI 评估依据所提供的摘要；缺少摘要意味着证据不足。导入的被引数仅为来源报告值，不作为已核实的影响力证据。'],
  ssDone:['Import saved','导入结果已保存'],ssNew:['New','新增'],ssMerged:['Already in library','已有论文'],ssUpdated:['Updated','更新'],ssTrashed:['In trash (kept there)','在回收站中（保持删除）'],ssAttached:['Added to history','加入发展史'],ssErrors:['Could not import','未能导入'],ssDateExcluded:['Outside the history date range or undated','不符合发展史年份范围或缺少年份'],
  ssNext:['Use Analyze in Library, or Review imported papers in this history, to assess relevance. Existing completed assessments are preserved.','可在资料库点击“分析”，或在发展史点击“评估导入论文”。已有评估结果保留。'],ssReview:['Review imported papers','评估导入论文'],ssHistoryImports:['Imported search results','已导入的检索结果'],
  ssSearchMethod:['AI matches the research question and methods against abstracts, with reasons and evidence. Crossref/arXiv provide text-search candidates; SciSpace imports can supplement semantic discovery. Missing abstracts are marked uncertain.','AI 根据摘要匹配研究问题与方法，并给出理由和证据。Crossref／arXiv 提供文本检索候选；SciSpace 导入可补充语义检索结果。缺少摘要时标为不确定。']
});
Object.assign(ERRORS,{
  scispace_file_size:['Use a non-empty file, at most 180 KB and 200 records.','请使用非空文件，每次不超过 180 KB、200 条记录。'],
  scispace_invalid_file:['Cannot read this export. Use CSV, RIS or JSON.','无法读取此导出文件，请使用 CSV、RIS 或 JSON。'],
  scispace_no_records:['No usable papers: each needs a title and a DOI or web link.','没有有效论文：每条记录需包含标题以及 DOI 或网页链接。'],
  scispace_history_busy:['Pause this history task and wait for it to stop before importing. Other tasks may keep running.','请先暂停该发展史任务，等待暂停完成后导入。其他任务可继续运行。'],
  scispace_manual_source:['SciSpace exports are imported manually; an API connection is not configured.','SciSpace 导出结果需手动导入；尚未配置 API 连接。']
});
const SS={revision:0,busy:false,preview:null};
function scispacePanel(){return `<section class="panel"><div class="section-label"><h2>SciSpace</h2><span class="badge">${esc(t('ssManual'))}</span></div><p class="small muted">${esc(t('ssIntro'))}</p>${btn('scispace','ssTitle')}</section>`}
function scispaceCoverage(h){return (h.progress.imports||[]).map(x=>`<div class="coverage-row"><strong>${esc(x.source)} · ${esc(t('ssManual'))}</strong> · ${x.count} ${esc(t('papersCount'))} · ${esc(displayDate(x.at))}<p class="small">${esc(x.question)}</p></div>`).join('')}
function invalidateSciSpace(){SS.revision++;SS.preview=null;const preview=$('#ss-preview');if(preview)preview.innerHTML='';if($('#ss-import'))$('#ss-import').disabled=true}
async function scispaceContext(){invalidateSciSpace();const revision=SS.revision,target=$('#ss-target').value;const result=await api('/api/scispace/context'+(target?'?history_id='+encodeURIComponent(target):''));if(revision!==SS.revision||!$('#scispace-dialog')?.open)return;$('#ss-question').value=result.question}
async function showSciSpace(){
  $('#scispace-dialog')?.remove();SS.busy=false;invalidateSciSpace();
  const dialog=document.createElement('dialog');dialog.id='scispace-dialog';dialog.setAttribute('aria-labelledby','ss-heading');
  const chosen=S.page==='history'?H.id:null;
  dialog.innerHTML=`<div class="dialog-head"><strong id="ss-heading">${esc(t('ssTitle'))}</strong><button type="button" id="ss-close" aria-label="${esc(t('close'))}">×</button></div><div class="ss-body"><p class="small muted">${esc(t('ssIntro'))}</p><label>${esc(t('ssTarget'))}<select id="ss-target"><option value="">${esc(t('library'))}</option>${(S.boot.histories||[]).map(h=>`<option value="${h.id}" ${h.id===chosen?'selected':''}>${esc(t('historyPage'))} · ${esc(historyTitle(h))}</option>`).join('')}</select></label><label>${esc(t('ssQuestion'))}<textarea id="ss-question" rows="5"></textarea></label><div class="toolbar"><button type="button" id="ss-copy">${esc(t('ssCopy'))}</button><a href="https://scispace.com/literature-review" target="_blank" rel="noopener noreferrer">${esc(t('ssOpen'))}</a></div><hr><label>${esc(t('ssFile'))}<input id="ss-file" type="file" accept=".csv,.ris,.json,text/csv,application/json,application/x-research-info-systems"></label><p class="tiny muted">${esc(t('ssFormat'))}</p><p class="small ss-evidence">${esc(t('ssEvidence'))}</p><div class="toolbar"><button type="button" id="ss-preview-button">${esc(t('ssPreview'))}</button><button type="button" id="ss-import" class="primary" disabled>${esc(t('ssImport'))}</button></div><div id="ss-preview" aria-live="polite"></div><div id="ss-result" aria-live="polite"></div></div>`;
  document.body.append(dialog);dialog.showModal();
  dialog.addEventListener('cancel',e=>{if(SS.busy)e.preventDefault()});
  $('#ss-close').onclick=()=>{if(!SS.busy){invalidateSciSpace();dialog.close()}};
  $('#ss-target').onchange=()=>scispaceContext().catch(fail);
  $('#ss-question').oninput=invalidateSciSpace;$('#ss-file').onchange=invalidateSciSpace;
  $('#ss-copy').onclick=async()=>{try{await navigator.clipboard.writeText($('#ss-question').value);notify(t('ssCopied'))}catch{$('#ss-question').select();notify(t('ssCopyFallback'))}};
  $('#ss-preview-button').onclick=()=>previewSciSpace().catch(fail);$('#ss-import').onclick=()=>importSciSpace().catch(fail);
  await scispaceContext();
}
function scispaceBusy(value){SS.busy=value;for(const selector of ['#ss-target','#ss-question','#ss-file','#ss-preview-button','#ss-close'])$(selector).disabled=value;$('#ss-import').disabled=value||!SS.preview}
function scispacePreviewHTML(data){return `<h3>${data.count} ${esc(t('ssReady'))}</h3>${data.skipped_rows.length?`<p class="warning">${esc(t('ssSkipped'))}: ${esc(data.skipped_rows.join(', '))}</p>`:''}${data.outside_year?`<p class="warning">${esc(t('ssDateExcluded'))}: ${data.outside_year}</p>`:''}<ol class="ss-samples">${data.sample.map(p=>`<li><strong>${esc(p.title)}</strong><p class="tiny muted">${esc(p.authors.join('; '))}<br>${esc(p.journal||t('journalUnknown'))} · ${esc(p.published_at||'—')}<br>${esc(p.doi||'')}</p></li>`).join('')}</ol>`}
async function previewSciSpace(){
  if(SS.busy)return;invalidateSciSpace();scispaceBusy(true);
  try{const file=$('#ss-file').files[0];if(!file||file.size>180000)throw {code:'scispace_file_size'};
    const payload={content:await file.text(),format:'auto',question:$('#ss-question').value,history_id:$('#ss-target').value||null};
    const data=await api('/api/scispace/preview',payload);SS.preview=payload;$('#ss-preview').innerHTML=scispacePreviewHTML(data);$('#ss-result').innerHTML='';
  }finally{scispaceBusy(false)}
}
async function importSciSpace(){
  if(SS.busy||!SS.preview)return;scispaceBusy(true);
  try{const result=await api('/api/scispace/import',SS.preview);SS.preview=null;
    $('#ss-result').innerHTML=`<h3>${esc(t('ssDone'))}</h3><p>${[['new','ssNew'],['duplicates','ssMerged'],['updated','ssUpdated'],['trashed','ssTrashed'],['history_added','ssAttached'],['outside_year','ssDateExcluded']].map(([k,label])=>`${esc(t(label))}: ${result[k]||0}`).join(' · ')}</p>${result.errors.length?`<p class="warning">${esc(t('ssErrors'))}: ${result.errors.length}</p>`:''}<p class="small muted">${esc(t('ssNext'))}</p>`;
    await refreshVisible();
  }finally{scispaceBusy(false)}
}
