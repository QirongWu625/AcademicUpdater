# Changelog / 更新记录

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
