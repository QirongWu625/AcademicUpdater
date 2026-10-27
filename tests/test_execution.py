import copy,datetime as dt,json,tempfile,threading,time,unittest
from unittest.mock import Mock,patch
from concurrent.futures import ThreadPoolExecutor
from academic_updater.storage import Store,encode,now
from academic_updater.service import Service
from academic_updater.network import AppError
from academic_updater.ai import AI,PROFILE_SCHEMA
from test_core import record,scope
from test_history import ControlledAI,history_record,answer
from test_upgrade import save_analysis,result


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name)
        p=self.store.save_profile({'revision':0,'prompt':'Quantum sensing','exclude':'Marketing'})
        self.store.apply_profile(p['revision'],scope());self.store.put('settings',{**self.store.settings(),'model':'test-model','ai_concurrency':3})
        self.ai=ControlledAI();self.service=Service(self.store,self.ai)
    def tearDown(self):
        self.service.stop.set();self.wait();self.temp.cleanup()
    def wait(self):
        end=time.monotonic()+10
        while self.service.lock.locked() and time.monotonic()<end:time.sleep(.01)
        self.assertFalse(self.service.lock.locked())
    def add(self,n,saved=False):
        i=self.store.ingest(1,history_record(n))['id']
        if saved:self.store.feedback(i,{'saved':True})
        return i
    def history(self):
        return self.service.history.save({'prompt':'Quantum measurement history','scope':{'field_en':'Quantum measurement','queries':['quantum measurement']},'config':{'sources':['crossref'],'limit':100,'discovery_mode':'all'}})['id']
    def test_history_and_daily_collection_run_together_and_duplicate_is_rejected(self):
        started=threading.Event();release=threading.Event();hid=self.history()
        def page(*args):started.set();release.wait(4);return [],{'position':0,'total':0,'done':True}
        with patch('academic_updater.history.historical_page',side_effect=page),patch('academic_updater.service.collect',return_value=([],False)):
            history_job=self.service.start_job('history_search',hid);self.assertTrue(started.wait(2))
            with self.assertRaises(AppError):self.service.start_job('history_search',hid)
            requested=self.service.collect_updates();daily=requested['job_id'];self.assertFalse(requested['already_running'])
            end=time.monotonic()+3
            while self.store.job(daily)['status']=='running' and time.monotonic()<end:time.sleep(.02)
            self.assertEqual(self.store.job(daily)['status'],'complete');self.assertEqual(self.store.job(history_job)['status'],'running')
            release.set();self.wait()
    def test_simultaneous_collection_clicks_share_one_active_run(self):
        started=threading.Event();release=threading.Event()
        def collect(*args):started.set();release.wait(5);return [],False
        with patch('academic_updater.service.collect',side_effect=collect):
            try:
                with ThreadPoolExecutor(max_workers=8) as pool:requests=list(pool.map(lambda _:self.service.collect_updates(),range(8)))
                self.assertTrue(started.wait(2));self.assertEqual(len({r['job_id'] for r in requests}),1)
                self.assertEqual(sum(not r['already_running'] for r in requests),1)
                with self.store.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM runs WHERE kind='collect'").fetchone()[0],1)
            finally:release.set();self.wait()

    def test_collect_click_reuses_scheduled_run_and_allows_a_new_day(self):
        started=threading.Event();release=threading.Event()
        def collect(*args):started.set();release.wait(5);return [],False
        with patch('academic_updater.service.collect',side_effect=collect),patch.object(self.service,'local_day',return_value='2026-10-27'):
            try:
                old=self.service.start_job('collect',{'day':'2026-10-26'});self.assertTrue(started.wait(2))
                self.service.schedule_tick(dt.datetime(2026,10,27,5,tzinfo=dt.timezone.utc))
                requested=self.service.collect_updates();self.assertTrue(requested['already_running']);self.assertNotEqual(requested['job_id'],old)
                with self.store.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM runs WHERE kind='collect'").fetchone()[0],2)
            finally:release.set();self.wait()
    def test_daily_paper_assessment_is_parallel_and_globally_bounded(self):
        ids=[self.add(i) for i in range(1,8)];started=threading.Event();release=threading.Event();guard=threading.Lock();active=0;maximum=0;seen=[]
        def analyze(item_id,**kw):
            nonlocal active,maximum
            with guard:
                active+=1;maximum=max(maximum,active);seen.append(item_id)
                if active==3:started.set()
            release.wait(4)
            try:return save_analysis(self.store,item_id,**{k:v for k,v in kw.items() if k!='expected_version'})
            finally:
                with guard:active-=1
        self.ai.analyze=analyze
        a=self.service.start_job('analyze');self.assertTrue(started.wait(2))
        b=self.service.start_job('item_analysis',ids[-1]);self.assertLessEqual(self.service.ai_limiter.state()['active'],3)
        release.set();self.wait()
        self.assertEqual(maximum,3);self.assertEqual(self.store.job(a)['status'],'complete');self.assertEqual(self.store.job(b)['status'],'complete')
        self.assertEqual(len(self.store.pending_items(1)),0)
    def test_pause_one_task_does_not_cancel_other_task(self):
        started=threading.Event();release=threading.Event();hid=self.history()
        def page(*args):started.set();release.wait(3);return [history_record(1)],{'position':1,'done':True,'total':1}
        with patch('academic_updater.history.historical_page',side_effect=page),patch('academic_updater.service.collect',return_value=([],False)):
            a=self.service.start_job('history_search',hid);self.assertTrue(started.wait(2));self.service.pause(a)
            b=self.service.start_job('collect');release.set();self.wait()
        self.assertEqual(self.store.job(a)['status'],'paused');self.assertEqual(self.store.job(b)['status'],'complete')

    def test_live_concurrency_increases_and_reduction_drains_existing_requests(self):
        ids=[self.add(i) for i in range(1,7)];gates={i:threading.Event() for i in ids};seen=[];condition=threading.Condition()
        self.service.save_settings({'ai_concurrency':1})
        def analyze(item_id,**kw):
            with condition:seen.append(item_id);condition.notify_all()
            gates[item_id].wait(20)
            return save_analysis(self.store,item_id,profile=kw['profile'],settings=kw['settings'])
        def wait_started(count):
            with condition:self.assertTrue(condition.wait_for(lambda:len(seen)>=count,10))
        self.ai.analyze=analyze
        try:
            job=self.service.start_job('analyze');wait_started(1)
            self.service.save_settings({'ai_concurrency':4});wait_started(4)
            self.assertEqual(self.service.ai_limiter.state()['by_job'][job],4)
            self.service.save_settings({'ai_concurrency':1})
            self.assertEqual(self.service.ai_limiter.state()['active'],4)
            for item in seen[:3]:gates[item].set()
            end=time.monotonic()+10
            while self.service.ai_limiter.state()['active']>1 and time.monotonic()<end:time.sleep(.02)
            self.assertEqual(self.service.ai_limiter.state()['active'],1);self.assertEqual(len(seen),4)
            gates[seen[3]].set();wait_started(5)
            self.assertEqual(self.service.ai_limiter.state()['active'],1);self.assertEqual(len(seen),5)
        finally:
            for gate in gates.values():gate.set()
            self.wait()
        self.assertEqual(self.store.job(job)['status'],'complete');self.assertEqual(len(set(seen)),6)

    def test_parallel_limit_validation_preserves_previous_setting(self):
        for invalid in (0,65,'invalid'):
            with self.assertRaises(AppError):self.service.save_settings({'ai_concurrency':invalid})
            self.assertEqual(self.store.settings()['ai_concurrency'],3)
    def test_history_batches_overlap_and_saved_assessments_are_not_repeated(self):
        hid=self.history();started=threading.Event();release=threading.Event();guard=threading.Lock();active=0;maximum=0;seen=[]
        original=self.ai.generate
        def generate(task,instructions,payload,spec,settings=None):
            nonlocal active,maximum
            if task!='history_papers':return original(task,instructions,payload,spec,settings)
            with guard:
                active+=1;maximum=max(maximum,active);seen.extend(p['id'] for p in payload['papers'])
                if active==3:started.set()
            release.wait(15)
            with guard:active-=1
            return {'papers':[answer(p) for p in payload['papers']]}
        self.ai.generate=generate
        with patch('academic_updater.history.historical_page',return_value=([history_record(i) for i in range(1,32)],{'position':31,'done':True,'total':31})):
            job=self.service.start_job('history_search',hid)
            # Ingestion writes all 31 records before assessment begins. Allow
            # slower Windows disks without relaxing the three-worker assertion.
            try:self.assertTrue(started.wait(10))
            finally:release.set();self.wait()
        self.assertEqual(maximum,3);self.assertEqual(len(seen),31);self.assertEqual(len(set(seen)),31)
        self.assertEqual(self.store.job(job)['status'],'complete');self.assertEqual(self.service.history.get(hid,False)['counts']['completed'],31)
    def test_scheduler_catches_up_while_history_and_old_pauses_exist(self):
        current=dt.datetime(2026,10,27,5,tzinfo=dt.timezone.utc)
        with self.store.db() as c:c.execute("INSERT INTO runs(kind,status,started_at,error) VALUES('analyze','paused',?,'paused_by_user')",(now(),))
        hid=self.history();release=threading.Event();started=threading.Event()
        def page(*args):started.set();release.wait(4);return [],{'position':0,'done':True,'total':0}
        with patch('academic_updater.history.historical_page',side_effect=page),patch('academic_updater.service.collect',return_value=([],False)):
            self.service.start_job('history_search',hid);self.assertTrue(started.wait(2));self.service.schedule_tick(current);self.service.schedule_tick(current)
            release.set();self.wait()
        with self.store.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM runs WHERE kind='collect'").fetchone()[0],1)
        self.assertEqual(self.store.get('scheduled_day'),'2026-10-27')
    def test_all_interrupted_jobs_recover_but_manual_pauses_do_not(self):
        ids=[];hid=self.history()
        with self.store.db() as c:
            for kind,progress in [('analyze',{}),('history_search',{}),('collect',{'pause_requested':True})]:
                argument={'input':hid if kind=='history_search' else None,'profile':self.store.get('profile')['active'],'settings':self.store.settings()}
                ids.append(c.execute("INSERT INTO runs(kind,status,started_at,argument,progress) VALUES(?,'interrupted',?,?,?)",(kind,now(),encode(argument),encode(progress))).lastrowid)
        with patch.object(self.service,'resume') as resume:self.service.recover_interrupted();self.assertEqual([c.args[0] for c in resume.call_args_list],ids[:2])
        self.assertEqual(self.store.job(ids[2])['status'],'paused')
    def test_transient_request_retries_then_saves_once(self):
        item=self.add(1);calls=[]
        def analyze(item_id,**kw):
            calls.append(item_id)
            if len(calls)<3:raise AppError('ai_stream_interrupted')
            return save_analysis(self.store,item_id,profile=kw['profile'],settings=kw['settings'])
        self.ai.analyze=analyze
        with patch.object(self.service,'_wait_retry'):
            job=self.service.start_job('analyze');self.wait()
        self.assertEqual(self.store.job(job)['status'],'complete');self.assertEqual(len(calls),3)
        self.assertEqual(len(self.store.item(item)['analyses']),1)
        self.assertEqual([e['event'] for e in self.store.job(job)['events']],['retry','retry'])
    def test_network_exhaustion_sets_retry_and_auto_resume_finishes_remaining(self):
        item=self.add(1);self.ai.analyze=Mock(side_effect=AppError('network_error'))
        with patch.object(self.service,'_wait_retry'):
            job=self.service.start_job('analyze');self.wait()
        state=self.store.job(job);self.assertEqual(state['status'],'failed');self.assertTrue(state['progress']['retry_at'])
        self.ai.analyze=lambda item_id,**kw:save_analysis(self.store,item_id,profile=kw['profile'],settings=kw['settings'])
        self.service.retry_tick(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1));self.wait()
        self.assertEqual(self.store.job(job)['status'],'complete');self.assertEqual(self.store.job(job)['queue']['completed'],1)
    def test_budget_pause_retries_next_local_day_but_auth_error_does_not(self):
        self.add(1);self.ai.analyze=Mock(side_effect=AppError('daily_ai_limit'))
        job=self.service.start_job('analyze');self.wait();state=self.store.job(job)
        retry=dt.datetime.fromisoformat(state['progress']['retry_at'])
        local=retry+dt.timedelta(hours=self.store.settings()['utc_offset']);self.assertEqual((local.hour,local.minute),(0,0))
        with patch.object(self.service,'resume') as resume:
            self.service.retry_tick(retry-dt.timedelta(seconds=1));resume.assert_not_called()
            self.service.retry_tick(retry);resume.assert_called_once_with(job,automatic=True)
        self.ai.analyze=Mock(side_effect=AppError('sign_in_again'));self.service.resume(job);self.wait()
        self.assertEqual(self.store.job(job)['status'],'paused');self.assertNotIn('retry_at',self.store.job(job)['progress'])
    def test_source_retry_only_refetches_failed_sources(self):
        calls=[]
        def collect(source,*args):
            calls.append(source['id'])
            if source['kind']=='arxiv':raise AppError('network_error')
            return [],False
        with patch('academic_updater.service.collect',side_effect=collect):job=self.service.start_job('collect');self.wait()
        self.assertEqual(self.store.job(job)['status'],'partial')
        with patch('academic_updater.service.collect',return_value=([],False)) as remote:
            self.service.retry_tick(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1));self.wait()
        self.assertEqual(remote.call_count,1);self.assertEqual(remote.call_args.args[0]['kind'],'arxiv');self.assertEqual(self.store.job(job)['status'],'complete')
    def test_scheduler_survives_unexpected_exception(self):
        count=[]
        def tick():
            count.append(1)
            if len(count)==1:raise RuntimeError('temporary failure')
            self.service.stop.set()
        with patch.object(self.service,'schedule_tick',side_effect=tick),patch.object(self.service.stop,'wait'):
            self.service.scheduler()
        self.assertEqual(len(count),2);self.assertIsNone(self.store.get('scheduler_status')['error'])

    def test_same_paper_and_scope_share_one_ai_result_across_jobs(self):
        item=self.add(1);started=threading.Event();release=threading.Event();real=AI(self.store,Mock(),Mock());self.service.ai=real
        def generate(*args,**kw):started.set();release.wait(3);return result()
        with patch.object(real,'generate',side_effect=generate) as call:
            a=self.service.start_job('analyze');self.assertTrue(started.wait(2));b=self.service.start_job('item_analysis',item)
            release.set();self.wait();self.assertEqual(call.call_count,1)
        self.assertEqual(self.store.job(a)['status'],'complete');self.assertEqual(self.store.job(b)['status'],'complete')

    def test_parallel_requests_cannot_exceed_daily_budget(self):
        self.store.put('settings',{**self.store.settings(),'daily_ai_limit':1})
        def reserve(_):
            try:return self.store.reserve_ai('test')
            except AppError as e:return e.code
        with ThreadPoolExecutor(max_workers=8) as pool:out=list(pool.map(reserve,range(16)))
        self.assertEqual(sum(isinstance(x,int) for x in out),1);self.assertEqual(out.count('daily_ai_limit'),15)

    def test_next_day_collection_is_not_blocked_by_previous_day_analysis(self):
        item=self.add(1);started=threading.Event();release=threading.Event()
        def analyze(item_id,**kw):started.set();release.wait(4);return save_analysis(self.store,item_id,profile=kw['profile'],settings=kw['settings'])
        self.ai.analyze=analyze
        with patch('academic_updater.service.collect',return_value=([],False)):
            old=self.service.start_job('collect',{'day':'2026-10-26'});self.assertTrue(started.wait(2))
            self.service.schedule_tick(dt.datetime(2026,10,27,5,tzinfo=dt.timezone.utc))
            with self.store.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM runs WHERE kind='collect' AND status='running'").fetchone()[0],2)
            release.set();self.wait()


