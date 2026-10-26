import copy,json,tempfile,time,unittest,urllib.parse
from unittest.mock import Mock,patch
from academic_updater.storage import Store,encode,now
from academic_updater.service import Service
from academic_updater.history import historical_page,BATCH_SCHEMA
from academic_updater.ai import validate
from academic_updater.network import AppError
from test_core import record,scope

def history_record(n):
    return record(title=f'Paper {n}: measurement method',doi=f'10.1234/history{n}',external_id=f'h{n}',url=f'https://example.org/history{n}',published_at=str(1990+n)+'-01-01',raw_metadata={'container-title':['History Journal'],'type':'journal-article','author':[{'family':'Researcher','given':'A'}]})

def answer(p):
    return {'id':p['id'],'relevance':'high','role':'method','contribution_zh':'摘要报告一种测量方法。','contribution_en':'The abstract reports a measurement method.','reason_zh':'与测量研究相关。','reason_en':'Relevant to measurement research.','evidence_quotes':[p['title']]}

class ControlledAI:
    def __init__(self):self.calls=[]
    def check_effort(self,s):pass
    def generate(self,task,instructions,payload,spec,settings=None):
        self.calls.append((task,copy.deepcopy(settings)))
        if task=='history_scope':return scope()
        if task=='history_papers':return {'papers':[answer(p) for p in payload['papers']]}
        p=payload['papers'][0]
        return {'overview_en':'A chronology of retrieved measurement methods.','overview_zh':'已检索测量方法的发展线索。','limitations_en':'Title and abstract evidence only.','limitations_zh':'仅依据标题与摘要。','milestones':[{'year':p['year'],'title_en':'Measurement methods','title_zh':'测量方法','change_en':'The supplied paper describes measurement.','change_zh':'所提供论文描述了测量方法。','paper_ids':[p['id']]}]}

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.ai=ControlledAI();self.service=Service(self.store,self.ai);self.history=self.service.history
        p=self.store.save_profile({'revision':0,'prompt':'Daily scope'});self.store.apply_profile(p['revision'],scope())
    def tearDown(self):self.temp.cleanup()
    def create(self,analyze=True,sources=None,limit=100):
        return self.history.save({'prompt':'History of measurement methods','scope':{'field_en':'Measurement methods','queries':['measurement methods']},'config':{'sources':sources or ['crossref'],'limit':limit,'analyze':analyze,'discovery_mode':'all'}})['id']
    def wait(self):
        until=time.monotonic()+8
        while self.service.lock.locked() and time.monotonic()<until:time.sleep(.02)
        self.assertFalse(self.service.lock.locked())
    def page(self,*args):return [history_record(1),history_record(2)],{'position':2,'total':2,'done':True,'source_limited':False}
    def search(self,hid):
        with patch('academic_updater.history.historical_page',side_effect=self.page):
            job=self.service.start_job('history_search',hid);self.wait()
        return self.store.job(job)

    def test_saved_scope_is_independent_of_daily_scope(self):
        before=copy.deepcopy(self.store.get('profile'));hid=self.create(False)
        job=self.service.start_job('history_plan',hid);self.wait()
        self.assertEqual(self.store.job(job)['status'],'complete');self.assertEqual(self.history.get(hid)['scope']['field_en'],'Quantum sensing')
        self.assertEqual(self.store.get('profile'),before)
        self.assertEqual(Store(self.temp.name).get('profile'),before)

    def test_search_saves_deduplicates_classifies_and_cites_real_ids(self):
        old=self.store.ingest(1,history_record(1))['id'];self.store.feedback(old,{'notes':'Keep this note','saved':True})
        hid=self.create(sources=['crossref','arxiv']);job=self.search(hid);h=self.history.get(hid)
        self.assertEqual(job['status'],'complete');self.assertEqual(h['counts'],{'completed':2,'total':2});self.assertEqual(self.store.stats()['total'],2)
        self.assertEqual(self.store.item(old)['notes'],'Keep this note');self.assertEqual(self.store.item(old)['saved'],1)
        self.assertEqual(len(h['report']['references']),2);self.assertEqual(h['report']['milestones'][0]['paper_ids'],[old])
        self.assertEqual(self.store.item(old)['analyses'],[])
        self.assertEqual(self.history.papers(hid,{'filter':'relevant'})['total'],2)
        reopened=Service(Store(self.temp.name),self.ai).history.get(hid);self.assertEqual(reopened['report'],h['report'])

    def test_historical_only_papers_do_not_enter_daily_queue_or_digest(self):
        hid=self.create(False);self.search(hid)
        self.assertEqual(self.store.pending_items(1),[]);self.assertEqual(self.service.digest()['ids'],[])
        self.assertEqual(len(self.store.items()),2);self.assertEqual(self.store.items(daily=True),[])
        self.store.ingest(1,history_record(1));self.assertEqual(len(self.store.pending_items(1)),1);self.assertEqual(len(self.store.items(daily=True)),1)

    def test_completed_search_scope_cannot_be_changed(self):
        hid=self.create(False);self.search(hid)
        with self.assertRaises(AppError):self.history.save({'prompt':'Changed','scope':{},'config':{}},hid)
        with self.assertRaises(AppError):self.service.start_job('history_plan',hid)

    def test_pagination_and_cap_have_explicit_coverage(self):
        hid=self.create(False)
        def page(source,query,config,state,size):return [history_record(1)],{'position':100,'cursor':'next','total':900,'done':False}
        with patch('academic_updater.history.historical_page',side_effect=page):job=self.service.start_job('history_search',hid);self.wait()
        self.assertEqual(self.store.job(job)['status'],'partial');h=self.history.get(hid)
        self.assertTrue(h['progress']['streams'][0]['capped']);self.assertEqual(h['progress']['streams'][0]['total'],900)

    def test_resume_retries_failed_source_without_repeating_other_source(self):
        hid=self.create(False,sources=['crossref','arxiv'])
        def page(source,*args):
            if source=='arxiv':raise AppError('network_error')
            return self.page()
        with patch('academic_updater.history.historical_page',side_effect=page):job=self.service.start_job('history_search',hid);self.wait()
        self.assertEqual(self.store.job(job)['status'],'partial')
        with patch('academic_updater.history.historical_page',side_effect=self.page) as remote:self.service.resume(job);self.wait()
        self.assertEqual(remote.call_count,1);self.assertEqual(remote.call_args.args[0],'arxiv');self.assertEqual(self.history.get(hid)['counts']['total'],2)

    def test_invalid_batch_evidence_does_not_save_partial_analysis(self):
        hid=self.create(False);self.search(hid);batch=self.history.get(hid)['items'];bad=[answer(p) for p in batch];bad[1]['evidence_quotes']=['invented evidence']
        with patch.object(self.ai,'generate',return_value={'papers':bad}):
            with self.assertRaises(AppError):self.history.analyze_batch(hid,{},batch,{})
        self.assertEqual(self.history.get(hid)['counts'],{'pending':2,'total':2})
        bad[1]=answer(batch[1]);bad[1]['id']=99999
        with patch.object(self.ai,'generate',return_value={'papers':bad}):
            with self.assertRaises(AppError):self.history.analyze_batch(hid,{},batch,{})

    def test_invalid_timeline_citation_rejected(self):
        hid=self.create();self.search(hid);h=self.history.get(hid);bad=copy.deepcopy(h['report']);bad['milestones'][0]['paper_ids']=[999999]
        self.history.update(hid,report={})
        with patch.object(self.ai,'generate',return_value=bad):
            with self.assertRaises(AppError):self.history.synthesize(h,self.store.settings())
        self.assertEqual(self.history.get(hid)['report'],{})

    def test_budget_pause_resumes_saved_collection_with_original_settings(self):
        hid=self.create();settings={**self.store.settings(),'model':'gpt-6-astra','reasoning_effort':'high'};self.store.put('settings',settings)
        with patch.object(self.ai,'generate',side_effect=AppError('daily_ai_limit')):job=self.search(hid)
        self.assertEqual(job['status'],'paused');self.assertEqual(self.history.get(hid)['counts']['total'],2)
        self.store.put('settings',{**settings,'reasoning_effort':'xhigh'})
        with patch('academic_updater.history.historical_page') as remote:self.service.resume(job['id']);self.wait();remote.assert_not_called()
        self.assertEqual(self.history.get(hid)['status'],'complete');self.assertEqual(self.ai.calls[0][1]['reasoning_effort'],'high')

    def test_restart_resumes_completed_collection_and_skips_saved_classification(self):
        hid=self.create();self.search(hid);h=self.history.get(hid);job=h['job']['id'];calls=len(self.ai.calls)
        with self.store.db() as c:
            c.execute("UPDATE runs SET status='running' WHERE id=?",(job,));c.execute("UPDATE histories SET status='analyzing' WHERE id=?",(hid,))
        self.store=Store(self.temp.name);self.service=Service(self.store,self.ai)
        with patch('academic_updater.history.historical_page') as remote:self.service.recover_interrupted();self.wait();remote.assert_not_called()
        self.assertEqual(len(self.ai.calls),calls);self.assertEqual(self.service.history.get(hid)['status'],'complete')

    def test_unlimited_does_not_stop_at_selected_cap(self):
        hid=self.create(False,limit=0)
        def page(source,query,config,state,size):
            n=state['position'];return [history_record(n+1)],{'position':n+100,'cursor':'next','total':201,'done':n>=200}
        with patch('academic_updater.history.historical_page',side_effect=page) as remote:job=self.service.start_job('history_search',hid);self.wait()
        self.assertEqual(remote.call_count,3);self.assertEqual(self.store.job(job)['status'],'complete')

    def test_query_validation_and_date_range(self):
        for config in [{'year_from':2025,'year_to':1990},{'year_from':'bad'},{'sources':[]},{'limit':-1}]:
            with self.assertRaises(AppError):self.history.save({'prompt':'Area','config':config})

    def test_crossref_uses_publication_years_and_cursor(self):
        message={'items':[{'title':['Paper'],'DOI':'10.1234/a','type':'journal-article'}],'total-results':101,'next-cursor':'opaque'}
        with patch('academic_updater.history.get_json',return_value={'message':message}) as remote:
            rows,state=historical_page('crossref','quantum sensing',{'year_from':1900,'year_to':2000},{'cursor':'saved','position':100})
        q=urllib.parse.parse_qs(urllib.parse.urlsplit(remote.call_args.args[0]).query)
        self.assertEqual(q['cursor'],['saved']);self.assertIn('from-pub-date:1900-01-01',q['filter'][0]);self.assertNotIn('index-date',q['filter'][0]);self.assertEqual(state['position'],101)

    def test_arxiv_search_has_no_recent_window_and_uses_submission_dates(self):
        with patch('academic_updater.history.arxiv_request',return_value=b'x') as remote,patch('academic_updater.history.arxiv_records',return_value=([],0)):
            historical_page('arxiv','quantum sensing',{},{});q=urllib.parse.parse_qs(urllib.parse.urlsplit(remote.call_args.args[0]).query)
            self.assertNotIn('lastUpdatedDate',q['search_query'][0]);self.assertNotIn('submittedDate',q['search_query'][0])
            historical_page('arxiv','quantum sensing',{'year_from':1995,'year_to':2005},{})
            self.assertIn('submittedDate:[199501010000 TO 200512312359]',urllib.parse.parse_qs(urllib.parse.urlsplit(remote.call_args.args[0]).query)['search_query'][0])

    def test_cursor_can_recover_again_after_a_later_pause(self):
        hid=self.create(False);job=self.search(hid)['id']
        for attempt in range(2):
            progress=self.history.get(hid)['progress'];progress['streams'][0].update(done=False,cursor='expired',position=2,restarted=True)
            self.history.update(hid,progress=progress)
            with self.store.db() as c:c.execute("UPDATE runs SET status='paused' WHERE id=?",(job,))
            with patch('academic_updater.history.historical_page',side_effect=[AppError('upstream_http_error','api.crossref.org: HTTP 404'),self.page()]) as remote:
                self.service.resume(job);self.wait()
            self.assertEqual(remote.call_count,2);self.assertEqual(self.store.job(job)['status'],'complete')
            self.assertEqual(self.history.get(hid)['counts']['total'],2)

    def test_years_before_arxiv_return_empty_without_request(self):
        with patch('academic_updater.history.arxiv_request') as remote:
            rows,state=historical_page('arxiv','measurement',{'year_to':1990},{})
        remote.assert_not_called();self.assertEqual(rows,[]);self.assertTrue(state['done'])

    def test_nested_ai_schema_validates_ids_and_enum(self):
        value={'papers':[answer({'id':1,'title':'Source'})]};self.assertEqual(validate(value,BATCH_SCHEMA),value)
        for bad in [True,-1,'1']:
            value['papers'][0]['id']=bad
            with self.assertRaises(AppError):validate(value,BATCH_SCHEMA)

if __name__=='__main__':unittest.main()
