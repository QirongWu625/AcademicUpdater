"""Semantic discovery and author-identity retrieval from documented public APIs."""
import datetime as dt
import re
import threading
import time
import unicodedata
import urllib.parse
from .network import AppError,get_json,doi,plain

_semantic_lock=threading.Lock()
_semantic_last=0.0
RETRIEVAL_PROPERTIES={
    'mode':{'type':'string','enum':['topic','author']},
    **{k:{'type':'string'} for k in ('author_name','institution','orcid','topic_constraint')},
    'semantic_queries':{'type':'array','items':{'type':'string'}}}
RETRIEVAL_SCHEMA={'type':'object','properties':RETRIEVAL_PROPERTIES,'required':list(RETRIEVAL_PROPERTIES),'additionalProperties':False}
INTENT_INSTRUCTIONS='''Identify whether the user wants a TOPIC or the outputs of a specific AUTHOR. For author requests extract the full name, institution and ORCID only if provided. Institution identifies the person; do not restrict all career papers to that institution. If the user says no topic/discipline/method restriction, topic_constraint MUST be empty and do not invent one from your knowledge of the author. Author requests default to all that author\'s outputs, not landmark-only. For topic requests create 1-3 complementary natural-language English descriptions (not keyword lists), including the problem, required method/target and semantic alternatives for embedding retrieval. Do not invent IDs or papers.'''


def normalize_plan(value):
    value=value or {}
    if not isinstance(value,dict) or value.get('mode','topic') not in ('topic','author'):raise AppError('invalid_retrieval_plan')
    plan={'mode':value.get('mode','topic')}
    for k in ('author_name','institution','orcid','topic_constraint'):plan[k]=str(value.get(k,'')).strip()[:1000]
    queries=value.get('semantic_queries',[])
    if not isinstance(queries,list) or len(queries)>3 or any(not isinstance(q,str) or not q.strip() or len(q)>2000 for q in queries):raise AppError('invalid_retrieval_plan')
    plan['semantic_queries']=queries
    if plan['mode']=='author' and not plan['author_name']:raise AppError('author_name_required')
    if plan['orcid'] and not re.fullmatch(r'(?:https://orcid.org/)?\d{4}-\d{4}-\d{4}-[\dX]{4}',plan['orcid']):raise AppError('invalid_retrieval_plan')
    return plan


def openalex(path,params=None,semantic=False):
    global _semantic_last
    # Public access only; do not inspect or transmit account keys.
    params=dict(params or {})
    url='https://api.openalex.org/'+path+('?' + urllib.parse.urlencode(params) if params else '')
    if semantic:
        with _semantic_lock:
            time.sleep(max(0,1-(time.monotonic()-_semantic_last)))
            try:return get_json(url,timeout=60)
            finally:_semantic_last=time.monotonic()
    return get_json(url,timeout=60)


def normalized(value):
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]+',' ',''.join(c for c in unicodedata.normalize('NFKD',value).casefold() if not unicodedata.combining(c))).strip()


def resolve_author(plan):
    data=openalex('authors',{'search':plan['author_name'],'per_page':25});candidates=[]
    for row in data.get('results',[]):
        institutions=list({x.get('display_name','') for x in row.get('last_known_institutions',[]) if x.get('display_name')}|{a.get('institution',{}).get('display_name','') for a in row.get('affiliations',[]) if a.get('institution',{}).get('display_name')})
        names=[row.get('display_name',''),*(row.get('display_name_alternatives') or [])]
        name_match=normalized(plan['author_name']) in {normalized(n) for n in names}
        institution_match=not plan['institution'] or any(set(normalized(alias).split())<=set(normalized(i).split()) for alias in re.split(r'[/／;|]',plan['institution']) if normalized(alias) for i in institutions)
        orcid_match=not plan['orcid'] or (row.get('orcid') or '').removeprefix('https://orcid.org/')==plan['orcid'].removeprefix('https://orcid.org/')
        if name_match and institution_match and orcid_match and re.fullmatch(r'https://openalex.org/A\d+',row.get('id','')):
            candidates.append({'id':row['id'],'name':row['display_name'],'orcid':row.get('orcid') or '',
                               'institutions':sorted(institutions),'works_count':row.get('works_count',0),'source_url':row['id'],'verified_at':dt.datetime.now(dt.timezone.utc).isoformat()})
    if len(candidates)!=1:raise AppError('author_identity_ambiguous','Matching identities: '+str(len(candidates))+'. Refine the full name, institution or ORCID.')
    return candidates[0]


