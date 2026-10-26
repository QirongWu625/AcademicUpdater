import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock,patch

from academic_updater.storage import Store,encode,now
from academic_updater.service import Service
from academic_updater.server import Application,make_server
from academic_updater.network import AppError
from test_core import record,scope
from test_history import ControlledAI,history_record


class TrashTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.ai=ControlledAI();self.service=Service(self.store,self.ai);self.history=self.service.history
        p=self.store.save_profile({'revision':0,'prompt':'Measurement methods'})
        self.store.apply_profile(p['revision'],scope())

    def tearDown(self):self.tmp.cleanup()

    def create_history(self,analyze=True):
        return self.history.save({'prompt':'Measurement history','scope':{'field_en':'Measurement','queries':['measurement']},'config':{'sources':['crossref'],'limit':100,'analyze':analyze,'discovery_mode':'all'}})['id']

    def wait(self):
        until=time.monotonic()+8
        while self.service.lock.locked() and time.monotonic()<until:time.sleep(.02)
        self.assertFalse(self.service.lock.locked())

    def search(self,hid):
        with patch('academic_updater.history.historical_page',return_value=([history_record(1),history_record(2)],{'position':2,'total':2,'done':True})):
            job=self.service.start_job('history_search',hid);self.wait()
        self.assertEqual(self.store.job(job)['status'],'complete')
        return job

    def test_delete_restore_preserves_notes_versions_and_analysis(self):
        from test_upgrade import save_analysis
        item=self.store.ingest(1,record())['id'];self.store.feedback(item,{'notes':'Keep my note','saved':True,'is_read':True})
        save_analysis(self.store,item,'high')
        before=self.store.item(item);self.service.digest()
        self.service.set_deleted('items',item,True)
        self.assertEqual(self.store.items(),[]);self.assertEqual(self.store.pending_items(1),[])
        self.assertEqual(self.store.stats()['total'],0);self.assertEqual(self.store.stats()['saved'],0)
        self.assertEqual(self.service.digest()['ids'],[])
        self.assertEqual(self.store.items(deleted=True)[0]['id'],item)
        with self.assertRaises(AppError):self.store.item(item)
        with self.assertRaises(AppError):self.store.feedback(item,{'notes':'overwrite'})
        self.service.set_deleted('items',item,False)
        self.assertEqual(self.store.item(item),before)

    def test_collection_and_cross_source_import_do_not_resurrect(self):
        original=record();item=self.store.ingest(1,original)['id'];self.service.set_deleted('items',item,True)
        for source in (1,0,2):
            result=self.store.ingest(source,{**original,'title':'Changed upstream title'},historical=source==2)
            self.assertTrue(result['deleted']);self.assertEqual(result['id'],item)
        self.assertEqual(self.store.stats()['total'],0)
        self.service.set_deleted('items',item,False);self.assertEqual(self.store.item(item)['title'],original['title'])

    def test_search_delete_preserves_library_results_and_progress(self):
        hid=self.create_history();job=self.search(hid);before=self.history.get(hid);items=self.store.items()
        self.service.set_deleted('histories',hid,True)
        self.assertEqual(self.history.list(),[]);self.assertEqual(self.history.list(True)[0]['id'],hid)
        self.assertEqual(self.store.items(),items)
        self.assertNotIn(job,[j['id'] for j in self.store.stats()['runs']])
        with self.assertRaises(AppError):self.history.get(hid)
        with self.assertRaises(AppError):self.service.start_job('history_search',hid)
        self.service.set_deleted('histories',hid,False)
        self.assertEqual(self.history.get(hid),before)

    def test_removed_papers_hidden_in_history_counts_export_and_timeline(self):
        hid=self.create_history();self.search(hid);before=self.history.get(hid);item=before['items'][0]['id']
        self.service.set_deleted('items',item,True);h=self.history.get(hid)
        self.assertEqual(h['counts']['total'],1);self.assertEqual(len(h['items']),1)
        self.assertEqual(self.history.papers(hid,{})['total'],1)
        self.assertEqual(self.history.list()[0]['count'],1)
        self.assertEqual(h['report'],{});self.assertTrue(h['report_hidden_due_to_deleted_papers'])
        self.service.set_deleted('items',item,False);self.assertEqual(self.history.get(hid),before)

    def test_history_collection_skips_trashed_record(self):
        item=self.store.ingest(1,history_record(1))['id'];self.service.set_deleted('items',item,True)
        hid=self.create_history();self.search(hid)
        self.assertEqual(self.history.get(hid)['counts']['total'],1)
        self.assertNotIn(item,[i['id'] for i in self.history.get(hid)['items']])

    def test_timeline_rebuild_uses_remaining_papers(self):
        hid=self.create_history();self.search(hid);removed=self.history.get(hid)['items'][0]['id']
        self.service.set_deleted('items',removed,True)
        self.search(hid);h=self.history.get(hid)
        self.assertNotIn('report_hidden_due_to_deleted_papers',h)
        self.assertNotIn(removed,[r['id'] for r in h['report']['references']])
        self.assertEqual(h['report']['sample_count'],1)

    def test_paused_history_analysis_skips_deleted_pending_paper(self):
        hid=self.create_history();job=self.search(hid);item=self.history.get(hid)['items'][0]['id']
        with self.store.db() as c:
            c.execute("UPDATE history_items SET status='pending',result='{}' WHERE history_id=? AND item_id=?",(hid,item))
            c.execute("UPDATE runs SET status='paused' WHERE id=?",(job,))
            c.execute("UPDATE histories SET status='paused' WHERE id=?",(hid,))
        self.service.set_deleted('items',item,True);self.ai.calls=[]
        self.service.resume(job);self.wait()
        self.assertEqual(self.store.job(job)['status'],'complete')
        self.assertNotIn('history_papers',[c[0] for c in self.ai.calls])

    def test_delete_and_restore_blocked_while_worker_is_active(self):
        item=self.store.ingest(1,record())['id'];hid=self.create_history()
        self.service.lock.acquire()
        try:
            for kind,i in [('items',item),('histories',hid)]:
                for deleted in (True,False):
                    with self.assertRaises(AppError) as e:self.service.set_deleted(kind,i,deleted)
                    self.assertEqual(e.exception.code,'pause_before_delete');self.assertEqual(e.exception.status,409)
        finally:self.service.lock.release()
        self.assertIsNone(self.store.item(item)['deleted_at']);self.assertEqual(len(self.history.list()),1)

    def test_trashed_search_cannot_resume_or_recover_until_restored(self):
        hid=self.create_history();payload={'input':hid,'profile':self.store.get('profile')['active'],'settings':self.store.settings()}
        with self.store.db() as c:
            job=c.execute("INSERT INTO runs(kind,status,started_at,argument) VALUES('history_search','interrupted',?,?)",(now(),encode(payload))).lastrowid
        self.service.set_deleted('histories',hid,True)
        with self.assertRaises(AppError):self.service.resume(job)
        self.assertFalse(self.service.lock.locked())
        with patch.object(self.service,'resume') as resume:self.service.recover_interrupted();resume.assert_not_called()
        self.service.set_deleted('histories',hid,False)
        with patch.object(self.service,'_launch') as launch:
            self.service.resume(job);launch.assert_called_once_with(job)
        self.service.lock.release()

    def test_paused_analysis_skips_deleted_and_restored_task_can_retry(self):
        item=self.store.ingest(1,record())['id'];version=self.store.item(item)['current_version']
        payload={'input':None,'profile':self.store.get('profile')['active'],'settings':self.store.settings()}
        with self.store.db() as c:
            job=c.execute("INSERT INTO runs(kind,status,started_at,argument) VALUES('analyze','paused',?,?)",(now(),encode(payload))).lastrowid
            c.execute('INSERT INTO analysis_tasks(run_id,item_id,version_id,profile_version,updated_at) VALUES(?,?,?,?,?)',(job,item,version,1,now()))
        self.service.set_deleted('items',item,True)
        self.service.ai=Mock();self.service.resume(job);self.wait()
        self.service.ai.analyze.assert_not_called();self.assertEqual(self.store.job(job)['queue']['skipped'],1)
        self.service.set_deleted('items',item,False)
        self.assertEqual(self.store.job(job)['queue']['pending'],1)

    def test_old_database_migration_and_restart_preserve_records(self):
        item=self.store.ingest(1,record())['id'];hid=self.create_history()
        self.store.feedback(item,{'notes':'Old note'})
        # Reproduce the pre-trash schema, then upgrade it twice.
        with self.store.db() as c:
            c.execute('ALTER TABLE items DROP COLUMN deleted_at');c.execute('ALTER TABLE histories DROP COLUMN deleted_at')
        upgraded=Store(self.tmp.name);self.assertEqual(upgraded.item(item)['notes'],'Old note')
        self.assertIsNone(upgraded.item(item)['deleted_at']);self.assertEqual(Service(upgraded,Mock()).history.list()[0]['id'],hid)
        upgraded.set_deleted('items',item,True);reopened=Store(self.tmp.name)
        self.assertEqual(reopened.items(),[]);self.assertEqual(reopened.items(deleted=True)[0]['notes'],'Old note')


class TrashAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name);self.server=make_server(self.app,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.app.port)

    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def fetch(self,path,body=None,token=True):
        headers={'Content-Type':'application/json'}
        if token:headers['X-Academic-Token']=self.app.csrf
        request=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(request,timeout=4) as response:return response.read().decode('utf-8-sig')

    def test_item_endpoints_csrf_exports_and_restore(self):
        item=self.app.store.ingest(1,record())['id'];path=f'/api/items/{item}'
        with self.assertRaises(urllib.error.HTTPError) as e:self.fetch(path+'/delete',{},False)
        self.assertEqual(e.exception.code,403)
        self.fetch(path+'/delete',{});self.fetch(path+'/delete',{})
        self.assertEqual(json.loads(self.fetch('/api/items')),[])
        self.assertEqual(json.loads(self.fetch('/api/items?deleted=1'))[0]['id'],item)
        self.assertEqual(self.fetch('/api/export'),'')
        self.assertNotIn(record()['title'],self.fetch('/api/export?format=csv'))
        with self.assertRaises(urllib.error.HTTPError) as e:self.fetch(path)
        self.assertEqual(e.exception.code,404)
        self.fetch(path+'/restore',{});self.assertEqual(json.loads(self.fetch(path))['id'],item)
        self.assertEqual(json.loads(self.fetch('/api/items?deleted=1')),[])

    def test_history_endpoints_and_active_job_conflict(self):
        h=self.app.service.history.save({'prompt':'History of measurement'})['id'];path=f'/api/histories/{h}'
        self.app.service.lock.acquire()
        try:
            with self.assertRaises(urllib.error.HTTPError) as e:self.fetch(path+'/delete',{})
            self.assertEqual(e.exception.code,409)
        finally:self.app.service.lock.release()
        self.fetch(path+'/delete',{});self.assertEqual(json.loads(self.fetch('/api/histories')),[])
        self.assertEqual(json.loads(self.fetch('/api/histories?deleted=1'))[0]['id'],h)
        for suffix in ('','/papers','/export'):
            with self.assertRaises(urllib.error.HTTPError) as e:self.fetch(path+suffix)
            self.assertEqual(e.exception.code,404)
        self.fetch(path+'/restore',{});self.assertEqual(json.loads(self.fetch(path))['id'],h)
        with self.assertRaises(urllib.error.HTTPError) as e:self.fetch('/api/items/999999/delete',{})
        self.assertEqual(e.exception.code,404)


if __name__=='__main__':unittest.main()
