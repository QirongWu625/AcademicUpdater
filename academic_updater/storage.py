from __future__ import annotations
import contextlib
import datetime as dt
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from .network import AppError, canonical_url, doi, arxiv_id
from .metadata import bibliography,attach_metric,validate_metric


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


DEFAULT_SETTINGS = {'language': 'en', 'summary_language': 'auto', 'provider': 'subscription', 'model': '', 'reasoning_effort':'default', 'local_url': 'http://127.0.0.1:11434/v1', 'daily_ai_limit': 30, 'daily_digest_limit': 10, 'schedule_enabled': True, 'schedule_time': '08:00', 'utc_offset': 10, 'lookback_days': 14, 'max_per_source': 100}
EMPTY_PROFILE = {'topic': '', 'prompt': '', 'exclude': '', 'revision': 0, 'understanding': None, 'understanding_revision': None, 'origin': None, 'active': None}


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'academicupdater.sqlite3'
        with self.db() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,url TEXT NOT NULL DEFAULT '',enabled INTEGER NOT NULL DEFAULT 1,query TEXT NOT NULL DEFAULT '',last_success TEXT,last_status TEXT,last_error TEXT);
            CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,title TEXT NOT NULL,abstract TEXT NOT NULL DEFAULT '',url TEXT NOT NULL,authors TEXT NOT NULL DEFAULT '[]',published_at TEXT,first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,updated_at TEXT NOT NULL,saved INTEGER NOT NULL DEFAULT 0,is_read INTEGER NOT NULL DEFAULT 0,ignored INTEGER NOT NULL DEFAULT 0,notes TEXT NOT NULL DEFAULT '',primary_record INTEGER,current_version INTEGER,notice TEXT NOT NULL DEFAULT 'new');
            CREATE TABLE IF NOT EXISTS identifiers(key TEXT PRIMARY KEY,item_id INTEGER NOT NULL REFERENCES items(id));
            CREATE TABLE IF NOT EXISTS source_records(id INTEGER PRIMARY KEY,item_id INTEGER NOT NULL REFERENCES items(id),source_id INTEGER NOT NULL,external_id TEXT NOT NULL,url TEXT NOT NULL,content_hash TEXT NOT NULL,raw_json TEXT NOT NULL,last_seen TEXT NOT NULL,UNIQUE(source_id,external_id));
            CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY,item_id INTEGER NOT NULL REFERENCES items(id),record_id INTEGER NOT NULL REFERENCES source_records(id),label TEXT NOT NULL,content_hash TEXT NOT NULL,title TEXT NOT NULL,abstract TEXT NOT NULL,observed_at TEXT NOT NULL,UNIQUE(record_id,content_hash));
            CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY,item_id INTEGER NOT NULL REFERENCES items(id),version_id INTEGER NOT NULL,profile_version INTEGER NOT NULL,provider TEXT NOT NULL,model TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(item_id,version_id,profile_version,provider,model));
            CREATE TABLE IF NOT EXISTS ai_usage(id INTEGER PRIMARY KEY,day TEXT NOT NULL,task TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,status TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT,result TEXT NOT NULL DEFAULT '{}',error TEXT);
            CREATE TABLE IF NOT EXISTS digests(day TEXT PRIMARY KEY,item_ids TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS delivered(item_id INTEGER NOT NULL,version_id INTEGER NOT NULL,PRIMARY KEY(item_id,version_id));
            CREATE INDEX IF NOT EXISTS items_updated ON items(updated_at DESC);
            CREATE INDEX IF NOT EXISTS analyses_item ON analyses(item_id,profile_version);
            CREATE TABLE IF NOT EXISTS journal_metrics(id INTEGER PRIMARY KEY,journal TEXT NOT NULL,journal_key TEXT NOT NULL,issns TEXT NOT NULL DEFAULT '[]',year INTEGER NOT NULL,impact_factor REAL NOT NULL,source TEXT NOT NULL,source_url TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL,UNIQUE(journal_key,year));
            CREATE TABLE IF NOT EXISTS analysis_tasks(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL REFERENCES runs(id),item_id INTEGER NOT NULL REFERENCES items(id),version_id INTEGER NOT NULL,profile_version INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,error TEXT,updated_at TEXT NOT NULL,UNIQUE(run_id,item_id));
            ''')
            c.executescript("""
            CREATE TABLE IF NOT EXISTS histories(id INTEGER PRIMARY KEY,prompt TEXT NOT NULL,scope TEXT NOT NULL DEFAULT '{}',config TEXT NOT NULL DEFAULT '{}',progress TEXT NOT NULL DEFAULT '{}',report TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'draft',error TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history_items(history_id INTEGER NOT NULL REFERENCES histories(id),item_id INTEGER NOT NULL REFERENCES items(id),version_id INTEGER NOT NULL,snapshot TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',result TEXT NOT NULL DEFAULT '{}',PRIMARY KEY(history_id,item_id));
            CREATE INDEX IF NOT EXISTS history_items_status ON history_items(history_id,status);
            """)
            self._migrate(c)
            c.execute("UPDATE histories SET status='interrupted' WHERE status IN ('planning','searching','analyzing','summarizing')")
            c.execute("INSERT OR IGNORE INTO kv VALUES('settings',?)", (encode(DEFAULT_SETTINGS),))
            c.execute("INSERT OR IGNORE INTO kv VALUES('profile',?)", (encode(EMPTY_PROFILE),))
            if not c.execute('SELECT 1 FROM sources LIMIT 1').fetchone():
                c.executemany('INSERT INTO sources(kind,name,url) VALUES(?,?,?)', [('crossref','Crossref','https://api.crossref.org/works'),('arxiv','arXiv','https://export.arxiv.org/api/query')])
            # A terminated process must never leave a job looking active forever.
            c.execute("UPDATE runs SET status='interrupted',finished_at=?,error='Application stopped before this run completed.' WHERE status='running'", (now(),))
            c.execute("UPDATE analysis_tasks SET status='pending',error='interrupted',updated_at=? WHERE status='running'",(now(),))
            c.execute("UPDATE ai_usage SET status='interrupted' WHERE status='started'")

    def _migrate(self,c):
        for table in ('items','histories'):
            if 'deleted_at' not in {r['name'] for r in c.execute(f'PRAGMA table_info({table})')}:
                c.execute(f'ALTER TABLE {table} ADD COLUMN deleted_at TEXT')
        columns={r['name'] for r in c.execute('PRAGMA table_info(items)')}
        if 'history_only' not in columns:c.execute('ALTER TABLE items ADD COLUMN history_only INTEGER NOT NULL DEFAULT 0')
        for name,definition in [('journal',"TEXT NOT NULL DEFAULT ''"),('journal_key',"TEXT NOT NULL DEFAULT ''"),('issns',"TEXT NOT NULL DEFAULT '[]'"),('venue_type',"TEXT NOT NULL DEFAULT 'unknown'"),('author_sort',"TEXT NOT NULL DEFAULT ''")]:
            if name not in columns:c.execute(f'ALTER TABLE items ADD COLUMN {name} {definition}')
        if 'reasoning_effort' not in {r['name'] for r in c.execute('PRAGMA table_info(analyses)')}:
            c.execute('ALTER TABLE analyses RENAME TO analyses_v1')
            c.execute("CREATE TABLE analyses(id INTEGER PRIMARY KEY,item_id INTEGER NOT NULL REFERENCES items(id),version_id INTEGER NOT NULL,profile_version INTEGER NOT NULL,provider TEXT NOT NULL,model TEXT NOT NULL,reasoning_effort TEXT NOT NULL DEFAULT 'default',result TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(item_id,version_id,profile_version,provider,model,reasoning_effort))")
            c.execute("INSERT INTO analyses(id,item_id,version_id,profile_version,provider,model,result,created_at) SELECT id,item_id,version_id,profile_version,provider,model,result,created_at FROM analyses_v1")
            c.execute('DROP TABLE analyses_v1')
            c.execute('CREATE INDEX IF NOT EXISTS analyses_item ON analyses(item_id,profile_version)')
        run_columns={r['name'] for r in c.execute('PRAGMA table_info(runs)')}
        for name in ('argument','progress'):
            if name not in run_columns:c.execute(f"ALTER TABLE runs ADD COLUMN {name} TEXT NOT NULL DEFAULT '{{}}'")
        marker=c.execute("SELECT value FROM kv WHERE key='bibliography_migrated'").fetchone()
        if not marker:
            # Restore metadata from stored source evidence without reimporting papers or AI work.
            for item in c.execute('SELECT * FROM items').fetchall():
                merged=bibliography({'authors':json.loads(item['authors'])})
                records=c.execute('SELECT raw_json FROM source_records WHERE item_id=? ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END,id',(item['id'],item['primary_record'])).fetchall()
                for row in records:
                    candidate=bibliography(json.loads(row['raw_json']))
                    if candidate['journal'] and (not merged['journal'] or candidate['venue_type']=='journal' and merged['venue_type']!='journal'):
                        merged.update({k:v for k,v in candidate.items() if v})
                    for key,value in candidate.items():
                        if value and value!='unknown' and (not merged.get(key) or merged[key]=='unknown' or (key=='author_sort' and not merged.get('journal'))):merged[key]=value
                c.execute('UPDATE items SET journal=?,journal_key=?,issns=?,venue_type=?,author_sort=? WHERE id=?',(merged['journal'],merged['journal_key'],encode(merged['issns']),merged['venue_type'],merged['author_sort'],item['id']))
            c.execute("INSERT INTO kv VALUES('bibliography_migrated','true')")

    @contextlib.contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def get(self, key, default=None):
        with self.db() as c:
            row = c.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.db() as c:
            c.execute('INSERT INTO kv VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, encode(value)))

    def settings(self):
        return {**DEFAULT_SETTINGS, **self.get('settings', {})}

    def save_profile(self, draft):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            p = json.loads(c.execute("SELECT value FROM kv WHERE key='profile'").fetchone()[0])
            if draft.get('revision') != p['revision']:
                raise AppError('stale_profile', status=409)
            raw = {k: str(draft.get(k, p[k])).strip()[:limit] for k, limit in [('topic',200),('prompt',12000),('exclude',2000)]}
            if any(raw[k] != p[k] for k in raw):
                p.update(raw)
                p['revision'] += 1
            c.execute("UPDATE kv SET value=? WHERE key='profile'", (encode(p),))
            return p

    def set_understanding(self, revision, result, origin):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            p = json.loads(c.execute("SELECT value FROM kv WHERE key='profile'").fetchone()[0])
            if p['revision'] != revision:
                raise AppError('stale_profile', status=409)
            p.update(understanding=result, understanding_revision=revision, origin=origin)
            c.execute("UPDATE kv SET value=? WHERE key='profile'", (encode(p),))
            return p

    def apply_profile(self, revision, understanding, origin='manual'):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            p = json.loads(c.execute("SELECT value FROM kv WHERE key='profile'").fetchone()[0])
            if p['revision'] != revision or not p['prompt'].strip():
                raise AppError('stale_profile', status=409)
            if p['active'] and p['active']['revision']==revision and p['active']['understanding']==understanding:
                return p
            version = (p['active'] or {}).get('version',0) + 1
            p.update(understanding=understanding,understanding_revision=revision,origin=origin)
            p['active'] = {'version':version,'revision':revision,'topic':p['topic'],'prompt':p['prompt'],'exclude':p['exclude'],'understanding':understanding,'applied_at':now(),'origin':origin}
            c.execute("UPDATE kv SET value=? WHERE key='profile'", (encode(p),))
            return p

    def sources(self):
        with self.db() as c:
            return [dict(r) for r in c.execute('SELECT * FROM sources ORDER BY id')]

    def source_status(self, source_id, status, detail=''):
        with self.db() as c:
            c.execute('UPDATE sources SET last_status=?,last_error=?,last_success=CASE WHEN ?=\'ok\' THEN ? ELSE last_success END WHERE id=?', (status,detail,status,now(),source_id))

    def ingest(self, source_id, record, historical=False):
        title = str(record.get('title','')).strip()[:2000]
        if not title:
            raise AppError('missing_title')
        url = canonical_url(record['url'])
        abstract = str(record.get('abstract',''))[:30000]
        authors = record.get('authors',[])[:100]
        stamp = now()
        keys = ['url:'+url]
        if (d := doi(record.get('doi'))): keys.append('doi:'+d)
        if (a := arxiv_id(record.get('arxiv_id'))): keys.append('arxiv:'+a)
        content = {'title':title,'abstract':abstract,'authors':authors,'label':str(record.get('version',''))}
        fingerprint = hashlib.sha256(encode(content).encode()).hexdigest()
        ext = str(record.get('external_id') or url)
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT * FROM source_records WHERE source_id=? AND external_id=?',(source_id,ext)).fetchone()
            matches = {r[0] for k in keys for r in c.execute('SELECT item_id FROM identifiers WHERE key=?',(k,))}
            if old: matches.add(old['item_id'])
            if len(matches)>1:
                raise AppError('identifier_conflict','Conflicting identifiers; no records were merged.')
            is_new = not matches
            if is_new:
                item_id = c.execute('INSERT INTO items(kind,title,abstract,url,authors,published_at,first_seen,last_seen,updated_at) VALUES(?,?,?,?,?,?,?,?,?)', (record.get('kind','paper'),title,abstract,url,encode(authors),record.get('published_at'),stamp,stamp,stamp)).lastrowid
            else:
                item_id = next(iter(matches))
                if c.execute('SELECT deleted_at FROM items WHERE id=?',(item_id,)).fetchone()[0]:
                    # Keep identity tombstones so collection cannot resurrect removed records.
                    for key in keys:c.execute('INSERT OR IGNORE INTO identifiers VALUES(?,?)',(key,item_id))
                    return {'id':item_id,'new':False,'updated':False,'duplicate':True,'deleted':True}
            for key in keys:
                c.execute('INSERT OR IGNORE INTO identifiers VALUES(?,?)',(key,item_id))
            if historical and is_new:c.execute('UPDATE items SET history_only=1 WHERE id=?',(item_id,))
            elif not historical:c.execute('UPDATE items SET history_only=0 WHERE id=?',(item_id,))
            raw = encode(record)
            older = False
            if old:
                previous = json.loads(old['raw_json'])
                before, after = re.fullmatch(r'v(\d+)',str(previous.get('version',''))), re.fullmatch(r'v(\d+)',str(record.get('version','')))
                if before and after:
                    older = int(after[1]) < int(before[1])
                elif previous.get('source_updated') and record.get('source_updated'):
                    try:
                        older = dt.datetime.fromisoformat(record['source_updated'].replace('Z','+00:00')) < dt.datetime.fromisoformat(previous['source_updated'].replace('Z','+00:00'))
                    except (ValueError,TypeError): pass
            if old:
                record_id = old['id']
                if older:
                    c.execute('UPDATE source_records SET last_seen=? WHERE id=?',(stamp,record_id))
                else:
                    c.execute('UPDATE source_records SET content_hash=?,raw_json=?,last_seen=? WHERE id=?',(fingerprint,raw,stamp,record_id))
            else:
                record_id = c.execute('INSERT INTO source_records(item_id,source_id,external_id,url,content_hash,raw_json,last_seen) VALUES(?,?,?,?,?,?,?)',(item_id,source_id,ext,url,fingerprint,raw,stamp)).lastrowid
            existed = c.execute('SELECT id FROM versions WHERE record_id=? AND content_hash=?',(record_id,fingerprint)).fetchone()
            changed = old is not None and not existed and not older
            if not existed:
                version_id = c.execute('INSERT INTO versions(item_id,record_id,label,content_hash,title,abstract,observed_at) VALUES(?,?,?,?,?,?,?)',(item_id,record_id,str(record.get('version') or stamp[:10]),fingerprint,title,abstract,stamp)).lastrowid
            else:
                version_id = existed[0]
            current = c.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone()
            primary = is_new or current['primary_record']==record_id or (not current['abstract'] and abstract)
            # Old source snapshots remain available without replacing a newer primary version.
            if not older and primary and (is_new or changed or not current['abstract']):
                c.execute('UPDATE items SET title=?,abstract=?,authors=?,url=?,primary_record=?,current_version=?,last_seen=?,updated_at=?,notice=? WHERE id=?',(title,abstract,encode(authors),url,record_id,version_id,stamp,stamp,'new' if is_new else 'updated' if changed else current['notice'],item_id))
            else:
                c.execute('UPDATE items SET last_seen=? WHERE id=?',(stamp,item_id))
            meta=bibliography(record)
            if not older and not current['published_at'] and record.get('published_at'):c.execute('UPDATE items SET published_at=? WHERE id=?',(record['published_at'],item_id))
            if not older:
                if current['journal'] and not meta['journal']:meta['venue_type']='unknown'
                c.execute("UPDATE items SET journal=CASE WHEN ?<>'' THEN ? ELSE journal END,journal_key=CASE WHEN ?<>'' THEN ? ELSE journal_key END,issns=CASE WHEN ?<>'[]' THEN ? ELSE issns END,venue_type=CASE WHEN ?<>'unknown' THEN ? ELSE venue_type END,author_sort=CASE WHEN ?<>'' THEN ? ELSE author_sort END WHERE id=?",(meta['journal'],meta['journal'],meta['journal_key'],meta['journal_key'],encode(meta['issns']),encode(meta['issns']),meta['venue_type'],meta['venue_type'],meta['author_sort'],meta['author_sort'],item_id))
            return {'id':item_id,'new':is_new,'updated':bool(changed and primary),'duplicate':not is_new and not changed}

    def items(self, query='', kind='', saved=False, limit=300, sort='updated',direction=None,daily=False,deleted=False):
        with self.db() as c:
            where, params = ['i.deleted_at IS NOT NULL' if deleted else 'i.deleted_at IS NULL'], []
            if daily:where.append('i.history_only=0')
            if kind:
                where.append('i.kind=?'); params.append(kind)
            if saved: where.append('i.saved=1')
            if query:
                where.append('(i.title LIKE ? OR i.abstract LIKE ? OR i.notes LIKE ? OR i.authors LIKE ? OR i.journal LIKE ?)')
                params.extend(['%'+query+'%']*5)
            result=[]
            active_version=(self.get('profile')['active'] or {}).get('version',0)
            sql='''SELECT i.*,a.result AS analysis_json,a.model AS analysis_model,a.reasoning_effort AS analysis_effort FROM items i LEFT JOIN analyses a ON a.id=(SELECT MAX(a2.id) FROM analyses a2 WHERE a2.item_id=i.id AND a2.version_id=i.current_version AND a2.profile_version=?)'''+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY i.updated_at DESC,i.id DESC'
            metrics=self.metrics()
            for row in c.execute(sql,(active_version,*params)):
                item=dict(row);item['authors']=json.loads(item['authors']);item['issns']=json.loads(item['issns'])
                raw=item.pop('analysis_json');item['analysis']=json.loads(raw) if raw else None
                result.append(attach_metric(item,metrics))
            rank={'high':0,'medium':1,'low':2,'uncertain':3}
            descending=direction=='desc' if direction else sort in ('updated','published','impact_factor')
            if sort=='relevance':
                scored=[x for x in result if (x['analysis'] or {}).get('relevance') in ('high','medium','low')]
                scored.sort(key=lambda x:rank[x['analysis']['relevance']],reverse=direction=='desc')
                result=scored+[x for x in result if (x['analysis'] or {}).get('relevance')=='uncertain']+[x for x in result if not x['analysis']]
            elif sort in ('author','journal','title','published','impact_factor'):
                key={'author':'author_sort','journal':'journal_key','title':'title','published':'published_at','impact_factor':'impact_factor'}[sort]
                present=[x for x in result if x.get(key) is not None and x.get(key)!=''];missing=[x for x in result if x.get(key) is None or x.get(key)=='']
                present.sort(key=lambda x:x[key].casefold() if isinstance(x[key],str) else x[key],reverse=descending);result=present+missing
            elif direction=='asc':result.reverse()
            return result[:limit] if limit else result

    def item(self, item_id, include_deleted=False):
        with self.db() as c:
            row=c.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone()
            if not row or (row['deleted_at'] and not include_deleted): raise AppError('not_found',status=404)
            result=dict(row);result['authors']=json.loads(result['authors']);result['issns']=json.loads(result['issns'])
            result['sources']=[dict(r) for r in c.execute('SELECT r.id,r.url,r.external_id,r.last_seen,s.name FROM source_records r LEFT JOIN sources s ON r.source_id=s.id WHERE r.item_id=?',(item_id,))]
            result['versions']=[dict(r) for r in c.execute('SELECT id,label,title,abstract,observed_at,record_id FROM versions WHERE item_id=? ORDER BY id DESC',(item_id,))]
            result['identifiers']=[r[0] for r in c.execute('SELECT key FROM identifiers WHERE item_id=?',(item_id,))]
            result['analyses']=[{**dict(r),'result':json.loads(r['result'])} for r in c.execute('SELECT * FROM analyses WHERE item_id=? ORDER BY id DESC LIMIT 20',(item_id,))]
            return attach_metric(result,self.metrics())

    def metrics(self):
        with self.db() as c:return [{**dict(r),'issns':json.loads(r['issns'])} for r in c.execute('SELECT * FROM journal_metrics ORDER BY year DESC,id DESC')]

    def save_metrics(self,rows):
        validated=[validate_metric(row) for row in rows]
        with self.db() as c:
            for m in validated:
                c.execute('INSERT INTO journal_metrics(journal,journal_key,issns,year,impact_factor,source,source_url,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(journal_key,year) DO UPDATE SET journal=excluded.journal,issns=excluded.issns,impact_factor=excluded.impact_factor,source=excluded.source,source_url=excluded.source_url,updated_at=excluded.updated_at',(m['journal'],m['journal_key'],encode(m['issns']),m['year'],m['impact_factor'],m['source'],m['source_url'],now()))
        return len(validated)

    def pending_items(self,profile_version):
        with self.db() as c:return [dict(r) for r in c.execute('SELECT i.id,i.current_version FROM items i WHERE i.deleted_at IS NULL AND i.ignored=0 AND i.history_only=0 AND NOT EXISTS(SELECT 1 FROM analyses a WHERE a.item_id=i.id AND a.version_id=i.current_version AND a.profile_version=?) ORDER BY i.updated_at DESC,i.id DESC',(profile_version,))]

    def set_deleted(self,kind,record_id,deleted):
        table={'items':'items','histories':'histories'}[kind]
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute(f'SELECT deleted_at FROM {table} WHERE id=?',(record_id,)).fetchone()
            if not row:raise AppError('not_found',status=404)
            stamp=(row['deleted_at'] or now()) if deleted else None
            c.execute(f'UPDATE {table} SET deleted_at=? WHERE id=?',(stamp,record_id))
            if kind=='items' and not deleted:
                c.execute("UPDATE analysis_tasks SET status='pending',error=NULL WHERE item_id=? AND status='skipped' AND error='item_in_trash'",(record_id,))
            if kind=='items' and deleted:
                for digest in c.execute('SELECT day,item_ids FROM digests').fetchall():
                    ids=json.loads(digest['item_ids'])
                    if record_id in ids:c.execute('UPDATE digests SET item_ids=? WHERE day=?',(encode([i for i in ids if i!=record_id]),digest['day']))
        return {'id':record_id,'deleted':deleted}

    def job(self,job_id):
        with self.db() as c:
            row=c.execute('SELECT * FROM runs WHERE id=?',(job_id,)).fetchone()
            if not row:raise AppError('not_found',status=404)
            result=dict(row)
            for key in ('argument','progress','result'):result[key]=json.loads(result[key])
            counts={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM analysis_tasks WHERE run_id=? GROUP BY status',(job_id,))}
            result['queue']={'total':sum(counts.values()),**counts}
            return result

    def feedback(self,item_id,body):
        allowed={'saved','is_read','ignored','notes'}
        with self.db() as c:
            if not c.execute('SELECT 1 FROM items WHERE id=? AND deleted_at IS NULL',(item_id,)).fetchone():raise AppError('not_found',status=404)
            for k in allowed & body.keys():
                value=str(body[k])[:30000] if k=='notes' else int(bool(body[k]))
                c.execute(f'UPDATE items SET {k}=? WHERE id=?',(value,item_id))

    def reserve_ai(self,task):
        s=self.settings();day=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=s['utc_offset'])).date().isoformat()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            count=c.execute('SELECT COUNT(*) FROM ai_usage WHERE day=?',(day,)).fetchone()[0]
            if count>=s['daily_ai_limit']:raise AppError('daily_ai_limit',status=429)
            return c.execute("INSERT INTO ai_usage(day,task,status,created_at) VALUES(?,?,'started',?)",(day,task,now())).lastrowid

    def finish_ai(self,usage_id,status):
        with self.db() as c:c.execute('UPDATE ai_usage SET status=? WHERE id=?',(status,usage_id))

    def backup(self):
        folder=self.directory/'backups';folder.mkdir(exist_ok=True)
        destination=folder/(now()[:10]+'.sqlite3')
        with contextlib.closing(sqlite3.connect(self.path)) as source, contextlib.closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        return destination

    def stats(self):
        with self.db() as c:
            active=(self.get('profile')['active'] or {}).get('version',0)
            pending=len(self.pending_items(active))
            return {'total':c.execute('SELECT COUNT(*) FROM items WHERE deleted_at IS NULL').fetchone()[0],'saved':c.execute('SELECT COUNT(*) FROM items WHERE saved=1 AND deleted_at IS NULL').fetchone()[0],'versions':c.execute('SELECT COUNT(*) FROM versions v JOIN items i ON i.id=v.item_id WHERE i.deleted_at IS NULL').fetchone()[0],'pending':pending,'runs':[dict(r) for r in c.execute("SELECT * FROM runs WHERE kind NOT IN ('history_plan','history_search') OR EXISTS(SELECT 1 FROM histories h WHERE h.id=json_extract(runs.argument,'$.input') AND h.deleted_at IS NULL) ORDER BY id DESC LIMIT 10")]}
