"""Identifier-matched abstract recovery, with durable provenance and retry state."""
import datetime as dt
import hashlib
import json
import re
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from .network import AppError, get_json, request, plain, doi, TextParser
from .discovery import abstract_text
from .sources import arxiv_records, arxiv_request
from .storage import now, encode


def usable(text):
    text=plain(text)
    if len(text)<100 or len(text)>30000:return ''
    if re.search(r'^(access denied|just a moment|enable javascript|abstract unavailable|no abstract)',text,re.I):return ''
    return text


class Abstracts:
    def __init__(self,service):
        self.service=service;self.store=service.store
        self.guard=threading.Lock();self.locks={};self.lookup_slots=threading.BoundedSemaphore(3)

    def pending(self):
        with self.store.db() as c:
            return [r[0] for r in c.execute("""SELECT i.id FROM items i LEFT JOIN abstract_lookups a ON a.item_id=i.id
                WHERE i.kind='paper' AND i.deleted_at IS NULL AND trim(i.abstract)=''
                AND (a.item_id IS NULL OR a.version_id<>i.current_version OR a.status IN ('pending','running')
                     OR (a.retry_at IS NOT NULL AND a.retry_at<=?))
                ORDER BY i.history_only,i.saved DESC,i.id DESC""",(now(),))]

    def status(self):
        with self.store.db() as c:
            counts={r[0]:r[1] for r in c.execute("SELECT a.status,count(*) FROM abstract_lookups a JOIN items i ON i.id=a.item_id WHERE i.deleted_at IS NULL GROUP BY a.status")}
            counts['missing']=c.execute("SELECT count(*) FROM items WHERE deleted_at IS NULL AND kind='paper' AND trim(abstract)=''").fetchone()[0]
        counts['pending']=len(self.pending())
        return counts

    def lookup(self,item,check):
        identifiers=item['identifiers'];identifier=next((x[4:] for x in identifiers if x.startswith('doi:')),'')
        arxiv=next((x[6:] for x in identifiers if x.startswith('arxiv:')),'')
        attempts=[]
        def attempt(source,url,fetch):
            check()
            try:
                text=usable(fetch())
                attempts.append({'source':source,'url':url,'status':'found' if text else 'unavailable'})
                if text:return {'source':source,'url':url,'abstract':text,'retrieved_at':now(),'matched_doi':identifier,'attempts':attempts}
            except AppError as exc:
                status='unavailable' if 'HTTP 404' in exc.detail else 'error'
                attempts.append({'source':source,'url':url,'status':status,'error':exc.code,'detail':exc.detail})
            except (TypeError,ValueError,KeyError,AttributeError):
                attempts.append({'source':source,'url':url,'status':'error','error':'invalid_source_metadata'})
            return None
        if identifier:
            url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':'DOI:"'+identifier.replace('"','')+'"','format':'json','resultType':'core','pageSize':5})
            def europe():
                rows=get_json(url,timeout=18).get('resultList',{}).get('result',[]) or []
                return next((r.get('abstractText','') for r in rows if isinstance(r,dict) and doi(r.get('doi'))==identifier and usable(r.get('abstractText',''))),'')
            found=attempt('Europe PMC',url,europe)
            if found:return found,attempts
            url='https://api.openalex.org/works/https://doi.org/'+urllib.parse.quote(identifier,safe='')
            def openalex():
                row=get_json(url,timeout=18)
                return abstract_text(row.get('abstract_inverted_index')) if doi(row.get('doi'))==identifier else ''
            found=attempt('OpenAlex',url,openalex)
            if found:return found,attempts
        else:
            work_id=next((r.get('external_id','') for r in item.get('sources',[]) if re.fullmatch(r'(?:https://openalex.org/)?W\d+',r.get('external_id',''))),'')
            if work_id:
                work_id=work_id.rsplit('/',1)[-1];url='https://api.openalex.org/works/'+work_id
                def openalex_id():
                    row=get_json(url,timeout=18)
                    return abstract_text(row.get('abstract_inverted_index')) if row.get('id')=='https://openalex.org/'+work_id else ''
                found=attempt('OpenAlex',url,openalex_id)
                if found:return found,attempts
        if arxiv:
            url='https://export.arxiv.org/api/query?'+urllib.parse.urlencode({'id_list':arxiv})
            def arxiv_abstract():
                records,_=arxiv_records(arxiv_request(url))
                return next((r['abstract'] for r in records if r.get('arxiv_id')==arxiv),'')
            found=attempt('arXiv',url,arxiv_abstract)
            if found:return found,attempts
        # Explicit abstract metadata only; generic page descriptions are not abstracts.
        url='https://doi.org/'+urllib.parse.quote(identifier,safe='/') if identifier else item['url']
        def publisher():
            parser=TextParser();parser.feed(request(url,timeout=18,limit=2_000_000).decode('utf-8',errors='replace'))
            if identifier:
                if doi(parser.meta.get('citation_doi') or parser.meta.get('dc.identifier'))!=identifier:return ''
            else:
                normalize=lambda value:re.sub(r'\W+','',plain(value).casefold())
                if normalize(parser.meta.get('citation_title',''))!=normalize(item['title']):return ''
            return parser.meta.get('citation_abstract') or parser.meta.get('dc.description') or ''
        found=attempt('Publisher',url,publisher)
        return found,attempts

    def apply(self,item,evidence):
        """Add a source snapshot without replacing original source records or feedback."""
        stamp=now();content={'title':item['title'],'abstract':evidence['abstract'],'authors':item['authors'],'label':'Retrieved abstract'}
        fingerprint=hashlib.sha256(encode(content).encode()).hexdigest()
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            current=c.execute('SELECT * FROM items WHERE id=?',(item['id'],)).fetchone()
            if not current or current['deleted_at'] or current['abstract'].strip() or current['current_version']!=item['current_version']:return False
            record={'title':item['title'],'abstract':evidence['abstract'],'retrieval':evidence}
            external=str(item['id'])+':'+str(item['current_version'])
            record_id=c.execute('INSERT INTO source_records(item_id,source_id,external_id,url,content_hash,raw_json,last_seen) VALUES(?,-1,?,?,?,?,?)',(item['id'],external,evidence['url'],fingerprint,encode(record),stamp)).lastrowid
            version=c.execute('INSERT INTO versions(item_id,record_id,label,content_hash,title,abstract,observed_at) VALUES(?,?,?,?,?,?,?)',(item['id'],record_id,'Abstract · '+evidence['source'],fingerprint,item['title'],evidence['abstract'],stamp)).lastrowid
            c.execute("UPDATE items SET abstract=?,primary_record=?,current_version=?,updated_at=?,notice='updated' WHERE id=?",(evidence['abstract'],record_id,version,stamp,item['id']))
            # History uses frozen snapshots. Refresh only missing abstracts; preserve
            # author identity, citation evidence and each history's independent scope.
            for row in c.execute('SELECT * FROM history_items WHERE item_id=?',(item['id'],)).fetchall():
                snapshot=json.loads(row['snapshot'])
                if str(snapshot.get('abstract') or '').strip():continue
                snapshot.update(abstract=evidence['abstract'],abstract_source=evidence,abstract_refresh=True,current_version=version)
                c.execute("UPDATE history_items SET snapshot=?,version_id=?,status='pending',result='{}' WHERE history_id=? AND item_id=?",(encode(snapshot),version,row['history_id'],item['id']))
                c.execute("UPDATE histories SET report='{}',updated_at=? WHERE id=?",(stamp,row['history_id']))
            c.execute("UPDATE abstract_lookups SET status='found',evidence=?,updated_at=?,retry_at=NULL WHERE item_id=?",(encode(evidence),stamp,item['id']))
        return True

    def enrich(self,item_id,job):
        with self.guard:lock=self.locks.setdefault(item_id,threading.Lock())
        check=lambda:self.service._check_pause(job)
        while not lock.acquire(timeout=.2):check()
        try:
            check();item=self.store.item(item_id,include_deleted=True)
            if item['deleted_at'] or item['kind']!='paper' or item['abstract'].strip():return False
            with self.store.db() as c:
                row=c.execute('SELECT * FROM abstract_lookups WHERE item_id=?',(item_id,)).fetchone()
                if row and row['version_id']==item['current_version'] and row['status'] not in ('pending','running') and (not row['retry_at'] or row['retry_at']>now()):return False
                c.execute("INSERT INTO abstract_lookups(item_id,version_id,status,updated_at) VALUES(?,?,'running',?) ON CONFLICT(item_id) DO UPDATE SET version_id=excluded.version_id,status='running',updated_at=excluded.updated_at",(item_id,item['current_version'],now()))
            try:
                while not self.lookup_slots.acquire(timeout=.2):check()
                try:evidence,attempts=self.lookup(item,check)
                finally:self.lookup_slots.release()
                check()
                if evidence and self.apply(item,evidence):return True
                error=any(a['status']=='error' for a in attempts)
                retry=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=6) if error else dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=30)).isoformat(timespec='seconds')
                with self.store.db() as c:c.execute('UPDATE abstract_lookups SET status=?,evidence=?,updated_at=?,retry_at=? WHERE item_id=?',('error' if error else 'unavailable',encode({'attempts':attempts}),now(),retry,item_id))
                return False
            except BaseException:
                with self.store.db() as c:c.execute("UPDATE abstract_lookups SET status='pending',updated_at=? WHERE item_id=? AND status='running'",(now(),item_id))
                raise
        finally:lock.release()

    def history_pending(self):
        with self.store.db() as c:return [r[0] for r in c.execute("""SELECT DISTINCT h.id FROM history_items x JOIN histories h ON h.id=x.history_id JOIN items i ON i.id=x.item_id
            WHERE h.deleted_at IS NULL AND i.deleted_at IS NULL AND json_extract(h.config,'$.analyze')=1
            AND (x.status='pending' OR h.report='{}') AND json_extract(x.snapshot,'$.abstract_refresh')=1
            AND NOT EXISTS(SELECT 1 FROM runs r WHERE r.id=(SELECT max(r2.id) FROM runs r2 WHERE r2.kind='history_search' AND json_extract(r2.argument,'$.input')=h.id) AND r.status='paused')""")]

    def assessment_pending(self,profile):
        if not profile:return False
        with self.store.db() as c:return bool(c.execute("SELECT 1 FROM abstract_lookups x JOIN items i ON i.id=x.item_id WHERE x.status='found' AND i.deleted_at IS NULL AND i.ignored=0 AND i.history_only=0 AND NOT EXISTS(SELECT 1 FROM analyses a WHERE a.item_id=i.id AND a.version_id=i.current_version AND a.profile_version=?) LIMIT 1",(profile['version'],)).fetchone())

    def reassess_histories(self,job,settings):
        for hid in self.history_pending():
            with self.service.guard:
                if any(w['group']==('history',hid) for w in self.service.workers.values()):continue
                # Reserve the history group while updating its assessment and report.
                self.service.abstract_history_claims.add(('history',hid))
            try:
                h=self.service.history.get(hid)
                batch=[i for i in h['items'] if i.get('abstract_refresh') and i['history_status']=='pending']
                def assess(entries):
                    self.service._check_pause(job)
                    self.service.ai_call(job,lambda effective:self.service.history.analyze_batch(hid,{**h['scope'],'original_prompt':h['prompt']},entries,effective),settings)
                self.service.parallel_work(job,(batch[start:start+10] for start in range(0,len(batch),10)),assess)
                self.service.ai_call(job,lambda effective:self.service.history.synthesize(self.service.history.get(hid),effective),settings)
            finally:
                with self.service.guard:self.service.abstract_history_claims.discard(('history',hid))

    def run(self,job,payload):
        self.service._checkpoint(job,phase='abstract_retrieval')
        ids=self.pending();completed=0;found=0;guard=threading.Lock()
        def work(item_id):
            nonlocal completed,found
            changed=self.enrich(item_id,job)
            with guard:
                completed+=1;found+=int(changed)
                self.service._checkpoint(job,abstract_processed=completed,abstract_total=len(ids),abstract_found=found)
        # Keep public metadata traffic modest, independently of AI parallelism.
        with ThreadPoolExecutor(max_workers=3,thread_name_prefix='abstract') as pool:
            list(pool.map(work,ids))
        if payload['profile']:analysis=self.service._analyze_queue(job,payload)
        else:analysis={}
        self.service._checkpoint(job,phase='abstract_history')
        self.reassess_histories(job,payload['settings'])
        return {'processed':completed,'found':found,'analysis':analysis,'abstracts':self.status()}
