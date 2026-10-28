# Changelog / 更新记录

## 1.9.2 — 2026-10-28

- Handle null author institution lists and incomplete affiliation records without aborting author interpretation.
- When a requested company is missing from an author profile, check the same author ID in up to 100 recent paper bylines. Retain linked evidence, reject coauthor affiliations and ambiguous matches, and keep author searches across the full career.
- Show the affiliation evidence in Chinese and English and let failed interpretation tasks resume without losing saved data.

修复作者机构信息为空导致的 TypeError；支持用本人论文署名中的原始机构名称核对公司任职，展示来源依据，避免误用共同作者的机构。

## 1.9.1 — 2026-10-28

- Keep expanded and collapsed sections stable during live refreshes, including task records, nested task events, research-history coverage and paper evidence. Match sections by record ID, not list position or translated text.
- Preserve disclosure keyboard focus and read the latest open state immediately before rendering, including clicks while requests are in flight. Existing papers, saved searches, analyses and settings are unchanged.

修复折叠区域在自动刷新后自行收起的问题；按任务、检索和论文标识保留展开／收起状态及键盘焦点，兼容列表重排与中英文切换。

## 1.9.0 — 2026-10-27

- Add an optional third-party IF fallback after publisher verification fails, using actual AI page-open events and dated journal records from Bioxbio, LetPub or WoS Journal Info. Keep references distinct from official/AI publisher verification.
- Label references on paper cards, show the metric year and direct source link, count them separately in Profile, and include the provenance status in CSV/JSON exports. The option can be disabled in Profile.
- Reject CiteScore, Scopus impact scores, five-year IF, estimates, mismatched journals and release-year confusion. Resolve print/electronic ISSN aliases through OpenAlex records rather than AI guesses.
- Prevent references from replacing same-year publisher values or manual corrections. Preserve existing papers, source evidence, saved feedback, analyses and task checkpoints.

官方来源无法核验时，可自动补充第三方 IF 参考值，单独标注年份、来源链接与参考身份；不覆盖同年份官方核验值或手动修正。支持纸质／电子版 ISSN 核对，保留旧资料及任务进度。

## 1.8.2 — 2026-10-27

- Keep one journal IF task running across batches until all eligible journals have either a result or a recorded failure. Checkpoint cumulative progress, distinguish waiting from in-flight journals, and restore unfinished entries after interruption.
- Make repeated Retry clicks return the active task without resetting its failures or creating competing jobs. Empty queues do not create placeholder runs.
- Refresh IF counts and failure details in Profile and Sources without overwriting unsaved settings. Keep observing automatic work between batches and show processed/found/unavailable/failed counts.
- Preserve manual pauses and authentication/budget barriers with visible reasons. A broken journal record does not stop other journals; unrelated scheduler errors no longer prevent IF scheduling.

修复个人资料中 IF 数字不刷新、重试重置运行中队列的问题；同一任务持续处理全部待查期刊，显示等待、查询中、已查到及失败进度，保留暂停恢复与旧资料。

## 1.8.1 — 2026-10-27

- Fix OpenAlex daily semantic requests: use the supported publication-year filter, then enforce the exact date window locally. Resume previously failed sources even when an older run saved its phase as analysis; keep successful sources and finished assessments.
- Treat daily candidate caps as completed with a coverage notice. Actual source and analysis failures remain resumable.
- Retain completed streaming output items when the final response omits them, restoring detection of real AI web-search and page-open events.
- Resolve legacy Oxford/Frontiers journal homepages, verify publisher table columns and metric-year statements, and match uppercase ISSN check digits. Requeue previously failed IF lookups once; manual Refresh retries missing values immediately.
- When a publisher declines direct HTML access, accept only two agreeing independent AI web reads with actual page-open events, journal/ISSN identity and explicit dated JIF statements. Label these **AI web sources**, separately from directly verified publisher text. Conflicting readings are not saved. Preserve manual corrections.
- Display recent IF lookup errors in Profile. Existing papers, saved feedback, analyses, searches and credentials are preserved.

修复采集断点续作和 OpenAlex 日期参数；区分采集上限与实际失败。恢复 AI 联网查询识别，改进期刊旧网址、IF 表格与年份核验。区分官网原文核验与 AI 联网查证，自动重试旧的缺失 IF，并保留已有资料。

## 1.8.0 — 2026-10-27

