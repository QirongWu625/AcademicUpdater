import copy,json,tempfile,time,unittest,urllib.error,urllib.parse
from unittest.mock import Mock,patch
from academic_updater.scispace import parse_export,research_question
from academic_updater.sources import collect
from academic_updater.storage import Store,encode
from academic_updater.service import Service
from academic_updater.network import AppError
from academic_updater.relevance import require_abstract,SEMANTIC_RELEVANCE
from test_core import record,scope
from test_history import ControlledAI
from test_upgrade import save_analysis
import test_trash


def export(**changes):
    paper={'title':'Individualized image-guided targeting','doi':'10.1234/example','abstract':'MRI guidance improves coil positioning.','date':'2004-03-01',
           'journal':{'display_name':'Imported Journal','issn':'1234-5678'},'authors':{'data':[{'display_name':'A. Researcher'},{'display_name':'B. Scientist'}]},
           'unique_id':'test-001','full_slug':'individualized-image-guided-targeting-test-001','metrics':{'citations':{'total':None}}}
    paper.update(changes)
    return json.dumps({'searchTerm':'Which methods guide individual coil targeting?','papers':[paper]})


class ExportTests(unittest.TestCase):
    def test_native_json_metadata_and_missing_citations(self):
        p=parse_export(export())['records'][0]
        self.assertEqual(p['journal'],'Imported Journal');self.assertEqual(len(p['authors']),2)
        self.assertEqual(p['url'],'https://doi.org/10.1234/example');self.assertEqual(p['published_at'],'2004-03-01')
        self.assertIsNone(p['raw_metadata']['scispace_citations']);self.assertNotIn('impact_factor',p)
        self.assertEqual(parse_export(export(abstract='',tldr='AI generated claim'))['records'][0]['abstract'],'')
        self.assertEqual(parse_export(export(doi='10.1101/test'))['records'][0]['venue_type'],'preprint')
    def test_csv_ris_and_invalid_dates(self):
        text='Title,DOI,Authors,Journal,Year,Abstract\n"研究, targeting",10.1234/csv,"Smith, A.; Li, B.",Journal,2001,Abstract\n'
        p=parse_export(text)['records'][0];self.assertEqual(p['title'],'研究, targeting');self.assertEqual(p['authors'],['Smith, A.','Li, B.'])
        ris='TY  - JOUR\nTI  - Coil targeting\nAU  - Smith, A.\nAU  - Li, B.\nDO  - 10.1234/ris\nPY  - 1999/03/02\nAB  - First line\ncontinued text\nER  -\n'
        p=parse_export(ris)['records'][0];self.assertEqual(p['abstract'],'First line continued text');self.assertEqual(p['published_at'],'1999-03-02')
        self.assertIsNone(parse_export(export(date='2020-13-45'))['records'][0]['published_at'])
    def test_reject_bad_rows_unsafe_urls_and_bounded_files(self):
        rows=[{'title':'OK','url':'https://example.org/p'},{'title':'Bad','url':'javascript:alert(1)'},{'doi':'10.1234/missing'}]
        p=parse_export(json.dumps(rows));self.assertEqual(len(p['records']),1);self.assertEqual(p['skipped_rows'],[2,3])
        for text in ['x'*180001,'[]','{bad','TY  - JOUR\nTI  - Unterminated',json.dumps(rows[:1]*201)]:
            with self.assertRaises(AppError):parse_export(text)
    def test_question_and_metadata_only_relevance(self):
        question=research_question({'field_en':'MRI-guided stimulation','excluded_en':['animal experiments']},'Personalized targeting',True)
        self.assertIn('foundational',question);self.assertIn('animal experiments',question);self.assertIn('Personalized targeting',question)
        a={'relevance':'high','role':'foundation'};require_abstract(a,' ')
        self.assertEqual(a['relevance'],'uncertain');self.assertEqual(a['role'],'uncertain');self.assertIn('未提供摘要',a['reason_zh'])
        self.assertIn('Equivalent terminology',SEMANTIC_RELEVANCE)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.service=Service(self.store,ControlledAI())
        p=self.store.save_profile({'revision':0,'prompt':'MRI targeting'});self.store.apply_profile(p['revision'],scope())
    def tearDown(self):
        self.service.stop.set()
        end=time.monotonic()+10
        while self.service.lock.locked() and time.monotonic()<end:time.sleep(.02)
        self.tmp.cleanup()
    def history(self,**config):
        return self.service.history.save({'prompt':'History of MRI targeting','scope':{'field_en':'MRI targeting','queries':['MRI targeting']},'config':{'sources':['crossref'],'discovery_mode':'all',**config}})['id']
    def test_preview_does_not_write_and_repeat_import_preserves_user_data(self):
        old=self.store.ingest(1,record(journal='Original Journal',venue_type='journal'))['id']
        self.store.feedback(old,{'saved':True,'notes':'Keep 中文 note'});save_analysis(self.store,old)
        before=self.store.item(old);sources=self.store.sources()
        with self.store.db() as c:analyses=[tuple(r) for r in c.execute('SELECT * FROM analyses')]
        self.service.scispace_import({'content':export()},True)
        self.assertEqual(self.store.sources(),sources);self.assertEqual(self.store.item(old),before)
        first=self.service.scispace_import({'content':export()});second=self.service.scispace_import({'content':export()})
        self.assertEqual(first['duplicates'],1);self.assertEqual(second['duplicates'],1)
        after=self.store.item(old)
        for key in ('saved','notes','analyses','journal','current_version','primary_record','title','authors'):
            if key in before:self.assertEqual(after[key],before[key],key)
        with self.store.db() as c:self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM analyses')],analyses)
        manual=[s for s in self.store.sources() if s['kind']=='scispace_import'];self.assertEqual(len(manual),1);self.assertFalse(manual[0]['enabled'])
    def test_trash_never_resurrects_and_other_workers_may_continue(self):
        item=self.store.ingest(1,record())['id'];self.store.set_deleted('items',item,True)
        self.service.workers[999]={'group':('daily','other')}
        result=self.service.scispace_import({'content':export()});self.assertEqual(result['trashed'],1);self.assertEqual(self.store.items(),[])
        self.service.workers.clear()
    def test_history_date_filter_active_conflict_and_import_only_analysis(self):
        hid=self.history(year_from=2000,year_to=2005)
        self.service.workers[999]={'group':('history',hid)}
        with self.assertRaises(AppError) as e:self.service.scispace_import({'content':export(),'history_id':hid})
        self.assertEqual(e.exception.code,'scispace_history_busy');self.service.workers.clear()
        rejected=self.service.scispace_import({'content':export(date='1990'),'history_id':hid});self.assertEqual(rejected['outside_year'],1)
        self.assertEqual(self.store.stats()['total'],0)
        result=self.service.scispace_import({'content':export(),'history_id':hid});self.assertEqual(result['history_added'],1)
        h=self.service.history.get(hid);self.assertEqual(h['progress']['streams'],[]);self.assertEqual(h['counts']['pending'],1)
        with patch('academic_updater.history.historical_page') as network:
            job=self.service.start_job('history_search',hid)
            end=time.monotonic()+8
            while self.service.lock.locked() and time.monotonic()<end:time.sleep(.02)
            network.assert_not_called()
        self.assertEqual(self.store.job(job)['status'],'complete');h=self.service.history.get(hid);self.assertEqual(h['counts']['completed'],1)
        again=self.service.scispace_import({'content':export(),'history_id':hid})
        self.assertEqual(again['history_added'],0);self.assertEqual(self.service.history.get(hid)['report'],h['report'])


