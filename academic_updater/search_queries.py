"""Compile the shared history search syntax for each source.

arXiv supports phrases, AND/OR and groups. Crossref bibliographic queries are
ranked text searches, so OR alternatives become separate, bounded searches.
"""
import itertools
import re
from .network import AppError

MAX_ALTERNATIVES=16


def parse_query(query):
    query=str(query).translate(str.maketrans({'“':'"','”':'"','（':'(','）':')'})).strip()
    if not query or len(query)>250:raise AppError('history_query_syntax')
    tokens=re.findall(r'"[^"\n]+"|[()]|[^\s()"]+|"',query)
    if len(tokens)>80:raise AppError('history_query_syntax')
    index=0

    def atom(depth):
        nonlocal index
        if depth>12 or index>=len(tokens):raise AppError('history_query_syntax')
        token=tokens[index];index+=1
        if token=='(':
            result=expression(depth+1)
            if index>=len(tokens) or tokens[index]!=')':raise AppError('history_query_syntax')
            index+=1;return result
        if token in ('AND','OR','NOT','ANDNOT',')','"') or ':' in token or '\\' in token:
            raise AppError('history_query_syntax')
        term=token[1:-1] if token.startswith('"') else token
        if not term.strip():raise AppError('history_query_syntax')
        return ('term',re.sub(r'\s+',' ',term.strip()))

    def conjunction(depth):
        nonlocal index
        nodes=[atom(depth)]
        while index<len(tokens) and tokens[index] not in (')','OR'):
            if tokens[index]=='AND':index+=1
            nodes.append(atom(depth))
        return nodes[0] if len(nodes)==1 else ('and',nodes)

    def expression(depth):
        nonlocal index
        nodes=[conjunction(depth)]
        while index<len(tokens) and tokens[index]=='OR':
            index+=1;nodes.append(conjunction(depth))
        return nodes[0] if len(nodes)==1 else ('or',nodes)

    result=expression(0)
    if index!=len(tokens):raise AppError('history_query_syntax')
    return result


def _alternatives(node):
    kind,value=node
    if kind=='term':return [(value,)]
    groups=[_alternatives(child) for child in value]
    if kind=='or':result=[terms for group in groups for terms in group]
    else:
        size=1
        for group in groups:size*=len(group)
        if size>MAX_ALTERNATIVES:raise AppError('history_query_too_broad')
        result=[tuple(itertools.chain.from_iterable(terms)) for terms in itertools.product(*groups)]
    result=list(dict.fromkeys(result))
    if len(result)>MAX_ALTERNATIVES:raise AppError('history_query_too_broad')
    return result


def crossref_queries(query):
    return list(dict.fromkeys(' '.join(terms) for terms in _alternatives(parse_query(query))))


def arxiv_query(query):
    def render(node):
        kind,value=node
        if kind=='term':return 'all:"'+value+'"'
        return '('+(' AND ' if kind=='and' else ' OR ').join(render(child) for child in value)+')'
    return render(parse_query(query))


def history_streams(config,queries):
    streams=[]
    for source in config['sources']:
        for original in queries:
            variants=crossref_queries(original) if source=='crossref' else [original]
            if source=='arxiv':arxiv_query(original)
            sorts=['is-referenced-by-count','score'] if source=='crossref' and config.get('discovery_mode')=='landmark' else ['score']
            choices=[(query,sort) for query in variants for sort in sorts]
            cap=config['limit']
            for index,(query,sort) in enumerate(choices):
                limit=cap//len(choices)+(index<cap%len(choices)) if cap else 0
                streams.append({'source':source,'query':query,'original_query':original,'sort':sort,'position':0,
                                'cursor':'*','done':False,'total':None,'limit':int(limit),'query_version':2})
    return streams


def upgrade_history_streams(config,queries,streams):
    """Replay legacy Boolean queries only when a saved search is explicitly run.

    A cursor belongs to its exact query. Retain ordinary-query checkpoints and
    archive replaced checkpoints; already saved papers/analyses deduplicate.
    """
    affected={(s['source'],s['query']) for s in streams if s.get('query_version',1)<2
              and re.search(r'["()]|\b(?:AND|OR)\b',s['query'])}
    if not affected:return streams,[]
    replacements=history_streams(config,queries);result=[];archived=[];inserted=set()
    for stream in streams:
        key=(stream['source'],stream['query'])
        if key not in affected:result.append(stream);continue
        matching=[s for s in replacements if (s['source'],s['original_query'])==key]
        if not matching:result.append(stream);continue
        archived.append(dict(stream))
        if key not in inserted:result.extend(matching);inserted.add(key)
    return result,archived