- Add OpenAlex embedding retrieval and author identity resolution, with editable interpreted strategy, per-work authorship checks, explicit coverage limits and unrestricted author bibliographies when requested.
- Automatically queue new and existing missing journal IF. Use AI web search or fetched publisher pages; verify two-year JIF, metric year, journal identity and exact source evidence. Preserve manual corrections and show unavailable values honestly.
- Add bilingual profile data-clear controls with typed confirmation, an idle-task barrier and a unique restorable backup. Preserve settings/credentials/usage, pause scheduling, and never clear data during upgrades.
- Allow daily AI limit 0 (unlimited) and 1–64 shared parallel requests, with up to 16 independent jobs. Raising an exhausted budget makes paused work eligible for retry.
- Remove SciSpace UI, routes and import implementation; preserve previously imported records and their provenance. Existing searches and assessments keep their original checkpoints.

新增语义召回、作者身份检索、自动 IF 核验和带备份确认的数据清空入口；支持不限每日额度及最高 64 个共享并发请求；移除 SciSpace 功能并保留旧资料。

## 1.7.0 — 2026-10-27

- Add bilingual SciSpace CSV/RIS/JSON preview and manual import into Library or a saved research history, with editable research questions and source provenance. Website/connector access is not presented as a standalone API integration.
- Preserve DOI/URL identities, existing bibliography, feedback, analyses and trash; honor history year bounds and checkpoints. New history candidates can be assessed without repeating completed work.
- Use complete planned queries in daily arXiv retrieval and relevance-ranked Crossref alternatives with a shared cap. Strengthen AI retrieval planning and abstract-based semantic assessment; papers without abstracts remain uncertain.
- Document text-retrieval versus semantic-assessment limits and verify the UI with synthetic import records.

新增 SciSpace 手动导入和中英文入口；改进候选检索及摘要语义评估。保留旧资料、分析和任务断点。尚未实现 SciSpace API 自动检索，也不声称已读取全文。

## 1.6.3 — 2026-10-27

- Running and resumed tasks adopt the current model and reasoning effort on each unsent AI request within the same connection, including requests waiting for a slot and retries. Requests already dispatched retain their own settings. Provider and local endpoint changes do not redirect existing tasks.
- Show next-request settings separately from actual in-flight model/effort counts. Clarify when saved AI settings take effect.
- Keep completed daily and history assessments, record the actual settings for new history classifications, and preserve task scopes and checkpoints.

修复运行中任务一直沿用旧推理档位的问题：同一 AI 连接下，后续请求采用最新模型与档位；已发出的请求正常完成，已完成论文不重跑。界面分别显示“后续请求”与“正在执行的请求”。

## 1.6.2 — 2026-10-27

- Add a bilingual Set parallelism control beside active tasks and in AI connection. Change the shared limit from 1 to 8 without pausing or restarting tasks; the dialog retains edits during progress refreshes.
- Show each task's actual active AI request count and the global waiting count. Explain per-paper versus history-batch processing and why completion counts arrive incrementally.
- Verify that increasing concurrency admits additional requests during a running task and lowering it drains existing requests before admitting more work.

新增任务进度旁的“设置并发数量”入口，可即时调节 1–8 个共享 AI 请求；显示各任务实际并发数及等待数。修改时无需中断任务，保留论文和既有分析进度。

## 1.6.1 — 2026-10-27

- Repeated Collect updates requests return the current day's active collection instead of a conflict, including simultaneous clicks and requests racing scheduled collection.
- Replace Collect updates with View collection progress while that collection is running; keep independent history searches and next-day collection available. Refresh the button as background tasks start or finish.
- Show a refresh notice after application upgrades without discarding unsaved edits automatically. Clarify the duplicate-task message in both languages.

修复采集按钮的误导提示：采集已在运行时，重复点击会显示现有进度；不新建重复任务。保留跨任务并行，并提示已打开的旧界面刷新。

## 1.6.0 — 2026-10-27

- Run daily collection, independent historical searches and paper analysis concurrently. Share a fair AI request limit (default 3, adjustable 1–8); checkpoint each completed paper or history batch. Prevent duplicate work on the same paper/version/scope/model.
- Recover all eligible interrupted tasks, retry temporary connection errors with backoff, resume daily-budget pauses after local midnight, and retain manual pauses. Show interruption causes, retry times and recovery events per task. Network recovery stops after five automatic job retries; configuration and sign-in errors require attention.
- Catch up missed daily collection on startup, keep the scheduler alive after unexpected errors, and allow the next day's update while an older analysis is still running. Add optional Windows login startup in Personal profile → Sources & schedule.
- Before a new collection, recompute the understood research field when the current saved-paper set changes. Preserve the original prompt, exclusions, unapplied drafts and historical-search scopes. Removing all saved papers restores the baseline; unchanged sets make no learning request. Large saved sets use an explicitly reported sample of up to 80 papers.
- Preserve existing data, model/effort settings and resumable checkpoints. Add parallelism, recovery, budget, scheduling and saved-feedback regression tests plus bilingual multi-job controls.

