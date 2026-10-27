"""Bibliographic metadata and explicitly sourced journal metrics; no inferred IF."""
import csv
import datetime as dt
import io
import math
import re
import unicodedata
import urllib.parse
from .network import AppError,plain

def journal_key(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',plain(value))).strip().casefold()

def issns(values):
    if isinstance(values,str):values=re.split(r'[;,\s]+',values)
    result=[]
    for value in values or []:
        value=re.sub(r'[^0-9X]','',str(value).upper())
        if re.fullmatch(r'\d{7}[\dX]',value):
            value=value[:4]+'-'+value[4:]
            if value not in result:result.append(value)
    return result

def bibliography(record):
    raw=record.get('raw_metadata') or {}
    names=raw.get('container-title') or []
    journal=plain(record.get('journal') or (names[0] if names else ''))
    publication_type=record.get('publication_type') or raw.get('type','')
    venue_type=record.get('venue_type') or ('journal' if publication_type in ('journal-article','journal-issue') else 'proceedings' if publication_type=='proceedings-article' else 'book' if publication_type.startswith('book') else 'preprint' if record.get('arxiv_id') else 'unknown')
    authors=record.get('authors') or []
    raw_authors=raw.get('author') or []
    first=raw_authors[0] if raw_authors else {}
    author_sort=record.get('author_sort') or (first.get('family','')+' '+first.get('given','')).strip()
    if not author_sort and authors:
        parts=authors[0].split();author_sort=(parts[-1]+' '+' '.join(parts[:-1])) if len(parts)>1 else authors[0]
    return {'journal':journal,'journal_key':journal_key(journal),'issns':issns(record.get('issns') or raw.get('ISSN')),'venue_type':venue_type,'author_sort':author_sort.casefold()}

def validate_metric(row):
    journal=plain(row.get('journal','')).strip()[:500]
    source=plain(row.get('source','')).strip()[:500]
    url=str(row.get('source_url','')).strip()[:2000]
    try:
        year=int(row.get('year'));value=float(row.get('impact_factor'))
        if not 1997<=year<=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=10)).year or not math.isfinite(value) or value<0 or value>1000:raise ValueError()
    except (TypeError,ValueError,OverflowError):raise AppError('invalid_metric')
    if not journal or not source:raise AppError('metric_source_required')
    if url:
        parsed=urllib.parse.urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise AppError('invalid_url')
    return {'journal':journal,'journal_key':journal_key(journal),'issns':issns(row.get('issns',[])),'year':year,'impact_factor':value,'source':source,'source_url':url}

def parse_metrics_csv(text):
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    required={'journal','year','impact_factor','source'}
    if not required.issubset(set(reader.fieldnames or [])):raise AppError('metric_csv_columns')
    rows=list(reader)
    if not rows or len(rows)>2000:raise AppError('metric_import_size')
    return [validate_metric(row) for row in rows]

def attach_metric(item,metrics):
    item.update(impact_factor=None,if_year=None,if_source='',if_source_url='',if_status='missing')
    if item['kind']!='paper' or item.get('venue_type') in ('preprint','proceedings','book'):
        item['if_status']='not_applicable';return item
    exact=[m for m in metrics if (item.get('journal_key') and m['journal_key']==item['journal_key']) or set(item.get('issns',[]))&set(m['issns'])]
    if exact:
        chosen=max(exact,key=lambda m:(m['year'],m['id']))
        item.update(impact_factor=chosen['impact_factor'],if_year=chosen['year'],if_source=chosen['source'],if_source_url=chosen['source_url'],if_status=('reference' if chosen.get('verification')=='third_party' else 'web_sourced' if chosen.get('verification')=='ai_web' else 'automatic') if chosen.get('origin')=='automatic' else 'provided',if_evidence=chosen.get('evidence_quote',''))
    return item
