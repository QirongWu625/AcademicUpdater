from __future__ import annotations
import datetime as dt
import email.utils
import re
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from .network import AppError, request, get_json, plain, doi, arxiv_id, TextParser
from .search_queries import arxiv_query,crossref_queries
from .discovery import discovery_page,semantic_queries

_arxiv_lock=threading.Lock()
_arxiv_last=0.0
ATOM={'a':'http://www.w3.org/2005/Atom','ar':'http://arxiv.org/schemas/atom','os':'http://a9.com/-/spec/opensearch/1.1/'}


def arxiv_request(url):
    global _arxiv_last
    with _arxiv_lock:
        time.sleep(max(0,3-(time.monotonic()-_arxiv_last)))
        try:return request(url,timeout=60)
        finally:_arxiv_last=time.monotonic()


def crossref_record(r):
    date=r.get('published',{}).get('date-parts',[[]])[0]
    published='-'.join(f'{v:04d}' if i==0 else f'{v:02d}' for i,v in enumerate(date)) or None
    identifier=doi(r.get('DOI'))
    return {'kind':'paper','title':plain((r.get('title') or [''])[0]),'abstract':plain(r.get('abstract','')),'doi':identifier,'url':r.get('URL') or 'https://doi.org/'+identifier,'external_id':identifier,'authors':[(' '.join([a.get('given',''),a.get('family','')]).strip() or a.get('name','')) for a in r.get('author',[])],'published_at':published,'source_updated':r.get('indexed',{}).get('date-time'),'version':'','raw_metadata':r}


def parse_xml(body):
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():raise AppError('unsafe_xml')
    try:return ET.fromstring(body)
    except ET.ParseError as exc:raise AppError('invalid_feed',status=502) from exc


def arxiv_records(body):
    root=parse_xml(body);records=[]
    if root.tag!='{http://www.w3.org/2005/Atom}feed':raise AppError('invalid_feed',status=502)
    for e in root.findall('a:entry',ATOM):
        url=e.findtext('a:id','',ATOM).replace('http://','https://')
        if '/api/errors' in url:raise AppError('source_query_error',status=502)
        if not arxiv_id(url):continue
        version=re.search(r'v(\d+)$',url)
        records.append({'kind':'paper','title':plain(e.findtext('a:title','',ATOM)),'abstract':plain(e.findtext('a:summary','',ATOM)),'url':url,'arxiv_id':arxiv_id(url),'doi':e.findtext('ar:doi','',ATOM),'external_id':arxiv_id(url),'version':'v'+version[1] if version else 'v1','authors':[a.findtext('a:name','',ATOM) for a in e.findall('a:author',ATOM)],'published_at':e.findtext('a:published','',ATOM),'source_updated':e.findtext('a:updated','',ATOM)})
    return records,int(root.findtext('os:totalResults','0',ATOM))


def iso_date(value):
    if not value:return None
    try:return email.utils.parsedate_to_datetime(value).astimezone(dt.timezone.utc).isoformat()
    except (ValueError,TypeError):return str(value)[:40]


def feed_records(body,kind,base):
    root=parse_xml(body);entries=root.findall('./channel/item');atom=False
    if root.tag not in ('rss','{http://www.w3.org/2005/Atom}feed'):raise AppError('invalid_feed',status=502)
    if not entries:entries=root.findall('a:entry',ATOM);atom=True
    records=[]
    for e in entries[:500]:
        if atom:
            title=e.findtext('a:title','',ATOM);description=e.findtext('a:summary','',ATOM) or e.findtext('a:content','',ATOM)
            links=e.findall('a:link',ATOM);url=next((x.get('href') for x in links if x.get('rel','alternate')=='alternate'),'')
            guid=e.findtext('a:id','',ATOM);published=e.findtext('a:published','',ATOM) or e.findtext('a:updated','',ATOM)
            authors=[a.findtext('a:name','',ATOM) for a in e.findall('a:author',ATOM)]
        else:
            title=e.findtext('title','');description=e.findtext('description','') or e.findtext('{http://purl.org/rss/1.0/modules/content/}encoded','')
            url=e.findtext('link','');guid=e.findtext('guid','');published=e.findtext('pubDate','');authors=[e.findtext('author','')]
        if not title or not url:continue
        url=urllib.parse.urljoin(base,url)
        if urllib.parse.urlsplit(url).scheme not in ('http','https'):continue
        # Store public source URLs as HTTPS; never execute HTML from feeds.
        url=url.replace('http://','https://',1)
        records.append({'kind':kind,'title':plain(title),'abstract':plain(description),'url':url,'external_id':guid or url,'authors':[x for x in authors if x],'published_at':iso_date(published),'source_updated':iso_date(published),'version':''})
    return records