支持跨任务并行、共享 AI 并发上限、自动补跑、断点恢复与退避重试；新增 Windows 登录自启设置。收藏增减后在采集前更新领域理解，保留原始提示词与排除条件；手动暂停、旧论文及既有分析继续保留。

## 1.5.0 — 2026-10-26

- Separate Trash navigation with live search and Library records / Historical searches tabs; preserve the old history-trash link.
- Distinguish AI field interpretation from paper retrieval and put a clear confirmation/start button above the search form.
- Fix quoted phrases, OR alternatives and parentheses in historical queries. Compile arXiv Boolean expressions correctly; split Crossref alternatives within the original per-query/source cap.
- Distinguish pending assessment, empty shortlists, source failures and actual zero-result searches, with direct access to all candidates.
- Retain existing records and trash contents. On explicit resume, replay legacy Boolean queries with the corrected adapter and archive their previous cursors; keep saved papers and assessments. Verify query behavior with live TMS metadata and regression tests.

新增独立回收站；明确区分“理解领域”和“检索论文”。修复历史检索式转换，区分待评估、暂无入选、来源失败与真正无结果，保留旧数据和任务进度。

## 1.4.0 — 2026-10-26

- Delete and restore library records and saved historical searches through separate trash views, with bilingual confirmation and immediate refresh.
- Preserve notes, analyses, identities and search progress; old databases migrate automatically without removing records.
- Exclude trashed papers from daily updates, historical results, analysis queues and exports. Collection respects deletions; hidden searches cannot resume until restored.
- Guard deletion/restoration while a task is running and hide timelines whose cited evidence was removed.

新增资料库与历史检索的删除、回收站及恢复功能。旧资料自动兼容，保留笔记、分析和检索进度；采集不会自动加回已删除论文，已删除检索不会自动恢复运行。

## 1.3.0 — 2026-10-26

Initial public source release under MIT.

- New application logo, browser icon and illustrated English/Chinese README.
- Historical discovery defaults to influential and foundational candidates, combining Crossref citation-ranked and relevance-ranked searches within the configured cap.
- Citation provenance and adjustable thresholds; abstract-supported foundational candidates, shortlist filters and a timeline restricted to qualifying papers.
- Existing searches, records and resumable jobs remain compatible.

首次公开发布源码；新增 Logo、双语真实应用截图、引用依据与可调门槛、奠基性候选筛选，并保留旧资料和检索兼容。

## 1.2.0 — 2026-10-26

Earlier local release, included in the initial public source distribution.

- Saved historical searches with editable bilingual AI field interpretation, source paging, relevance assessment and referenced timelines.
- Research field, sources/schedule and AI connection grouped under Personal profile.
- Historical candidates deduplicated against the existing library; historical-only discoveries do not fill the daily inbox.
- Checkpointed search and analysis with pause/resume and restart recovery.
- English/Chinese installation and contribution guides, issue/PR templates, public-tree checks and CI configuration.

首次以 MIT 许可证公开源码。新增保存的历史检索、研究领域解释、时间线及恢复能力，并把设置整合到个人中心；提供双语协作说明与自动检查配置。

## Earlier local development

### 1.1.0

- Supported reasoning-effort selection, author/journal display and user-supplied journal metrics.
- Relevance ordering and colors, live filtering, additional library sorting and resumable analysis.
- Migration support for existing papers and analyses.

增加推理强度、作者期刊与用户提供的 IF、相关性排序及颜色、实时筛选和中断恢复，并支持旧数据迁移。

### 1.0.0

- Local Python/SQLite application with Crossref, arXiv and RSS/Atom collection.
- Editable research scope, identifier deduplication, bilingual UI, library notes, exports and backups.
- ChatGPT sign-in integration, OpenAI API and local model connection options.

实现本机采集与资料库、可编辑研究范围、去重、双语界面、笔记导出备份及多种 AI 连接方式。
