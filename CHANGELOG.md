# Changelog / 更新记录

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