def abstract_text(index):
    if not isinstance(index,dict):return ''
    words={}
    for word,positions in index.items():
        if not isinstance(positions,list):continue
        for position in positions:
            if isinstance(position,int) and not isinstance(position,bool) and 0<=position<20000:words[position]=word
    return ' '.join(str(words[p]) for p in sorted(words))[:60000]


def work_record(row):
    location=row.get('primary_location') or {};source=location.get('source') or {}
    authorships=row.get('authorships') or [];identifier=doi(row.get('doi'))
    url=('https://doi.org/'+identifier) if identifier else location.get('landing_page_url') or row['id']
    if url.startswith('http://'):url='https://'+url[7:]
    authors=[a.get('author',{}).get('display_name','') for a in authorships]
    return {'kind':'paper','title':plain(row.get('title') or row.get('display_name') or ''),'abstract':abstract_text(row.get('abstract_inverted_index')),
            'doi':identifier,'url':url,'external_id':row['id'],'authors':authors,'published_at':row.get('publication_date'),
            'journal':source.get('display_name',''),'issns':source.get('issn') or [source.get('issn_l','')],
            'venue_type':'preprint' if row.get('type')=='preprint' or source.get('type')=='repository' else 'journal' if source.get('type')=='journal' else 'unknown',
            'version':'','raw_metadata':{'provider':'OpenAlex','id':row['id'],'authorships':authorships,'cited_by_count':row.get('cited_by_count'),
                                       'referenced_works':row.get('referenced_works') or [],'source':source}}


def discovery_page(query,config,state,size=100):
    size=min(size,100);filters=[]
    if config.get('year_from'):filters.append('from_publication_date:'+str(config['year_from'])+'-01-01')
    if config.get('year_to'):filters.append('to_publication_date:'+str(config['year_to'])+'-12-31')
    if state.get('since'):filters.append('from_publication_date:'+state['since'])
    semantic=state.get('mode')!='author';position=state.get('position',0)
    if semantic:
        size=min(size,50-position)
        if size<=0:return [],{'position':position,'done':True,'source_limited':True,'total':50}
        params={'search.semantic':query[:2000],'per_page':size}
    else:
        if position>=10000:return [],{'position':position,'done':True,'source_limited':True,'total':state.get('total')}
        identifier=state.get('author_id','')
        if not re.fullmatch(r'https://openalex.org/A\d+',identifier):raise AppError('author_identity_required')
        filters.append('authorships.author.id:'+identifier.rsplit('/',1)[1])
        page_size=state.get('page_size',size);params={'per_page':page_size,'page':state.get('page',1),'sort':'publication_date:desc'}
    if filters:params['filter']=','.join(filters)
    data=openalex('works',params,semantic=semantic);raw=data.get('results',[]);records=[];rejected=0
    for row in raw:
        if not semantic and not any(a.get('author',{}).get('id')==state['author_id'] for a in row.get('authorships',[])):
            rejected+=1;continue
        if row.get('title') or row.get('display_name'):records.append(work_record(row))
    total=data.get('meta',{}).get('count',len(raw));position+=len(raw)
    next_state={'position':position,'total':total,'done':semantic or not raw or position>=min(total,10000),
                'source_limited':bool(semantic and total>=size or not semantic and total>10000 and position>=10000),
                'identity_rejected':state.get('identity_rejected',0)+rejected}
    if not semantic:next_state.update(page=params['page']+1,page_size=params['per_page'])
    return records[:size],next_state


def semantic_queries(scope,prompt=''):
    plan=normalize_plan(scope.get('retrieval'))
    return plan['semantic_queries'] or [str(scope.get('question_en') or scope.get('field_en') or scope.get('field_zh') or prompt)[:2000]]
