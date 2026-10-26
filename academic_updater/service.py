from __future__ import annotations
import datetime as dt
import json
import threading
from .network import AppError,validate_url
from .sources import collect,import_link
from .storage import encode,now
from .ai import EFFORTS
from .history import History,HISTORY_KINDS

class JobPaused(Exception):
    def __init__(self,code='paused_by_user'):self.code=code

class Service:
    def __init__(self,store,ai):
        self.store,self.ai=store,ai
        self.lock=threading.Lock();self.stop=threading.Event();self.cancel=threading.Event();self.current_job=None
        self.history=History(self)

    def start_job(self,kind,argument=None):
        if kind in HISTORY_KINDS:
            h=self.history.get(argument,False)
            if kind=='history_plan' and h['progress'].get('search_started'):raise AppError('history_locked')
            if kind=='history_search' and (not h['scope'].get('queries') or not (h['scope'].get('field_en') or h['scope'].get('field_zh'))):raise AppError('history_scope_required')
        if not self.lock.acquire(False):raise AppError('job_already_running',status=409)
        try:
            if kind in HISTORY_KINDS:self.history.get(argument,False)
            if kind=='item_analysis':self.store.item(argument)
            payload={'input':argument,'profile':self.store.get('profile')['active'],'settings':self.store.settings()}
            with self.store.db() as c:job=c.execute("INSERT INTO runs(kind,status,started_at,argument) VALUES(?,'running',?,?)",(kind,now(),encode(payload))).lastrowid
            self._launch(job);return job
        except Exception:self.lock.release();raise

    def _launch(self,job):
        self.cancel.clear();self.current_job=job
        threading.Thread(target=self._run,args=(job,),daemon=True).start()

    def resume(self,job):
        row=self.store.job(job)
        if row['kind'] not in ('collect','analyze',*HISTORY_KINDS) or row['status'] not in ('interrupted','paused','partial','failed'):raise AppError('job_not_resumable')
        if not self.lock.acquire(False):raise AppError('job_already_running',status=409)
        try:
            argument=row['argument'];progress=row['progress']
            if row['kind'] in HISTORY_KINDS:self.history.get(argument.get('input'),False)
            if not argument:
                argument={'input':None,'profile':self.store.get('profile')['active'],'settings':self.store.settings()}
                # Old versions checkpointed each successful analysis but had no task table.
                with self.store.db() as c:had_analysis=c.execute('SELECT 1 FROM analyses WHERE created_at>=? LIMIT 1',(row['started_at'],)).fetchone()
                progress['phase']='analysis' if had_analysis or row['kind']=='analyze' else 'collection'
            progress.pop('pause_requested',None)
            with self.store.db() as c:
                c.execute("UPDATE runs SET status='running',finished_at=NULL,error=NULL,argument=?,progress=? WHERE id=?",(encode(argument),encode(progress),job))
                c.execute("UPDATE analysis_tasks SET status='pending',error=NULL WHERE run_id=? AND status IN ('running','failed')",(job,))
            self._launch(job);return job
        except Exception:self.lock.release();raise

    def pause(self,job):
        if self.current_job!=job:raise AppError('job_not_running')
        self.cancel.set();self._checkpoint(job,pause_requested=True)

    def recover_interrupted(self):
        with self.store.db() as c:row=c.execute("SELECT id,progress FROM runs WHERE kind IN ('collect','analyze','history_plan','history_search') AND status='interrupted' AND (kind IN ('collect','analyze') OR EXISTS(SELECT 1 FROM histories h WHERE h.id=json_extract(runs.argument,'$.input') AND h.deleted_at IS NULL)) ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            if json.loads(row['progress']).get('pause_requested'):
                with self.store.db() as c:c.execute("UPDATE runs SET status='paused',error='paused_by_user' WHERE id=?",(row['id'],))
            else:self.resume(row['id'])

    def set_deleted(self,kind,record_id,deleted):
        # Serialize with workers, including scheduled collection and resumed analysis.
        if not self.lock.acquire(False):raise AppError('pause_before_delete',status=409)
        try:return self.store.set_deleted(kind,record_id,deleted)
        finally:self.lock.release()

    def _checkpoint(self,job,**changes):
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE');old=json.loads(c.execute('SELECT progress FROM runs WHERE id=?',(job,)).fetchone()[0]);old.update(changes)
            c.execute('UPDATE runs SET progress=? WHERE id=?',(encode(old),job))

    def _check_pause(self):
        if self.cancel.is_set() or self.stop.is_set():raise JobPaused()

    def _run(self,job):
        row=self.store.job(job);kind=row['kind'];payload=row['argument'];result={}
        try:
            if kind=='collect':
                if row['progress'].get('phase')!='analysis':self._collect(job,payload)
                result=self.store.job(job)['progress'].get('collection',{})
                result['analysis']=self._analyze_queue(job,payload)
            elif kind=='analyze':result=self._analyze_queue(job,payload)
            elif kind=='history_plan':result=self.history.plan(payload['input'],payload['settings'])
            elif kind=='history_search':result=self.history.search(payload['input'],payload['settings'],job)
            elif kind=='interpret':result={'profile':self.ai.interpret(payload['input'])}
            elif kind=='item_analysis':result={'analysis':self.ai.analyze(payload['input'],profile=payload['profile'],settings=payload['settings'])}
            elif kind=='import':
                result=self.store.ingest(0,import_link(payload['input']['value'],payload['input'].get('kind','paper')))
                if result.get('deleted'):raise AppError('item_in_trash')
            else:raise AppError('invalid_job')
            partial=result.get('errors') or result.get('truncated') or result.get('analysis',{}).get('errors')
            with self.store.db() as c:c.execute('UPDATE runs SET status=?,finished_at=?,result=?,error=NULL WHERE id=?',('partial' if partial else 'complete',now(),encode(result),job))
        except JobPaused as exc:
            with self.store.db() as c:c.execute("UPDATE runs SET status='paused',finished_at=?,error=? WHERE id=?",(now(),exc.code,job))
        except Exception as exc:
            detail=(exc.code+': '+exc.detail) if isinstance(exc,AppError) else type(exc).__name__
            with self.store.db() as c:c.execute("UPDATE runs SET status=?,finished_at=?,error=? WHERE id=?",('paused' if kind in HISTORY_KINDS and isinstance(exc,AppError) and exc.code in ('daily_ai_limit','ai_not_connected','model_not_selected','subscription_not_authorized','sign_in_again','reasoning_not_supported') else 'failed',now(),detail,job))
        finally:
            try:
                if kind in HISTORY_KINDS:
                    final=self.store.job(job)
                    state='draft' if kind=='history_plan' and final['status']=='complete' else final['status']
                    self.history.update(payload['input'],status=state,error=final.get('error') or '')
                if kind in ('collect','analyze','item_analysis'):
                    try:self.digest()
                    except Exception:pass
            finally:self.current_job=None;self.lock.release()

    def _collect(self,job,payload):
        active=payload['profile'];settings=payload['settings']
        if not active:raise AppError('research_not_applied')
        self.store.backup();progress=self.store.job(job)['progress']
        result=progress.get('collection',{'new':0,'updated':0,'duplicates':0,'errors':[],'truncated':[]})
        done=progress.get('sources_done',[])
        for source in self.store.sources():
            if not source['enabled'] or source['id'] in done:continue
            self._check_pause();self._checkpoint(job,phase='collection',source=source['name'],collection=result,sources_done=done)
            try:
                records,truncated=collect(source,active,settings)
                for record in records:
                    self._check_pause()
                    try:
                        info=self.store.ingest(source['id'],record)
                        result['new']+=int(info['new']);result['updated']+=int(info['updated']);result['duplicates']+=int(info['duplicate'])
                    except AppError as exc:result['errors'].append(source['name']+': '+exc.code)
                if truncated:
                    result['truncated'].append(source['name']);self.store.source_status(source['id'],'limited','Collection limit reached.')
                else:self.store.source_status(source['id'],'ok')
            except AppError as exc:
                detail=exc.code+': '+exc.detail;result['errors'].append(source['name']+': '+detail);self.store.source_status(source['id'],'error',detail)
            done.append(source['id']);self._checkpoint(job,collection=result,sources_done=done)
        self._checkpoint(job,phase='analysis')

    def _analyze_queue(self,job,payload):
        active=payload['profile'];settings=payload['settings']
        if not active:raise AppError('research_not_applied')
        self._checkpoint(job,phase='analysis',model=settings['model'],reasoning_effort=settings.get('reasoning_effort','default'),profile_version=active['version'])
        for item in self.store.pending_items(active['version']):
            with self.store.db() as c:c.execute("INSERT OR IGNORE INTO analysis_tasks(run_id,item_id,version_id,profile_version,updated_at) VALUES(?,?,?,?,?)",(job,item['id'],item['current_version'],active['version'],now()))
        errors=[];consecutive=0
        while True:
            self._check_pause()
            with self.store.db() as c:
                task=c.execute("SELECT * FROM analysis_tasks WHERE run_id=? AND status='pending' ORDER BY id LIMIT 1",(job,)).fetchone()
            if not task:break
            item=self.store.item(task['item_id'],include_deleted=True)
            if item['deleted_at']:
                with self.store.db() as c:c.execute("UPDATE analysis_tasks SET status='skipped',error='item_in_trash',updated_at=? WHERE id=?",(now(),task['id']))
                continue
            with self.store.db() as c:
                already=c.execute('SELECT 1 FROM analyses WHERE item_id=? AND version_id=? AND profile_version=?',(task['item_id'],task['version_id'],task['profile_version'])).fetchone()
                if already or item['ignored']:
                    c.execute('UPDATE analysis_tasks SET status=?,updated_at=? WHERE id=?',('completed' if already else 'skipped',now(),task['id']));continue
                c.execute("UPDATE analysis_tasks SET status='running',attempts=attempts+1,updated_at=? WHERE id=?",(now(),task['id']))
            self._checkpoint(job,current_item=task['item_id'],current_title=item['title'][:240])
            try:
                self.ai.analyze(task['item_id'],profile=active,settings=settings,expected_version=task['version_id'])
                with self.store.db() as c:c.execute("UPDATE analysis_tasks SET status='completed',error=NULL,updated_at=? WHERE id=?",(now(),task['id']))
                consecutive=0;self.digest()
            except AppError as exc:
                blocked=exc.code in ('daily_ai_limit','ai_not_connected','model_not_selected','subscription_not_authorized','sign_in_again','reasoning_not_supported')
                status='pending' if blocked else 'skipped' if exc.code=='source_version_changed' else 'failed'
                with self.store.db() as c:c.execute('UPDATE analysis_tasks SET status=?,error=?,updated_at=? WHERE id=?',(status,exc.code,now(),task['id']))
                if blocked:raise JobPaused(exc.code)
                errors.append(str(task['item_id'])+': '+exc.code);consecutive+=1
                if consecutive>=3:break
            finally:self._checkpoint(job,current_item=None,current_title='')
        queue=self.store.job(job)['queue']
        return {'analyzed':queue.get('completed',0),'errors':errors,'remaining':queue.get('pending',0)+queue.get('failed',0)}

    def digest(self):
        s=self.store.settings();day=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=s['utc_offset'])).date().isoformat()
        ranked=self.store.items(limit=None,sort='relevance',daily=True)
        with self.store.db() as c:
            existing=c.execute('SELECT item_ids FROM digests WHERE day=?',(day,)).fetchone();old=set(json.loads(existing[0]) if existing else [])
            candidates=[]
            for item in ranked:
                if item['ignored'] or (item['analysis'] or {}).get('relevance')=='low':continue
                delivered=c.execute('SELECT 1 FROM delivered WHERE item_id=? AND version_id=?',(item['id'],item['current_version'])).fetchone()
                if item['id'] in old or not delivered:candidates.append(item)
            selected=candidates[:s['daily_digest_limit']];ids=[i['id'] for i in selected]
            for item in selected:c.execute('INSERT OR IGNORE INTO delivered VALUES(?,?)',(item['id'],item['current_version']))
            c.execute('INSERT INTO digests VALUES(?,?,?) ON CONFLICT(day) DO UPDATE SET item_ids=excluded.item_ids',(day,encode(ids),now()))
        return {'day':day,'ids':ids}

    def scheduler(self):
        while not self.stop.wait(20):
            try:self.schedule_tick()
            except AppError:pass

    def schedule_tick(self,current=None):
        s=self.store.settings()
        if not s['schedule_enabled'] or not self.store.get('profile')['active'] or self.lock.locked():return
        with self.store.db() as c:
            if c.execute("SELECT 1 FROM runs WHERE status IN ('paused','interrupted') AND kind IN ('collect','analyze') LIMIT 1").fetchone():return
        local=(current or dt.datetime.now(dt.timezone.utc))+dt.timedelta(hours=s['utc_offset']);day=local.date().isoformat()
        if local.strftime('%H:%M')<s['schedule_time'] or self.store.get('scheduled_day')==day:return
        self.start_job('collect');self.store.put('scheduled_day',day)

    def add_source(self,body):
        kind=body.get('kind')
        if kind not in ('paper','industry','conference'):raise AppError('invalid_source_type')
        url=validate_url(str(body.get('url','')).strip());name=str(body.get('name','')).strip()[:150]
        if not name:raise AppError('missing_name')
        with self.store.db() as c:
            if c.execute('SELECT 1 FROM sources WHERE url=?',(url,)).fetchone():raise AppError('source_exists',status=409)
            c.execute('INSERT INTO sources(kind,name,url) VALUES(?,?,?)',(kind,name,url))

    def save_settings(self,body):
        s=self.store.settings()
        if any(k in body and body[k]!=s[k] for k in ('model','provider','local_url')):s['reasoning_effort']='default'
        enums={'language':['zh-CN','en'],'summary_language':['auto','zh-CN','en'],'provider':['subscription','api','local'],'reasoning_effort':['default',*EFFORTS]}
        bounds={'daily_ai_limit':(1,500),'daily_digest_limit':(1,50),'utc_offset':(-12,14),'lookback_days':(1,365),'max_per_source':(1,200)}
        for key,allowed in enums.items():
            if key in body:
                if body[key] not in allowed:raise AppError('invalid_setting')
                s[key]=body[key]
        for key,(low,high) in bounds.items():
            if key in body:
                try:value=float(body[key]) if key=='utc_offset' else int(body[key])
                except (TypeError,ValueError):raise AppError('invalid_setting')
                if not low<=value<=high:raise AppError('invalid_setting')
                s[key]=value
        if 'schedule_time' in body:
            try:dt.datetime.strptime(body['schedule_time'],'%H:%M')
            except (ValueError,TypeError):raise AppError('invalid_setting')
            s['schedule_time']=body['schedule_time']
        if 'schedule_enabled' in body:s['schedule_enabled']=bool(body['schedule_enabled'])
        if 'model' in body:s['model']=str(body['model']).strip()[:120]
        if 'local_url' in body:s['local_url']=validate_url(str(body['local_url']).strip().rstrip('/'),local=True)
        self.ai.check_effort(s)
        self.store.put('settings',s);return s
