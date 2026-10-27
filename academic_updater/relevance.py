"""Shared evidence policy for daily and historical semantic assessment."""
SEMANTIC_RELEVANCE='''Judge semantic relevance from the research question and the paper abstract, not title/keyword overlap or shared acronyms. Identify the requested problem, method, target/population and explicit exclusions. Read what the study actually investigates, how it does so and its target. Equivalent terminology can be a direct match without any matching keyword. High means a direct match to the core question and required constraints; medium means a useful but partial or adjacent match; low means broad-discipline overlap only, a different problem, or an explicit exclusion; uncertain means insufficient evidence. Do not require incidental preferences as hard constraints, and do not invent constraints. Explain the matched problem/method and material mismatch or missing evidence in the bilingual reason, with exact abstract evidence where available. A TMS paper is not automatically relevant to personalized MRI-guided neuronavigation. Citation count, journal IF and search rank never establish relevance. Missing abstracts must be uncertain rather than judged from the title alone.'''


def require_abstract(answer,abstract):
    """A metadata-only candidate is never promoted to a relevant/landmark result."""
    if abstract and abstract.strip():return
    answer['relevance']='uncertain'
    answer['reason_en']='No abstract was supplied. Title and metadata alone are insufficient to judge semantic relevance.'
    answer['reason_zh']='未提供摘要。仅凭标题和元数据不足以判断语义相关性。'
    if 'role' in answer:answer['role']='uncertain'
