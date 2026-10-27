import copy
import io
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch
from academic_updater.storage import Store,now,encode
from academic_updater.ai import AI,ANALYSIS_SCHEMA,PROFILE_SCHEMA,model_efforts
from academic_updater.metadata import bibliography,parse_metrics_csv
from academic_updater.network import AppError
from academic_updater.service import Service
from test_core import record,scope

def result(relevance='high'):
    r={k:[] if v['type']=='array' else '' for k,v in ANALYSIS_SCHEMA['properties'].items()}
    r.update(relevance=relevance,summary_en='Supported summary',summary_zh='有依据的摘要')
    return r

def save_analysis(store,item_id,relevance='high',profile=None,settings=None):
    item=store.item(item_id);profile=profile or store.get('profile')['active'];settings=settings or store.settings()
    with store.db() as c:c.execute('INSERT OR REPLACE INTO analyses(item_id,version_id,profile_version,provider,model,reasoning_effort,result,created_at) VALUES(?,?,?,?,?,?,?,?)',(item_id,item['current_version'],profile['version'],settings['provider'],settings['model'],settings.get('reasoning_effort','default'),encode(result(relevance)),now()))
    return result(relevance)

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name)
        p=self.store.save_profile({'revision':0,'prompt':'Quantum sensing.'});self.store.apply_profile(p['revision'],scope())
    def tearDown(self):self.temp.cleanup()
    def add(self,n,journal='Journal Z',author='Zeta',kind='paper',**extra):
        return self.store.ingest(1,record(title=f'Paper {n}',doi=f'10.1234/{n}',external_id=str(n),url=f'https://example.org/{n}',kind=kind,authors=[author+' Researcher'],raw_metadata={'container-title':[journal],'type':'journal-article','author':[{'family':author,'given':'Researcher'}],'ISSN':['1234-5678']},**extra))['id']

    def test_old_database_migrates_without_losing_records_or_analysis(self):
        item=self.add(1,'Journal &amp; Results','Anderson');self.store.feedback(item,{'notes':'Important 中文 note','saved':True,'is_read':True});save_analysis(self.store,item)
        old=self.store.item(item)
        with self.store.db() as c:
            c.execute("DELETE FROM kv WHERE key='bibliography_migrated'")
            for key in ('journal','journal_key','issns','venue_type','author_sort'):c.execute('ALTER TABLE items DROP COLUMN '+key)
            c.execute('ALTER TABLE analyses RENAME TO modern_analyses')
            c.execute('CREATE TABLE analyses(id INTEGER PRIMARY KEY,item_id INTEGER,version_id INTEGER,profile_version INTEGER,provider TEXT,model TEXT,result TEXT,created_at TEXT,UNIQUE(item_id,version_id,profile_version,provider,model))')
            c.execute('INSERT INTO analyses SELECT id,item_id,version_id,profile_version,provider,model,result,created_at FROM modern_analyses');c.execute('DROP TABLE modern_analyses')
        migrated=Store(self.temp.name);new=migrated.item(item)
        for key in ('id','title','notes','saved','is_read','current_version'):self.assertEqual(new[key],old[key])
        self.assertEqual(new['journal'],'Journal & Results');self.assertEqual(new['author_sort'],'anderson researcher');self.assertEqual(new['analyses'][0]['reasoning_effort'],'default')
        self.assertEqual(migrated.stats()['total'],1);self.assertEqual(migrated.stats()['pending'],0)
        self.assertEqual(Store(self.temp.name).item(item)['analyses'],new['analyses'])

    def test_sort_is_global_before_limit_and_missing_values_last(self):
        first=self.add(1,'A Journal','Alpha');second=self.add(2,'Z Journal','Zeta');third=self.add(3,'B Journal','Beta')
        save_analysis(self.store,first,'high');save_analysis(self.store,second,'low');save_analysis(self.store,third,'medium')
        self.assertEqual([i['id'] for i in self.store.items(limit=2,sort='relevance')],[first,third])
        self.assertEqual([i['id'] for i in self.store.items(sort='author',direction='asc')],[first,third,second])
        self.assertEqual([i['id'] for i in self.store.items(sort='journal',direction='desc')],[second,third,first])
        self.assertEqual(self.store.items(query='Alpha')[0]['id'],first)
        self.assertEqual(self.store.items(query='A Journal')[0]['id'],first)

    def test_metrics_apply_to_old_and_new_records_with_year_and_source(self):
        item=self.add(1,'Journal Z')
        self.store.save_metrics([{'journal':'Journal Z','year':2024,'impact_factor':'5.4','source':'Publisher report','source_url':'https://example.org/metrics'}])
        self.assertEqual(self.store.item(item)['impact_factor'],5.4)
        other=self.add(2,'Journal Z');self.assertEqual(self.store.item(other)['if_year'],2024)
        self.store.save_metrics([{'journal':'Journal Z','year':2025,'impact_factor':'0','source':'JCR export'}])
        i=self.store.item(item);self.assertEqual(i['impact_factor'],0);self.assertEqual(i['if_source'],'JCR export');self.assertEqual(i['if_status'],'provided')

    def test_metrics_import_rejects_incomplete_or_nonfinite_values_atomically(self):
        for csv in ['journal,impact_factor\nJournal,5','journal,year,impact_factor,source\nJournal,2025,NaN,Report','journal,year,impact_factor,source\nJournal,2025,5,']:
            with self.assertRaises(AppError):self.store.save_metrics(parse_metrics_csv(csv))
        self.assertEqual(self.store.metrics(),[])
        rows=parse_metrics_csv('journal,year,impact_factor,source,issns\nJournal Z,2025,4.3,Publisher,1234-5678')
        self.assertEqual(self.store.save_metrics(rows),1)

    def test_preprint_does_not_receive_journal_if(self):
        i=self.store.ingest(2,record(doi='',arxiv_id='2401.12345',venue_type='preprint',journal='arXiv'))['id']
        self.store.save_metrics([{'journal':'arXiv','year':2025,'impact_factor':5,'source':'Test'}])
        self.assertEqual(self.store.item(i)['if_status'],'not_applicable');self.assertIsNone(self.store.item(i)['impact_factor'])

    def test_digest_reranks_after_new_analyses(self):
        first=self.add(1);second=self.add(2);service=Service(self.store,Mock());service.digest()
        save_analysis(self.store,first,'high');save_analysis(self.store,second,'medium')
        self.assertEqual(service.digest()['ids'],[first,second])

    def test_effort_transmitted_and_default_omitted(self):
        vault=Mock();vault.get.return_value=None;ai=AI(self.store,vault,Mock());settings={**self.store.settings(),'model':'gpt-6-astra','reasoning_effort':'xhigh'}
        with patch.object(ai,'credentials',return_value=(settings,'test-token')),patch('academic_updater.ai.request') as request,patch('academic_updater.ai.parse_stream',return_value=encode(scope())):
            ai.generate('profile','Task',{},PROFILE_SCHEMA)
            body=json.loads(request.call_args.kwargs['data']);self.assertEqual(body['reasoning'],{'effort':'xhigh'})
            settings['reasoning_effort']='default';ai.generate('profile','Task',{},PROFILE_SCHEMA)
            self.assertNotIn('reasoning',json.loads(request.call_args.kwargs['data']))

    def test_invalid_effort_rejected_before_network_request(self):
        vault=Mock();vault.get.return_value=None;ai=AI(self.store,vault,Mock());settings={**self.store.settings(),'model':'gpt-6-astra','reasoning_effort':'none'}
        with patch.object(ai,'credentials',return_value=(settings,'test-token')),patch('academic_updater.ai.request') as request:
            with self.assertRaises(AppError):ai.generate('profile','Task',{},PROFILE_SCHEMA)
            request.assert_not_called()

    def test_catalog_controls_supported_levels(self):
        self.assertEqual(model_efforts('gpt-6-astra',{'supported_reasoning_levels':[{'effort':'high'},{'effort':'xhigh'}]}),['high','xhigh'])
        self.assertEqual(model_efforts('gpt-6-astra',{'supported_reasoning_levels':[]}),[])
        self.assertEqual(model_efforts('unknown-model'),[])

    def test_effort_is_part_of_analysis_cache(self):
        item=self.add(1);vault=Mock();vault.get.return_value=None;ai=AI(self.store,vault,Mock());settings={**self.store.settings(),'model':'gpt-6-astra','reasoning_effort':'high'}
        with patch.object(ai,'generate',return_value=result()) as generate:
            ai.analyze(item,settings=settings);ai.analyze(item,settings=settings)
            settings['reasoning_effort']='xhigh';ai.analyze(item,settings=settings)
            self.assertEqual(generate.call_count,2)
        self.assertEqual(len(self.store.item(item)['analyses']),2)

