# Influential and foundational papers / 高影响力与奠基性论文

New topic searches default to **Focus on influential & foundational work**. Existing saved searches retain their previous scope, results and resume checkpoints. Copy an old search to create a new focused search.

新主题检索默认聚焦高影响力与奠基性论文。旧检索保留原范围、结果和恢复进度；可复制旧检索，以新模式重新搜索。

Author mode resolves the person by name, institution and optional ORCID, retrieves by author ID, and validates every authorship. No requested topic means no topic filter; earlier institutions are included. Ambiguous identities are not guessed.

作者模式按姓名、机构与可选 ORCID 核对身份，按作者标识检索并逐条核对署名。不限定主题时不增加主题过滤，包含早期机构成果；同名无法消歧时不猜测。

## Retrieval / 获取候选

OpenAlex uses title/abstract embeddings for natural-language descriptions (up to 50 results per description). It supplies observed citation counts, with explicit source caps and errors. Crossref/arXiv remain complementary text retrieval.

OpenAlex 使用标题／摘要向量进行自然语言召回，每条描述最多 50 篇，保留实际引用数、来源上限及错误。Crossref／arXiv 提供补充文本检索。

For Crossref, each query uses two independently checkpointed streams: citation-count order and relevance order. A finite per-source/per-query candidate limit is divided equally between them; duplicate records are reconciled. arXiv uses relevance order and supplies no citation count through this connector. Publication-year bounds apply to both sources.

Crossref 同时按引用量与相关性检索，每条检索保存独立进度。有限的每来源、每检索词上限在两种排序间平分，重复记录合并。arXiv 按相关性检索，此连接不提供引用数。两类来源都应用发表年份范围。

## Shortlist / 入选条件

AI must first assess the paper as highly or moderately relevant to the saved field. It then needs at least one of:

1. An observed OpenAlex or Crossref citation count meeting the configured threshold (default **100**, editable).
2. An AI classification as a foundational candidate with an exact supporting quotation from the supplied abstract. A title-only quotation, publication age, journal IF or author reputation does not satisfy this rule.

先由 AI 判断与领域高度相关或相关，再满足至少一个条件：OpenAlex 或 Crossref 实际引用数达到可编辑门槛（默认 100），或被判断为奠基性候选且有摘要中的直接引文支持。仅凭标题、年份、期刊 IF 或作者声望不能满足奠基性规则。

Counts, provider, observation date and source link are stored with the search snapshot. The model cannot supply or overwrite citation counts. Missing citation data stays missing, rather than becoming zero. A relevant paper meeting a citation threshold is a candidate for influence, not a proven landmark. The foundation label remains a candidate requiring specialist review; an abstract quotation supports the described contribution, not the whole historical influence claim.

引用数、来源、查询日期及链接随检索快照保存，不由模型生成或覆盖；缺失不当作零。达到引用门槛不等于已经证实的里程碑。摘要引文只支持所描述的贡献，不能独自证明其历史影响；奠基性候选仍需专业核查。

The default result view and timeline use shortlisted papers only. Other retrieved candidates remain in the saved search and Library for audit and deduplication, accessible through **All retrieved candidates** and **Reviewed, not shortlisted**. A search with no qualifying papers produces no speculative milestones. AI analysis is required in focused mode; incomplete analysis, source errors and daily limits remain visible and resumable.

默认结果视图和时间线仅使用入选论文。其他候选保留在检索及资料库中，便于追溯和去重，可通过“全部检索候选”“已评估但未入选”查看。没有合格论文时不会编造里程碑。精选模式需要 AI 分析，未完成的分析、来源错误和额度限制会显示并可恢复。

The threshold is a transparent heuristic, not a field-normalized bibliometric measure. Coverage differs by discipline, publication year and deposited references. Search wording and source caps also affect recall. The overview samples at most 80 eligible papers across publication years.

门槛是透明的筛选规则，并非经过学科归一化的计量指标。学科、年份、参考文献提交情况、检索词及来源上限都会影响覆盖。发展概述最多使用按年份选取的 80 篇合格论文。

Source documentation: [Crossref REST sorting](https://github.com/CrossRef/rest-api-doc#sorting), [Crossref Cited-by coverage](https://www.crossref.org/documentation/cited-by/).
