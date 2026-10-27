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


if __name__=='__main__':unittest.main()
