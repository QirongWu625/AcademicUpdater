from __future__ import annotations
import csv
import io
import json
import mimetypes
import os
import re
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from . import __version__
from .ai import AI,validate_scope
from .credentials import Vault,OAuth
from .network import AppError
from .service import Service
from .storage import Store,encode,now
from .metadata import parse_metrics_csv
from .scispace import research_question,HOME as SCISPACE_HOME
from . import startup


class Application:
    def __init__(self,directory):
        self.store=Store(directory);self.vault=Vault(directory);self.oauth=OAuth(self.vault,self.store)
        self.ai=AI(self.store,self.vault,self.oauth);self.service=Service(self.store,self.ai)
        self.csrf=secrets.token_urlsafe(32);self.port=0

    def bootstrap(self):
        with self.store.db() as c:
            ids=[r[0] for r in c.execute("SELECT id FROM runs WHERE (kind NOT IN ('history_plan','history_search') OR EXISTS(SELECT 1 FROM histories h WHERE h.id=json_extract(runs.argument,'$.input') AND h.deleted_at IS NULL)) ORDER BY CASE WHEN status='running' THEN 0 WHEN status IN ('paused','interrupted','failed') THEN 1 ELSE 2 END,id DESC LIMIT 30")]
        learning=self.store.saved_scope_snapshot(include_papers=False)
        jobs=[self.store.job(i) for i in ids]
        for job in jobs:job['ai_state']=self.service.job_ai_state(job)
        return {'app':'AcademicUpdater','version':__version__,'csrf':self.csrf,'settings':self.store.settings(),'profile':self.store.get('profile'),'sources':self.store.sources(),'stats':self.store.stats(),'auth':self.auth_status(),'capabilities':self.ai.capabilities(),'histories':self.service.history.list(),
                'jobs':jobs,'execution':self.service.ai_limiter.state(),'startup':startup.status(),
                'scheduler':self.store.get('scheduler_status',{}),'scheduled_day':self.store.get('scheduled_day'),'local_day':self.service.local_day(),
                'saved_learning':{'pending':learning['changed'],'count':learning['count']} if learning else None}

    def auth_status(self):
        return {'accounts':self.oauth.accounts(),'api_key_configured':bool(os.environ.get('OPENAI_API_KEY') or self.vault.get('api_key')),'key_from_environment':bool(os.environ.get('OPENAI_API_KEY')),'last_error':self.oauth.last_error}