def collect(source,active,settings):
    global _arxiv_last
    terms=active['understanding'].get('queries') or active['understanding'].get('keywords_en') or active['understanding'].get('keywords_zh')
    queries=[source['query']] if source.get('query') else (terms or [])[:3]
    query=queries[0] if queries else ''
    if source['kind'] in ('crossref','arxiv') and not query.strip():raise AppError('missing_search_terms')
    limit=settings['max_per_source'];days=settings['lookback_days']
    until=dt.datetime.now(dt.timezone.utc)
    since=until-dt.timedelta(days=days)
    # A successful checkpoint expands catch-up after missed days; overlap handles indexing delay.
    if source.get('last_success'):
        try:since=min(since,dt.datetime.fromisoformat(source['last_success'])-dt.timedelta(days=2))
        except ValueError:pass
    if source['kind']=='openalex':
        rows=[];seen=set();limited=False
        queries=[source['query']] if source.get('query') else semantic_queries(active['understanding'],active.get('prompt',''))
        for index,q in enumerate(queries):
            cap=min(50,limit//len(queries)+int(index<limit%len(queries)))
            if not cap:limited=True;continue
            found,state=discovery_page(q,{}, {'mode':'semantic','since':str(since.date()),'until':str(until.date())},cap)
            limited=limited or state['source_limited']
            for row in found:
                key=row['doi'] or row['external_id']
                if key not in seen:rows.append(row);seen.add(key)
        return rows,limited
    if source['kind']=='crossref':
        variants=list(dict.fromkeys(v for q in queries for v in crossref_queries(q)))
        rows=[];seen=set();limited=len(variants)>limit
        for index,variant in enumerate(variants):
            size=limit//len(variants)+int(index<limit%len(variants))
            if not size:continue
            params={'query.bibliographic':variant,'filter':f'from-index-date:{since.date()},until-index-date:{until.date()}','sort':'score','order':'desc','rows':size}
            result=get_json('https://api.crossref.org/works?'+urllib.parse.urlencode(params))['message']
            limited=limited or result.get('total-results',0)>size
            for r in result.get('items',[])[:size]:
                record=crossref_record(r);key=record['doi'] or record['url']
                if key not in seen:rows.append(record);seen.add(key)
        return rows,limited
    if source['kind']=='arxiv':
        # Preserve complete concept intersections; explicit native arXiv overrides stay intact.
        if not source.get('query'):
            query=' OR '.join('('+arxiv_query(q)+')' for q in queries)
        query=f'({query}) AND lastUpdatedDate:[{since:%Y%m%d}0000 TO {until:%Y%m%d}2359]'
        params={'search_query':query,'sortBy':'lastUpdatedDate','sortOrder':'descending','start':0,'max_results':limit}
        body=arxiv_request('https://export.arxiv.org/api/query?'+urllib.parse.urlencode(params))
        rows,total=arxiv_records(body)
        return rows,total>limit
    rows=feed_records(request(source['url']),source['kind'],source['url'])
    return rows[:limit],len(rows)>limit


def import_link(value,kind='paper'):
    identifier=doi(value)
    if identifier:
        return crossref_record(get_json('https://api.crossref.org/works/'+urllib.parse.quote(identifier,safe=''))['message'])
    if (a:=arxiv_id(value)):
        rows,_=arxiv_records(arxiv_request('https://export.arxiv.org/api/query?'+urllib.parse.urlencode({'id_list':a})))
        if not rows:raise AppError('not_found',status=404)
        return rows[0]
    body=request(value,limit=2_000_000)
    if body.startswith(b'%PDF'):raise AppError('pdf_metadata_required','Import the publication page or DOI instead of a PDF URL.')
    parser=TextParser();parser.feed(body.decode('utf-8',errors='replace'))
    title=parser.meta.get('citation_title') or parser.meta.get('og:title') or ''.join(parser.title)
    if not title:raise AppError('missing_title','This page has no usable title. Use a DOI or publication page.')
    abstract=parser.meta.get('citation_abstract') or parser.meta.get('description') or parser.meta.get('og:description') or ''
    return {'kind':kind,'title':plain(title),'abstract':plain(abstract),'url':value,'external_id':value,'doi':parser.meta.get('citation_doi',''),'journal':plain(parser.meta.get('citation_journal_title','')),'venue_type':'journal' if parser.meta.get('citation_journal_title') else 'unknown','issns':parser.meta_values.get('citation_issn',[]),'authors':[plain(a) for a in parser.meta_values.get('citation_author',[])],'published_at':parser.meta.get('citation_publication_date') or parser.meta.get('article:published_time'),'version':''}
