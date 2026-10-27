import json,threading,time,unittest
from unittest.mock import patch
from academic_updater import __version__
import test_trash


class CollectAPITests(unittest.TestCase):
    setUp=test_trash.TrashAPITests.setUp
    tearDown=test_trash.TrashAPITests.tearDown
    fetch=test_trash.TrashAPITests.fetch

    def test_repeat_collect_returns_existing_task_over_http(self):
        started=threading.Event();release=threading.Event()
        def collect(*args):started.set();release.wait(5)
        with patch.object(self.app.service,'_collect',side_effect=collect):
            try:
                first=json.loads(self.fetch('/api/collect',{}));self.assertTrue(started.wait(2))
                second=json.loads(self.fetch('/api/collect',{}))
                self.assertEqual(first['job_id'],second['job_id']);self.assertFalse(first['already_running']);self.assertTrue(second['already_running'])
            finally:
                release.set();end=time.monotonic()+5
                while self.app.service.lock.locked() and time.monotonic()<end:time.sleep(.01)
                self.assertFalse(self.app.service.lock.locked())

    def test_bootstrap_day_and_rendered_page_version(self):
        bootstrap=json.loads(self.fetch('/api/bootstrap'));self.assertEqual(bootstrap['local_day'],self.app.service.local_day())
        html=self.fetch('/');self.assertIn('name="academic-version" content="'+__version__+'"',html);self.assertNotIn('__APP_VERSION__',html)

    def test_reference_if_provenance_survives_csv_export(self):
        import csv,io
        from test_core import record
        from test_journal_reference import reference
        item=self.app.store.ingest(1,record(doi='10.1234/reference-export',external_id='reference-export',journal='Example Journal',issns=['1234-567X'],venue_type='journal'))['id']
        self.app.store.save_metrics([{**reference(),'issns':['1234-567X'],'verification':'third_party'}],automatic=True)
        rows=list(csv.DictReader(io.StringIO(self.fetch('/api/export?format=csv').lstrip('\ufeff'))))
        row=next(r for r in rows if int(r['id'])==item)
        self.assertEqual(row['if_status'],'reference');self.assertEqual(row['if_year'],'2025');self.assertEqual(row['if_source'],'Bioxbio')

    def test_metrics_refresh_returns_existing_run_without_resetting_failures(self):
        with self.app.store.db() as c:c.execute("INSERT INTO journal_lookups(journal_key,journal,updated_at) VALUES('example','Example','2026-10-27')")
        started=threading.Event();release=threading.Event()
        def run(*args):started.set();release.wait(5);return {}
        with patch.object(self.app.service.journals,'run',side_effect=run):
            try:
                first=json.loads(self.fetch('/api/metrics/refresh',{}));self.assertTrue(started.wait(2))
                with self.app.store.db() as c:c.execute("UPDATE journal_lookups SET status='error',error='metric_not_found',retry_at='2099'")
                second=json.loads(self.fetch('/api/metrics/refresh',{}))
                self.assertEqual(first['job_id'],second['job_id']);self.assertTrue(second['already_running'])
                self.assertEqual(json.loads(self.fetch('/api/bootstrap'))['journal_metrics_status'],{'error':1})
            finally:
                release.set();end=time.monotonic()+5
                while self.app.service.lock.locked() and time.monotonic()<end:time.sleep(.01)


if __name__=='__main__':unittest.main()