def make_server(app,port):
    static=Path(__file__).resolve().parent.parent/'static'
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'

        def log_message(self,*args):pass

        def check_origin(self,write=False):
            allowed={f'127.0.0.1:{app.port}',f'localhost:{app.port}'}
            if self.headers.get('Host') not in allowed:raise AppError('invalid_host',status=403)
            origin=self.headers.get('Origin')
            if origin and origin not in {'http://'+x for x in allowed}:raise AppError('invalid_origin',status=403)
            if write and not secrets.compare_digest(self.headers.get('X-Academic-Token',''),app.csrf):raise AppError('invalid_session',status=403)

        def send(self,body,content_type='application/json; charset=utf-8',status=200,filename=None):
            if isinstance(body,str):body=body.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
            self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass

        def json(self,value,status=200):self.send(encode(value),status=status)

        def handle_error(self,exc):
            if isinstance(exc,AppError):self.json({'error':exc.code,'detail':exc.detail},exc.status)
            else:self.json({'error':'internal_error','detail':type(exc).__name__},500)

        def do_OPTIONS(self):self.send(b'',status=403)

        def do_GET(self):
            try:
                self.check_origin()
                parsed=urllib.parse.urlsplit(self.path);path=parsed.path;q={k:v[0] for k,v in urllib.parse.parse_qs(parsed.query).items()}
                if path=='/api/health':return self.json({'app':'AcademicUpdater','version':__version__})
                if path=='/api/bootstrap':return self.json(app.bootstrap())
                if path=='/api/scispace/context':
                    if q.get('history_id'):
                        try:hid=int(q['history_id'])
                        except ValueError:raise AppError('invalid_setting')
                        h=app.service.history.get(hid,False);scope=h['scope'];prompt=h['prompt']
                    else:
                        active=app.store.get('profile').get('active') or {};scope=active.get('understanding') or {};prompt=active.get('prompt','')
                        if active.get('exclude'):prompt+='\nExplicit exclusions: '+active['exclude']
                    return self.json({'question':research_question(scope,prompt,bool(q.get('history_id'))),'url':SCISPACE_HOME,'mode':'manual_import'})
                if path=='/api/items':return self.json(app.store.items(q.get('q','')[:300],q.get('kind',''),q.get('saved')=='1',sort=q.get('sort','updated'),direction=q.get('direction'),daily=q.get('today')=='1',deleted=q.get('deleted')=='1' and q.get('today')!='1'))
                if path=='/api/model-capabilities':return self.json(app.ai.capabilities({**app.store.settings(),'model':q.get('model',app.store.settings()['model'])}))
                if path=='/api/histories':return self.json(app.service.history.list(deleted=q.get('deleted')=='1'))
                history_route=re.fullmatch(r'/api/histories/(\d+)(?:/(export|papers))?',path)
                if history_route:
                    hid=int(history_route[1]);h=app.service.history
                    if history_route[2]=='papers':return self.json(h.papers(hid,q))
                    if history_route[2]=='export':
                        return self.send(encode(h.get(hid)),'application/json; charset=utf-8',filename=f'AcademicUpdater-history-{hid}.json')
                    return self.json(h.get(hid,False))
                if path=='/api/metrics':return self.json(app.store.metrics())
                if path=='/api/metrics/template':return self.send('\ufeffjournal,year,impact_factor,source,issns,source_url\r\n','text/csv; charset=utf-8',filename='journal-impact-factors-template.csv')
                if re.fullmatch(r'/api/items/\d+',path):return self.json(app.store.item(int(path.rsplit('/',1)[1])))
                if re.fullmatch(r'/api/jobs/\d+',path):
                    return self.json(app.store.job(int(path.rsplit('/',1)[1])))
                if path=='/api/digest':
                    with app.store.db() as c:row=c.execute('SELECT * FROM digests ORDER BY day DESC LIMIT 1').fetchone()
                    return self.json({'day':row['day'],'ids':json.loads(row['item_ids'])} if row else {'day':None,'ids':[]})
                if path=='/api/export':
                    with app.store.db() as c:ids=[r[0] for r in c.execute('SELECT id FROM items WHERE deleted_at IS NULL ORDER BY id')]
                    if q.get('format')=='csv':
                        output=io.StringIO();writer=csv.writer(output);writer.writerow(['id','type','title','url','published_at','authors','journal','issns','impact_factor','if_year','if_source','if_source_url','saved','read','notes'])
                        def safe(v):
                            v=str(v or '')
                            return "'"+v if v.lstrip().startswith(('=','+','-','@')) else v
                        for item_id in ids:
                            i=app.store.item(item_id);writer.writerow([i['id'],i['kind'],safe(i['title']),safe(i['url']),safe(i['published_at']),safe('; '.join(i['authors'])),safe(i['journal']),safe('; '.join(i['issns'])),i['impact_factor'],i['if_year'],safe(i['if_source']),safe(i['if_source_url']),i['saved'],i['is_read'],safe(i['notes'])])
                        return self.send('\ufeff'+output.getvalue(),'text/csv; charset=utf-8',filename='AcademicUpdater.csv')
                    return self.send('\n'.join(encode(app.store.item(i)) for i in ids),'application/x-ndjson; charset=utf-8',filename='AcademicUpdater.jsonl')
                if path=='/api/backup':
                    p=app.store.backup();return self.send(p.read_bytes(),'application/octet-stream',filename='AcademicUpdater-backup.sqlite3')
                if path=='/auth/callback':
                    try:enabled=app.oauth.callback(q);app.oauth.last_error='' if enabled else 'subscription_not_authorized'
                    except AppError as exc:app.oauth.last_error=exc.code
                    self.send_response(303);self.send_header('Location','/#ai');self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
                files={'/logo.png':'logo.png','/':'index.html','/index.html':'index.html','/app.js':'app.js','/history.js':'history.js','/trash.js':'trash.js','/execution.js':'execution.js','/scispace.js':'scispace.js','/i18n.js':'i18n.js','/styles.css':'styles.css','/guide':'guide.html'}
                if path not in files:raise AppError('not_found',status=404)
                file=static/files[path]
                content=file.read_bytes()
                if file.name=='index.html':content=content.replace(b'__APP_VERSION__',__version__.encode())
                self.send(content,(mimetypes.guess_type(str(file))[0] or 'text/plain')+'; charset=utf-8')
            except Exception as exc:self.handle_error(exc)

        def do_POST(self):
            try:
                self.check_origin(True)
                length=int(self.headers.get('Content-Length','0'))
                if not 0<=length<=200_000:raise AppError('request_too_large',status=413)
                if not self.headers.get('Content-Type','').startswith('application/json'):raise AppError('json_required',status=415)
                try:body=json.loads(self.rfile.read(length)) if length else {}
                except ValueError:raise AppError('invalid_json')
                if not isinstance(body,dict):raise AppError('invalid_json')
                path=urllib.parse.urlsplit(self.path).path
                deletion=re.fullmatch(r'/api/(items|histories)/(\d+)/(delete|restore)',path)
                if deletion:return self.json(app.service.set_deleted(deletion[1],int(deletion[2]),deletion[3]=='delete'))
                if path=='/api/histories':return self.json(app.service.history.save(body))
                history_route=re.fullmatch(r'/api/histories/(\d+)(?:/(plan|search))?',path)
                if history_route:
                    hid=int(history_route[1]);operation=history_route[2]
                    if not operation:return self.json(app.service.history.save(body,hid))
                    return self.json({'job_id':app.service.start_job('history_'+operation,hid),'history_id':hid})
                if path=='/api/profile/save':return self.json(app.store.save_profile(body))
                if path=='/api/profile/interpret':return self.json({'job_id':app.service.start_job('interpret',body.get('revision'))})
                if path=='/api/profile/apply':
                    u=validate_scope(body.get('understanding'))
                    current=app.store.get('profile')
                    origin='ai' if current['origin']=='ai' and current['understanding']==u and current['understanding_revision']==body.get('revision') else 'manual'
                    return self.json(app.store.apply_profile(body.get('revision'),u,origin))
                if path=='/api/settings':return self.json(app.service.save_settings(body))
                if path=='/api/startup':return self.json(startup.configure(bool(body.get('enabled'))))
                if path=='/api/settings/key':
                    key=str(body.get('key','')).strip()
                    if key and not 10<=len(key)<=2000:raise AppError('invalid_api_key')
                    app.vault.set('api_key',key or None);return self.json(app.auth_status())
                if path=='/api/auth/start':return self.json({'url':app.oauth.start(app.port,body.get('account_id'))})
                if path=='/api/auth/select':app.oauth.select(body.get('account_id'));return self.json(app.auth_status())
                if path=='/api/auth/disconnect':return self.json({'revoked':app.oauth.disconnect(body.get('account_id')),'auth':app.auth_status()})
                if path=='/api/models':return self.json({'models':app.ai.models()})
                if path=='/api/metrics':return self.json({'saved':app.store.save_metrics([body])})
                if path=='/api/metrics/import':return self.json({'saved':app.store.save_metrics(parse_metrics_csv(str(body.get('csv',''))))})
                job_action=re.fullmatch(r'/api/jobs/(\d+)/(pause|resume)',path)
                if job_action:
                    job_id=int(job_action[1])
                    if job_action[2]=='pause':app.service.pause(job_id);return self.json(app.store.job(job_id))
                    return self.json({'job_id':app.service.resume(job_id)})
                if path=='/api/collect':return self.json(app.service.collect_updates())
                if path=='/api/analyze':return self.json({'job_id':app.service.start_job('analyze')})
                if path=='/api/import':
                    if body.get('kind','paper') not in ('paper','industry','conference'):raise AppError('invalid_source_type')
                    return self.json({'job_id':app.service.start_job('import',{'value':str(body.get('value','')).strip()[:4000],'kind':body.get('kind','paper')})})
                if path in ('/api/scispace/preview','/api/scispace/import'):return self.json(app.service.scispace_import(body,preview=path.endswith('/preview')))
                if path=='/api/sources':app.service.add_source(body);return self.json(app.store.sources())
                if re.fullmatch(r'/api/sources/\d+',path):
                    source_id=int(path.rsplit('/',1)[1])
                    with app.store.db() as c:
                        source=c.execute('SELECT kind FROM sources WHERE id=?',(source_id,)).fetchone()
                        if not source:raise AppError('not_found',status=404)
                        if source['kind']=='scispace_import' and body.get('enabled'):raise AppError('scispace_manual_source')
                        if 'enabled' in body:c.execute('UPDATE sources SET enabled=? WHERE id=?',(int(bool(body['enabled'])),source_id))
                        if 'query' in body:c.execute('UPDATE sources SET query=? WHERE id=?',(str(body['query']).strip()[:1000],source_id))
                    return self.json(app.store.sources())
                match=re.fullmatch(r'/api/items/(\d+)/(feedback|analyze)',path)
                if match:
                    item_id=int(match[1]);app.store.item(item_id)
                    if match[2]=='analyze':return self.json({'job_id':app.service.start_job('item_analysis',item_id)})
                    app.store.feedback(item_id,body);return self.json(app.store.item(item_id))
                raise AppError('not_found',status=404)
            except Exception as exc:self.handle_error(exc)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True;app.port=server.server_address[1]
    return server