class SavedLearningTests(unittest.TestCase):
    setUp=ExecutionTests.setUp
    tearDown=ExecutionTests.tearDown
    wait=ExecutionTests.wait
    add=ExecutionTests.add
    # Keep these tests independent of network and provider credentials.
    def run_collect(self):
        with patch('academic_updater.service.collect',return_value=([],False)):
            job=self.service.start_job('collect');self.wait()
        return self.store.job(job)
    def test_saved_add_remove_and_no_change(self):
        a=self.add(1,True);b=self.add(2,True);base=copy.deepcopy(scope());calls=[]
        def generate(task,instructions,payload,spec,settings=None):
            calls.append(payload);result=copy.deepcopy(base);result['question_en']='Adapted to '+str(payload['current_saved_count']);return result
        self.ai.generate=generate;self.ai.analyze=lambda item_id,**kw:save_analysis(self.store,item_id,profile=kw['profile'],settings=kw['settings'])
        self.run_collect();p=self.store.get('profile');self.assertEqual(len(calls),1);self.assertEqual(p['active']['version'],2)
        self.assertEqual(p['prompt'],'Quantum sensing');self.assertEqual(p['exclude'],'Marketing');self.assertEqual(p['active']['base_understanding'],base)
        self.run_collect();self.assertEqual(len(calls),1)
        self.store.feedback(a,{'saved':False});self.run_collect();self.assertEqual(len(calls),2)
        self.assertEqual([i['id'] for i in calls[-1]['current_saved_papers']],[b]);self.assertEqual(calls[-1]['original_scope'],base)
        self.store.feedback(b,{'saved':False});self.run_collect();self.assertEqual(len(calls),2);self.assertEqual(self.store.get('profile')['active']['understanding'],base)
    def test_empty_initial_set_uses_no_ai_and_notes_do_not_trigger_learning(self):
        a=self.add(1);self.ai.analyze=lambda item_id,**kw:save_analysis(self.store,item_id,profile=kw['profile'],settings=kw['settings'])
        with patch.object(self.ai,'generate') as generate:self.run_collect();self.store.feedback(a,{'notes':'note'});self.run_collect();generate.assert_not_called()
        self.assertEqual(self.store.get('profile')['active']['version'],1)
    def test_deleting_and_restoring_saved_papers_changes_learning_snapshot(self):
        a=self.add(1,True);before=self.store.saved_scope_snapshot();self.service.set_deleted('items',a,True)
        deleted=self.store.saved_scope_snapshot();self.assertNotEqual(before['fingerprint'],deleted['fingerprint']);self.assertEqual(deleted['count'],0)
        self.service.set_deleted('items',a,False);self.assertEqual(self.store.saved_scope_snapshot()['fingerprint'],before['fingerprint'])
    def test_stale_saved_set_cannot_overwrite_scope(self):
        a=self.add(1,True);snapshot=self.store.saved_scope_snapshot();self.store.feedback(a,{'saved':False})
        with self.assertRaises(AppError):self.store.apply_saved_scope(snapshot,scope())
        self.assertEqual(self.store.get('profile')['active']['version'],1)
    def test_unapplied_draft_survives_learning(self):
        self.add(1,True);snapshot=self.store.saved_scope_snapshot();self.store.save_profile({'revision':1,'prompt':'My new unfinished prompt'})
        changed=scope();changed['question_en']='Updated evidence';self.store.apply_saved_scope(snapshot,changed)
        p=self.store.get('profile');self.assertEqual(p['prompt'],'My new unfinished prompt');self.assertEqual(p['active']['prompt'],'Quantum sensing')
        self.assertEqual(p['understanding'],scope());self.assertEqual(p['active']['understanding'],changed)
    def test_learning_failure_still_collects_and_does_not_mark_set_current(self):
        self.add(1,True);self.ai.generate=Mock(side_effect=AppError('sign_in_again'));self.ai.analyze=Mock(side_effect=AppError('sign_in_again'))
        with patch('academic_updater.service.collect',return_value=([],False)) as collect:
            job=self.service.start_job('collect');self.wait()
        self.assertEqual(collect.call_count,3);self.assertEqual(self.store.job(job)['progress']['profile_learning']['status'],'deferred');self.assertTrue(self.store.saved_scope_snapshot()['changed'])


if __name__=='__main__':unittest.main()
