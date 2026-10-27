import contextlib,json,sqlite3,tempfile,threading,time,unittest,urllib.error
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock,patch
from academic_updater.storage import Store,now,encode
from academic_updater.service import Service
from academic_updater.network import AppError
from test_core import scope,record
from test_upgrade import save_analysis
from test_trash import TrashAPITests

class DataManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.service=Service(self.store,Mock())
        p=self.store.save_profile({'revision':0,'prompt':'Quantum sensing'});self.store.apply_profile(p['revision'],scope())
        self.item=self.store.ingest(1,record(journal='Example Journal',venue_type='journal'))['id'];self.store.feedback(self.item,{'saved':True,'notes':'Keep until cleared'})
        save_analysis(self.store,self.item);self.service.history.save({'prompt':'A saved historical search'})
    def tearDown(self):self.temp.cleanup()

    def test_clear_requires_confirmation_and_inactive_workers(self):
        for value in ('',None,'clear all'):
            with self.assertRaises(AppError):self.service.clear_dataset(value)
        self.service.lock.acquire()
        try:
            with self.assertRaises(AppError):self.service.clear_dataset('CLEAR ALL')
        finally:self.service.lock.release()
        self.assertEqual(self.store.stats()['total'],1)

    def test_backup_failure_aborts_clear(self):
        with patch.object(self.store,'backup',side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):self.service.clear_dataset('CLEAR ALL')
        self.assertEqual(self.store.item(self.item)['notes'],'Keep until cleared')

    def test_removed_integration_keeps_legacy_imported_records(self):
        with self.store.db() as c:source=c.execute("INSERT INTO sources(kind,name) VALUES('scispace_import','Legacy import')").lastrowid
        item=self.store.ingest(source,record(doi='10.1234/legacy',external_id='legacy',title='Previously imported paper'))['id']
        self.store.feedback(item,{'saved':True,'notes':'Keep imported provenance'})
        upgraded=Store(self.temp.name)
        self.assertEqual(upgraded.item(item)['notes'],'Keep imported provenance');self.assertTrue(upgraded.item(item)['saved'])
        self.assertFalse(next(s for s in upgraded.sources() if s['id']==source)['enabled'])

    def test_clear_preserves_configuration_and_usage_with_restorable_unique_backup(self):
        self.store.reserve_ai('test');profile=self.store.get('profile');sources=self.store.sources()
        first=self.store.backup();out=self.service.clear_dataset('CLEAR ALL');second=self.store.directory/'backups'/out['backup']
        self.assertNotEqual(first,second);self.assertEqual(self.store.dataset_counts(),{'items':0,'histories':0,'analyses':0,'journal_metrics':0})
        self.assertEqual(self.store.get('profile'),profile);self.assertFalse(self.store.settings()['schedule_enabled']);self.assertEqual(len(self.store.sources()),len(sources))
        with self.store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM ai_usage').fetchone()[0],1)
        with contextlib.closing(sqlite3.connect(second)) as c:self.assertEqual(c.execute('SELECT notes FROM items').fetchone()[0],'Keep until cleared');self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_unlimited_budget_and_positive_limit_remain_atomic(self):
        self.service.save_settings({'daily_ai_limit':0})
        with self.store.db() as c:c.executemany("INSERT INTO ai_usage(day,task,status,created_at) VALUES(?,'test','completed',?)",[(self.service.local_day(),now())]*501)
        self.store.reserve_ai('unlimited')
        self.service.save_settings({'daily_ai_limit':504})
        def reserve(_):
            try:self.store.reserve_ai('bounded');return True
            except AppError:return False
        with ThreadPoolExecutor(max_workers=8) as pool:self.assertEqual(sum(pool.map(reserve,range(8))),2)

    def test_increased_budget_unblocks_automatic_retry(self):
        progress={'retry_at':'2099-01-01','retry_reason':'daily_ai_limit'}
        with self.store.db() as c:job=c.execute("INSERT INTO runs(kind,status,started_at,error,progress) VALUES('analyze','paused',?,'daily_ai_limit',?)",(now(),encode(progress))).lastrowid
        self.service.save_settings({'daily_ai_limit':0})
        self.assertLessEqual(self.store.job(job)['progress']['retry_at'],now())

    def test_parallel_work_really_exceeds_previous_eight_worker_limit(self):
        self.service.save_settings({'ai_concurrency':16});barrier=threading.Barrier(16);seen=set();guard=threading.Lock()
        def work(n):
            with guard:seen.add(threading.get_ident())
            barrier.wait(timeout=10)
        self.service.parallel_work(None,range(16),work);self.assertEqual(len(seen),16)
        self.service.save_settings({'ai_concurrency':64});self.assertEqual(self.store.settings()['ai_concurrency'],64)
        with self.assertRaises(AppError):self.service.save_settings({'ai_concurrency':65})

class DatasetAPITests(TrashAPITests):
    # Reuse the HTTP fixture without duplicating its unrelated test cases.
    test_item_endpoints_csrf_exports_and_restore=None
    test_history_endpoints_and_active_job_conflict=None
    def test_clear_endpoint_and_removed_integration(self):
        self.app.store.ingest(1,record())
        with self.assertRaises(urllib.error.HTTPError) as e:self.fetch('/api/dataset/clear',{'confirmation':'CLEAR ALL'},False)
        self.assertEqual(e.exception.code,403);self.assertEqual(json.loads(self.fetch('/api/dataset'))['items'],1)
        for path in ('/api/scispace','/scispace.js'):
            with self.assertRaises(urllib.error.HTTPError) as e:self.fetch(path)
            self.assertEqual(e.exception.code,404)
        self.fetch('/api/dataset/clear',{'confirmation':'CLEAR ALL'});self.assertEqual(json.loads(self.fetch('/api/dataset'))['items'],0)
