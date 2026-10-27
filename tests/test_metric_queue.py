import json,tempfile,threading,time,unittest
from unittest.mock import Mock,patch
from academic_updater.storage import Store,now
from academic_updater.service import Service,JobPaused
from academic_updater.network import AppError
from test_journal_lookup import metric

class MetricQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name)
        self.store.put('settings',{**self.store.settings(),'model':'test-model','ai_concurrency':8})
        self.service=Service(self.store,Mock())
    def tearDown(self):
        self.service.stop.set();self.wait();self.temp.cleanup()
    def wait(self):
        end=time.monotonic()+15
        while self.service.lock.locked() and time.monotonic()<end:time.sleep(.01)
        self.assertFalse(self.service.lock.locked())
    def seed(self,n):
        with self.store.db() as c:
            c.executemany('INSERT INTO journal_lookups(journal_key,journal,issns,updated_at) VALUES(?,?,?,?)',[(f'journal {i:02}',f'Journal {i:02}','["1234-5678"]',now()) for i in range(n)])
    def test_68_journals_drain_in_one_automatic_run_without_repeating_failures(self):
        self.seed(68);seen=[];guard=threading.Lock()
        def find(job,settings,journal,issns):
            with guard:seen.append(journal)
            n=int(journal.split()[-1])
            if n%3==1:raise AppError('metric_not_found')
            if n%3==2:raise AppError('publisher_access_denied')
            return {**metric(),'journal':journal,'issns':issns}
        with patch.object(self.service.journals,'find',side_effect=find):
            self.service.metrics_tick();self.wait();self.service.metrics_tick();self.wait()
        self.assertEqual(len(seen),68);self.assertEqual(len(set(seen)),68)
        with self.store.db() as c:runs=c.execute('SELECT id FROM runs').fetchall()
        self.assertEqual(len(runs),1);r=self.store.job(runs[0][0])
        self.assertEqual(r['status'],'complete');self.assertEqual(r['result'],{'found':23,'reference':0,'unavailable':23,'failed':22,'processed':68})
        self.assertEqual(self.store.metric_status(),{'found':23,'unavailable':23,'error':22});self.assertEqual(self.service.journals.pending(),[])

    def test_active_retry_reuses_job_without_resetting_completed_failures(self):
        self.seed(2);entered=threading.Event();release=threading.Event()
        def run(*args):entered.set();release.wait(5);return {}
        with patch.object(self.service.journals,'run',side_effect=run):
            try:
                first=self.service.refresh_metrics();self.assertTrue(entered.wait(2))
                with self.store.db() as c:c.execute("UPDATE journal_lookups SET status='error',error='publisher_access_denied',retry_at='2099' WHERE journal_key='journal 00'")
                second=self.service.refresh_metrics()
                self.assertEqual(first['job_id'],second['job_id']);self.assertTrue(second['already_running'])
                self.assertEqual(self.store.metric_status(),{'pending':1,'error':1})
            finally:release.set();self.wait()

    def test_empty_retry_creates_no_fake_task(self):
        self.assertEqual(self.service.refresh_metrics(),{'job_id':None,'empty':True})
        with self.store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM runs').fetchone()[0],0)

    def test_auth_pause_keeps_waiting_rows_and_blocks_retry_storm(self):
        self.seed(12)
        with patch.object(self.service.journals,'find',side_effect=AppError('ai_not_connected')):
            request=self.service.refresh_metrics();self.wait()
        run=self.store.job(request['job_id']);self.assertEqual(run['status'],'paused');self.assertIn('ai_not_connected',run['error'])
        self.assertEqual(self.store.metric_status(),{'pending':12})
        with patch.object(self.service,'start_job') as start:self.service.metrics_tick();start.assert_not_called()

    def test_manual_pause_and_resume_keep_completed_journals(self):
        self.seed(12);self.store.put('settings',{**self.store.settings(),'ai_concurrency':1});seen=[]
        def find(job,settings,journal,issns):
            seen.append(journal)
            if len(seen)==2:raise JobPaused()
            return {**metric(),'journal':journal,'issns':issns}
        with patch.object(self.service.journals,'find',side_effect=find):
            request=self.service.refresh_metrics();self.wait();job=request['job_id']
            self.assertEqual(self.store.job(job)['status'],'paused');self.assertEqual(self.store.metric_status(),{'found':1,'pending':11})
            self.service.resume(job);self.wait()
        self.assertEqual(seen.count('Journal 00'),1);self.assertEqual(self.store.metric_status(),{'found':12})
        self.assertEqual(self.store.job(job)['result']['processed'],12)

    def test_restart_recovers_inflight_journal_and_preserves_finished_one(self):
        self.seed(2)
        with self.store.db() as c:
            c.execute("UPDATE journal_lookups SET status='running' WHERE journal_key='journal 00'")
            c.execute("UPDATE journal_lookups SET status='found' WHERE journal_key='journal 01'")
        store=Store(self.temp.name);self.assertEqual(store.metric_status(),{'pending':1,'found':1})

    def test_bad_journal_data_does_not_abort_other_journals(self):
        self.seed(12)
        with self.store.db() as c:c.execute("UPDATE journal_lookups SET issns='malformed' WHERE journal_key='journal 00'")
        with patch.object(self.service.journals,'find',side_effect=AppError('metric_not_found')):
            request=self.service.refresh_metrics();self.wait()
        self.assertEqual(self.store.job(request['job_id'])['result']['processed'],12)
        self.assertEqual(self.store.metric_status(),{'error':1,'unavailable':11})

    def test_unrelated_scheduler_failure_does_not_prevent_metrics_start(self):
        with patch.object(self.service,'schedule_tick',side_effect=AppError('research_not_applied')),patch.object(self.service,'recover_interrupted'),patch.object(self.service,'retry_tick'),patch.object(self.service,'metrics_tick',side_effect=self.service.stop.set) as metrics:
            self.service.scheduler();metrics.assert_called_once()
        self.assertEqual(self.store.get('scheduler_status')['error'],'research_not_applied')