class QueueTests(unittest.TestCase):
    setUp=UpgradeTests.setUp
    tearDown=UpgradeTests.tearDown
    add=UpgradeTests.add
    def wait(self,service):
        end=time.monotonic()+6
        while service.lock.locked() and time.monotonic()<end:time.sleep(.02)
        self.assertFalse(service.lock.locked())

    def test_pause_resume_only_processes_remaining_and_keeps_snapshot(self):
        self.store.put('settings',{**self.store.settings(),'ai_concurrency':1})
        for n in range(3):self.add(n)
        started=threading.Event();release=threading.Event();calls=[];profiles=[];service=None
        def analyze(item_id,profile,settings,expected_version):
            calls.append(item_id);profiles.append(profile['version'])
            if len(calls)==1:started.set();release.wait(3)
            return save_analysis(self.store,item_id,profile=profile,settings=settings)
        fake=Mock();fake.analyze.side_effect=analyze;service=Service(self.store,fake)
        job=service.start_job('analyze');self.assertTrue(started.wait(3));service.pause(job);release.set();self.wait(service)
        self.assertEqual(self.store.job(job)['status'],'paused');self.assertEqual(len(calls),1)
        changed=scope();changed['question_en']='A different scope';self.store.apply_profile(1,changed)
        service.resume(job);self.wait(service)
        self.assertEqual(len(calls),3);self.assertEqual(len(set(calls)),3);self.assertEqual(profiles,[1,1,1]);self.assertEqual(self.store.job(job)['status'],'complete')

    def test_legacy_interrupted_collection_resumes_analysis_without_refetch(self):
        a=self.add(1);b=self.add(2);save_analysis(self.store,a)
        with self.store.db() as c:job=c.execute("INSERT INTO runs(kind,status,started_at) VALUES('collect','running','2000-01-01T00:00:00Z')").lastrowid
        reopened=Store(self.temp.name);fake=Mock();fake.analyze.side_effect=lambda item_id,profile,settings,expected_version:save_analysis(reopened,item_id,profile=profile,settings=settings)
        service=Service(reopened,fake)
        with patch('academic_updater.service.collect') as remote:
            service.recover_interrupted();self.wait(service);remote.assert_not_called()
        self.assertEqual(fake.analyze.call_count,1);self.assertEqual(fake.analyze.call_args.args[0],b)
        self.assertEqual(reopened.job(job)['status'],'complete');self.assertEqual(reopened.stats()['pending'],0)

    def test_daily_budget_pause_keeps_pending_tasks(self):
        self.add(1);fake=Mock();fake.analyze.side_effect=AppError('daily_ai_limit');service=Service(self.store,fake)
        job=service.start_job('analyze');self.wait(service);state=self.store.job(job)
        self.assertEqual(state['status'],'paused');self.assertEqual(state['queue']['pending'],1)
        fake.analyze.side_effect=lambda item_id,profile,settings,expected_version:save_analysis(self.store,item_id,profile=profile,settings=settings)
        service.resume(job);self.wait(service);self.assertEqual(self.store.job(job)['status'],'complete')

    def test_restart_recovers_queue_without_repeating_saved_result(self):
        a=self.add(1);b=self.add(2);c=self.add(3)
        profile=self.store.get('profile')['active'];settings={**self.store.settings(),'model':'gpt-6-astra','reasoning_effort':'high'}
        save_analysis(self.store,a,settings=settings);save_analysis(self.store,b,settings=settings)
        payload={'input':None,'profile':profile,'settings':settings}
        with self.store.db() as db:
            job=db.execute("INSERT INTO runs(kind,status,started_at,argument,progress) VALUES('analyze','running',?,?,'{}')",(now(),encode(payload))).lastrowid
            for item,status in [(a,'completed'),(b,'running'),(c,'pending')]:
                db.execute('INSERT INTO analysis_tasks(run_id,item_id,version_id,profile_version,status,updated_at) VALUES(?,?,?,?,?,?)',(job,item,self.store.item(item)['current_version'],profile['version'],status,now()))
        self.store.put('settings',{**settings,'reasoning_effort':'xhigh'})
        reopened=Store(self.temp.name);fake=Mock()
        fake.analyze.side_effect=lambda item_id,profile,settings,expected_version:save_analysis(reopened,item_id,profile=profile,settings=settings)
        service=Service(reopened,fake);service.recover_interrupted();self.wait(service)
        fake.analyze.assert_called_once();self.assertEqual(fake.analyze.call_args.args[0],c)
        self.assertEqual(fake.analyze.call_args.kwargs['settings']['reasoning_effort'],'high')
        self.assertEqual(reopened.job(job)['queue'],{'total':3,'completed':3})

    def test_relevance_reverse_keeps_unknowns_last(self):
        a=self.add(1);b=self.add(2);c=self.add(3);d=self.add(4)
        save_analysis(self.store,a,'high');save_analysis(self.store,b,'low');save_analysis(self.store,c,'uncertain')
        self.assertEqual([x['id'] for x in self.store.items(sort='relevance',direction='desc')],[b,a,c,d])

if __name__=='__main__':unittest.main()