class ApiTests(unittest.TestCase):
    setUp=test_trash.TrashAPITests.setUp
    tearDown=test_trash.TrashAPITests.tearDown
    fetch=test_trash.TrashAPITests.fetch
    def test_context_csrf_import_and_manual_source(self):
        context=json.loads(self.fetch('/api/scispace/context'));self.assertEqual(context['mode'],'manual_import')
        with self.assertRaises(urllib.error.HTTPError) as e:self.fetch('/api/scispace/import',{'content':export()},False)
        self.assertEqual(e.exception.code,403)
        self.assertEqual(json.loads(self.fetch('/api/scispace/preview',{'content':export()}))['count'],1)
        self.assertEqual(json.loads(self.fetch('/api/scispace/import',{'content':export()}))['new'],1)
        source=next(s for s in self.app.store.sources() if s['kind']=='scispace_import')
        with self.assertRaises(urllib.error.HTTPError) as e:self.fetch('/api/sources/'+str(source['id']),{'enabled':True})
        self.assertEqual(e.exception.code,400)
        self.assertIn('showSciSpace',self.fetch('/scispace.js'))


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.active={'understanding':{'queries':['MRI AND neuronavigation','individualized AND targeting'],'keywords_en':['brain','TMS']}}
        self.settings={'max_per_source':5,'lookback_days':7}
    def test_arxiv_keeps_concept_intersections_and_native_override(self):
        with patch('academic_updater.sources.arxiv_request',return_value=b'feed') as remote,patch('academic_updater.sources.arxiv_records',return_value=([],0)):
            collect({'kind':'arxiv'},self.active,self.settings)
            q=urllib.parse.parse_qs(urllib.parse.urlsplit(remote.call_args.args[0]).query)['search_query'][0]
            self.assertIn('all:"MRI" AND all:"neuronavigation"',q);self.assertIn('all:"individualized" AND all:"targeting"',q);self.assertNotIn('all:"brain"',q)
            collect({'kind':'arxiv','query':'ti:neuronavigation AND cat:q-bio.NC'},self.active,self.settings)
            q=urllib.parse.parse_qs(urllib.parse.urlsplit(remote.call_args.args[0]).query)['search_query'][0];self.assertIn('ti:neuronavigation AND cat:q-bio.NC',q)
    def test_crossref_queries_ranked_and_budget_shared(self):
        def remote(url):
            q=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query);self.assertEqual(q['sort'],['score']);self.assertIn('from-index-date:',q['filter'][0])
            return {'message':{'items':[{'DOI':'10.1234/repeated','title':['Same paper']}]*int(q['rows'][0]),'total-results':100}}
        with patch('academic_updater.sources.get_json',side_effect=remote) as fetch:
            rows,limited=collect({'kind':'crossref'},self.active,self.settings)
        queries=[urllib.parse.parse_qs(urllib.parse.urlsplit(c.args[0]).query) for c in fetch.call_args_list]
        self.assertEqual([q['query.bibliographic'][0] for q in queries],['MRI neuronavigation','individualized targeting'])
        self.assertEqual(sum(int(q['rows'][0]) for q in queries),5);self.assertEqual(len(rows),1);self.assertTrue(limited)


if __name__=='__main__':unittest.main()
