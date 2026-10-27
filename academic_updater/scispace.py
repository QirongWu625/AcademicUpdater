"""Explicit SciSpace export ingestion, without assuming independent API access."""
import csv
import datetime as dt
import io
import json
import re
import urllib.parse
from .network import AppError,doi,plain

HOME='https://scispace.com/literature-review'
MAX_BYTES=180_000
MAX_ROWS=200


def research_question(scope,prompt='',historical=False):
    field=scope.get('field_en') or scope.get('field_zh') or prompt
    question=scope.get('question_en') or scope.get('question_zh') or ''
    if not field:return ''
    opening='Which original, influential or foundational studies directly address' if historical else 'Which recent research papers directly address'
    parts=[f'{opening} {field.strip().rstrip(".?")} ?']
    if question:parts.append('Focus on this research question: '+question)
    if prompt and prompt!=field:parts.append('Research intent: '+prompt[:2000])
    excluded=scope.get('excluded_en') or scope.get('excluded_zh') or []
    if excluded:parts.append('Exclude: '+'; '.join(excluded))
    parts.append('Match the specific problem and method, not just the broad discipline. Separate reviews and indirect background from directly relevant original studies.')
    return '\n'.join(parts)[:6000]


def _key(key):return re.sub(r'[^a-z0-9\u4e00-\u9fff]','',str(key).casefold())


def _ris(text):
    rows=[];current=None;previous=None
    for line in text.splitlines():
        match=re.match(r'^([A-Z0-9]{2})\s{2}-\s?(.*)$',line)
        if match:
            tag,value=match.groups()
            if tag=='TY':
                if current:raise AppError('scispace_invalid_file')
                current={};previous=None
            elif tag=='ER':
                if current is None:raise AppError('scispace_invalid_file')
                rows.append(current);current=None;previous=None
            elif current is not None:
                key={'TI':'title','T1':'title','AB':'abstract','N2':'abstract','JO':'journal','JF':'journal','T2':'journal','DO':'doi','UR':'url','PY':'year','Y1':'year','AU':'authors','A1':'authors','SN':'issn'}.get(tag)
                if key:
                    if key=='authors':current.setdefault(key,[]).append(value)
                    else:current[key]=value
                previous=key
        elif line.strip() and current is not None and previous and previous!='authors':current[previous]+=' '+line.strip()
    if current is not None:raise AppError('scispace_invalid_file')
    return rows


def _row(row):
    if not isinstance(row,dict):raise ValueError('record')
    normalized={_key(k):v for k,v in row.items()}
    def value(*keys,default=''):
        return next((normalized[_key(k)] for k in keys if normalized.get(_key(k)) not in (None,'')),default)
    title=plain(str(value('title','paper title','publication title','论文标题'))).strip()[:2000]
    if not title:raise ValueError('title')
    identifier=doi(str(value('doi')))
    slug=str(value('full_slug'));unique=str(value('unique_id'))
    supplied=str(value('url','link','paper url','paper link','publication url')).strip()
    scispace_url='https://scispace.com/papers/'+slug if re.fullmatch(r'[a-z0-9-]{3,500}',slug) else ''
    url=('https://doi.org/'+identifier) if identifier else supplied or scispace_url
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:raise ValueError('url')
    if parsed.scheme=='http':url='https://'+url[7:]
    if supplied and urllib.parse.urlsplit(supplied).hostname in ('scispace.com','www.scispace.com'):scispace_url=supplied
    authors=value('authors','author','作者',default=[])
    if isinstance(authors,dict):authors=authors.get('data',[])
    if isinstance(authors,str):authors=re.split(r'\s*(?:;|\||\band\b)\s*',authors)
    if not isinstance(authors,list):raise ValueError('authors')
    authors=[plain(str(a.get('display_name') or a.get('name') or '')) if isinstance(a,dict) else plain(str(a)) for a in authors[:100]]
    journal=value('journal','journal name','venue','publication venue','期刊')
    issn=value('issn','issns',default=[])
    if isinstance(journal,dict):issn=journal.get('issn') or issn;journal=journal.get('display_name') or journal.get('name') or ''
    date=str(value('date','published_at','publication date','year','publication year')).strip()
    date_match=re.match(r'^(\d{4})(?:[-/](\d{1,2})(?:[-/](\d{1,2}))?)?',date)
    published='-'.join(part.zfill(2) for part in date_match.groups() if part) if date_match else None
    if date_match:
        try:dt.date(int(date_match[1]),int(date_match[2] or 1),int(date_match[3] or 1))
        except ValueError:published=None
    abstract=plain(str(value('abstract','摘要')))[:30000]
    kind=str(value('publication_type','type')).casefold()
    preprint='preprint' in kind or identifier.startswith(('10.1101/','10.21203/'))
    venue='preprint' if preprint else 'proceedings' if 'conference' in kind else 'book' if 'book' in kind else 'journal' if journal else 'unknown'
    count=value('citation count','citations','cited by',default=None)
    if isinstance(row.get('metrics'),dict):
        citations=row['metrics'].get('citations')
        if isinstance(citations,dict):count=citations.get('total')
    if isinstance(count,str) and re.fullmatch(r'\d[\d,]*',count):count=int(count.replace(',',''))
    if isinstance(count,bool) or not isinstance(count,int) or count<0:count=None
    metadata={'provider':'SciSpace','scispace_url':scispace_url,'scispace_citations':count,'metadata_status':'reported_by_import'}
    return {'kind':'paper','title':title,'abstract':abstract,'doi':identifier,'url':url,'external_id':unique or identifier or url,
            'authors':[a for a in authors if a],'published_at':published,'version':'','journal':plain(str(journal)),
            'issns':issn,'venue_type':venue,'raw_metadata':metadata}


def parse_export(text,format='auto'):
    if not isinstance(text,str) or len(text.encode('utf-8'))>MAX_BYTES:raise AppError('scispace_file_size')
    text=text.lstrip('\ufeff').strip()
    if format=='auto':format='json' if text.startswith(('[','{')) else 'ris' if re.match(r'^TY\s{2}-',text) else 'csv'
    if format not in ('json','ris','csv'):raise AppError('scispace_invalid_file')
    question=''
    try:
        if format=='json':
            payload=json.loads(text)
            if isinstance(payload,dict):question=str(payload.get('searchTerm') or payload.get('question') or '')[:6000];rows=payload.get('papers') or payload.get('results') or []
            else:rows=payload
        elif format=='ris':rows=_ris(text)
        else:
            dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t')
            rows=list(csv.DictReader(io.StringIO(text),dialect=dialect))
    except (ValueError,TypeError,csv.Error):raise AppError('scispace_invalid_file')
    if not isinstance(rows,list) or not rows or len(rows)>MAX_ROWS:raise AppError('scispace_file_size')
    records=[];warnings=[]
    for index,row in enumerate(rows,1):
        try:records.append(_row(row))
        except (ValueError,TypeError,AttributeError):warnings.append(index)
    if not records:raise AppError('scispace_no_records')
    return {'records':records,'skipped_rows':warnings,'question':question,'format':format}
