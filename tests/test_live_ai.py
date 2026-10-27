import threading,time,unittest
from unittest.mock import patch
import test_execution
from test_history import history_record
from test_upgrade import save_analysis
from academic_updater.network import AppError


class LiveAITests(unittest.TestCase):
    setUp=test_execution.ExecutionTests.setUp
    tearDown=test_execution.ExecutionTests.tearDown
    wait=test_execution.ExecutionTests.wait
    add=test_execution.ExecutionTests.add
    history=test_execution.ExecutionTests.history

    def configure(self,**kw):self.service.save_settings({'ai_concurrency':1,'reasoning_effort':'max',**kw})

    def test_daily_switch_keeps_inflight_and_completed_results_at_original_effort(self):
        self.configure();ids=[self.add(i) for i in (1,2)];started=threading.Event();release=threading.Event();seen=[]
        def analyze(item_id,**kw):
            seen.append((item_id,dict(kw['settings'])))
            if len(seen)==1:started.set();release.wait(15)
            return save_analysis(self.store,item_id,profile=kw['profile'],settings=kw['settings'])
        self.ai.analyze=analyze
        try:
            job=self.service.start_job('analyze');self.assertTrue(started.wait(5))
            self.service.save_settings({'reasoning_effort':'medium'})
            state=self.service.job_ai_state(self.store.job(job))
            self.assertEqual(state['next']['reasoning_effort'],'medium')
            self.assertEqual(state['active'],[{'model':'test-model','reasoning_effort':'max','count':1}])
            self.assertEqual(seen[0][1]['reasoning_effort'],'max')
        finally:release.set();self.wait()
        self.assertEqual([s['reasoning_effort'] for _,s in seen],['max','medium'])
        self.assertEqual({item for item,_ in seen},set(ids))
        for item,settings in seen:self.assertEqual(self.store.item(item)['analyses'][0]['reasoning_effort'],settings['reasoning_effort'])
        self.assertEqual(self.service.job_ai_state(self.store.job(job))['active'],[])
        self.assertEqual(self.store.job(job)['status'],'complete')

    def test_request_waiting_for_slot_uses_new_model_and_effort(self):
        self.configure();a=self.add(1);b=self.add(2);started=threading.Event();release=threading.Event();seen=[]
        def analyze(item_id,**kw):
            seen.append((item_id,dict(kw['settings'])))
            if item_id==a:started.set();release.wait(15)
            return save_analysis(self.store,item_id,profile=kw['profile'],settings=kw['settings'])
        self.ai.analyze=analyze
        try:
            first=self.service.start_job('item_analysis',a);self.assertTrue(started.wait(5))
            second=self.service.start_job('item_analysis',b);end=time.monotonic()+5
            while self.service.ai_limiter.state()['waiting']<1 and time.monotonic()<end:time.sleep(.02)
            self.assertEqual(self.service.ai_limiter.state()['waiting'],1)
            self.service.save_settings({'model':'another-model','reasoning_effort':'medium'})
        finally:release.set();self.wait()
        self.assertEqual([(s['model'],s['reasoning_effort']) for _,s in seen],[('test-model','max'),('another-model','medium')])
        self.assertEqual(self.store.job(first)['status'],'complete');self.assertEqual(self.store.job(second)['status'],'complete')

    def test_retry_resolves_latest_settings_and_cleans_activity(self):
        self.configure();item=self.add(1);seen=[]
        def analyze(item_id,**kw):
            seen.append(kw['settings']['reasoning_effort'])
            if len(seen)==1:raise AppError('ai_stream_interrupted')
            return save_analysis(self.store,item_id,profile=kw['profile'],settings=kw['settings'])
        self.ai.analyze=analyze
        with patch.object(self.service,'_wait_retry',side_effect=lambda *a:self.service.save_settings({'reasoning_effort':'medium'})):
            job=self.service.start_job('analyze');self.wait()
        self.assertEqual(seen,['max','medium']);self.assertEqual(self.service.job_ai_state(self.store.job(job))['active'],[])
        self.assertEqual(self.store.job(job)['status'],'complete')

    def test_history_batches_and_synthesis_switch_without_reclassifying_completed_papers(self):
        self.configure();hid=self.history();started=threading.Event();release=threading.Event();original=self.ai.generate;seen=[]
        def generate(task,instructions,payload,spec,settings=None):
            seen.append((task,settings['reasoning_effort']))
            if task=='history_papers' and len(seen)==1:started.set();release.wait(15)
            return original(task,instructions,payload,spec,settings=settings)
        self.ai.generate=generate
        with patch('academic_updater.history.historical_page',return_value=([history_record(i) for i in range(1,12)],{'position':11,'done':True,'total':11})):
            try:
                job=self.service.start_job('history_search',hid);self.assertTrue(started.wait(10))
                self.service.save_settings({'reasoning_effort':'medium'})
            finally:release.set();self.wait()
        self.assertEqual(seen,[('history_papers','max'),('history_papers','medium'),('history_timeline','medium')])
        h=self.service.history.get(hid);levels=[p['history_analysis']['ai']['reasoning_effort'] for p in h['items']]
        self.assertEqual(levels.count('max'),10);self.assertEqual(levels.count('medium'),1)
        self.assertEqual(h['report']['reasoning_effort'],'medium');self.assertEqual(self.store.job(job)['status'],'complete')

    def test_connection_changes_do_not_redirect_existing_tasks(self):
        self.configure();original=self.store.settings()
        self.service.save_settings({'provider':'api','model':'another-model','reasoning_effort':'medium'})
        self.assertEqual(self.service.request_settings(original),original)
        local={**original,'provider':'local','local_url':'http://127.0.0.1:11434/v1'}
        self.store.put('settings',{**local,'local_url':'http://127.0.0.1:11435/v1','reasoning_effort':'medium'})
        self.assertEqual(self.service.request_settings(local),local)


if __name__=='__main__':unittest.main()
