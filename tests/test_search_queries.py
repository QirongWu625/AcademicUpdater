import json
import unittest
import urllib.parse
from unittest.mock import patch

import test_history as fixtures
from academic_updater.history import historical_page
from academic_updater.network import AppError
from academic_updater.search_queries import arxiv_query,crossref_queries,history_streams,upgrade_history_streams

TMS='"transcranial magnetic stimulation" (neuronavigation OR neuronavigated OR "navigated brain stimulation")'
TARGETING='TMS (individualized OR personalized OR "subject-specific") ("fMRI-guided" OR "connectivity-guided" OR "functional neuronavigation")'


class SearchQueryTests(unittest.TestCase):
    def test_tms_boolean_groups_and_phrases_are_not_literal_keywords(self):
        expected='(all:"transcranial magnetic stimulation" AND (all:"neuronavigation" OR all:"neuronavigated" OR all:"navigated brain stimulation"))'
        self.assertEqual(arxiv_query(TMS),expected)
        with patch('academic_updater.history.arxiv_request',return_value=b'x') as request,patch('academic_updater.history.arxiv_records',return_value=([],0)):
            historical_page('arxiv',TMS,{},{} )
        query=urllib.parse.parse_qs(urllib.parse.urlsplit(request.call_args.args[0]).query)['search_query'][0]
        self.assertEqual(query,expected);self.assertNotIn('all:"OR"',query)

    def test_crossref_gets_text_alternatives_not_boolean_operators(self):
        self.assertEqual(crossref_queries(TMS),[
            'transcranial magnetic stimulation neuronavigation',
            'transcranial magnetic stimulation neuronavigated',
            'transcranial magnetic stimulation navigated brain stimulation'])
        self.assertEqual(len(crossref_queries(TARGETING)),9)

    def test_plain_queries_and_operator_precedence(self):
        self.assertEqual(arxiv_query('quantum sensing'),'(all:"quantum" AND all:"sensing")')
        self.assertEqual(crossref_queries('a OR b AND c'),['a','b c'])
        self.assertEqual(crossref_queries('(a OR b) (c OR d)'),['a c','a d','b c','b d'])
        self.assertEqual(crossref_queries('a OR a'),['a'])
        self.assertEqual(arxiv_query('“brain stimulation” AND （TMS OR rTMS）'),'(all:"brain stimulation" AND (all:"TMS" OR all:"rTMS"))')

    def test_bad_or_explosive_queries_have_actionable_errors(self):
        for query in ('a OR','(a OR b','"broken','a )','a NOT b','all:TMS','()','a AND AND b','""','(' * 14+'TMS'+')'*14):
            with self.subTest(query=query),self.assertRaises(AppError) as error:arxiv_query(query)
            self.assertEqual(error.exception.code,'history_query_syntax')
        with self.assertRaises(AppError) as error:crossref_queries('(a OR b OR c OR d OR e) (f OR g OR h OR i)')
        self.assertEqual(error.exception.code,'history_query_too_broad')

    def test_variants_share_candidate_budget_without_rounding_loss(self):
        config={'sources':['crossref','arxiv'],'limit':500,'discovery_mode':'landmark'}
        streams=history_streams(config,[TMS,TARGETING])
        for original in (TMS,TARGETING):
            for source in config['sources']:
                selected=[s for s in streams if s['source']==source and s['original_query']==original]
                self.assertEqual(sum(s['limit'] for s in selected),500)
                self.assertTrue(all(s['limit']>0 for s in selected))
        self.assertEqual(len(streams),26)
        self.assertTrue(all(s['limit']==0 for s in history_streams({**config,'limit':0},[TMS])))

    def test_crossref_request_receives_expanded_query_and_fixed_date_range(self):
        config={'sources':['crossref'],'limit':100,'discovery_mode':'landmark','year_from':1990,'year_to':2020}
        streams=history_streams(config,[TMS])
        with patch('academic_updater.history.get_json',return_value={'message':{'items':[],'total-results':0}}) as request:
            for stream in streams:
                historical_page('crossref',stream['query'],config,stream,stream['limit'])
                q=urllib.parse.parse_qs(urllib.parse.urlsplit(request.call_args.args[0]).query)
                self.assertEqual(q['query.bibliographic'],[stream['query']]);self.assertNotIn(' OR ',q['query.bibliographic'][0])
                self.assertIn('from-pub-date:1990-01-01',q['filter'][0]);self.assertIn('until-pub-date:2020-12-31',q['filter'][0])

    def test_legacy_boolean_cursors_replay_once_and_plain_cursors_stay(self):
        config={'sources':['crossref','arxiv'],'limit':500,'discovery_mode':'landmark'}
        old=[{'source':'crossref','query':TMS,'sort':'score','position':100,'cursor':'old-cursor','done':True},
             {'source':'arxiv','query':'quantum sensing','position':12,'done':False}]
        streams,archived=upgrade_history_streams(config,[TMS,'quantum sensing'],old)
        self.assertEqual(archived,[old[0]]);self.assertIn(old[1],streams)
        updated=[s for s in streams if s['source']=='crossref']
        self.assertEqual(len(updated),6);self.assertEqual(sum(s['limit'] for s in updated),500)
        self.assertTrue(all(s['cursor']=='*' and s['position']==0 for s in updated))
        self.assertEqual(upgrade_history_streams(config,[TMS,'quantum sensing'],streams),(streams,[]))


class HistoricalWorkflowTests(unittest.TestCase):
    setUp=fixtures.HistoryTests.setUp
    tearDown=fixtures.HistoryTests.tearDown
    wait=fixtures.HistoryTests.wait

    def test_field_interpretation_remains_draft_not_a_completed_empty_search(self):
        hid=self.history.save({'prompt':'TMS neuronavigation history'})['id']
        job=self.service.start_job('history_plan',hid);self.wait()
        h=self.history.get(hid)
        self.assertEqual(self.store.job(job)['status'],'complete');self.assertEqual(h['status'],'draft')
        self.assertNotIn('search_started',h['progress']);self.assertFalse(self.history.list()[0]['search_started'])
        self.assertTrue(h['scope']['queries']);self.assertEqual(h['counts']['total'],0)

    def test_saved_boolean_scope_retrieves_and_deduplicates_candidates(self):
        hid=self.history.save({'prompt':'TMS neuronavigation history','scope':{'field_en':'TMS neuronavigation','queries':[TMS]},
             'config':{'sources':['crossref'],'limit':100,'discovery_mode':'all','analyze':False}})['id']
        seen=[]
        def page(source,query,config,state,size):
            seen.append((query,size));return [fixtures.history_record(1)],{'position':1,'total':1,'done':True}
        with patch('academic_updater.history.historical_page',side_effect=page):
            job=self.service.start_job('history_search',hid);self.wait()
        self.assertEqual(self.store.job(job)['status'],'complete')
        self.assertEqual([q for q,_ in seen],crossref_queries(TMS));self.assertEqual(sum(n for _,n in seen),100)
        h=self.history.get(hid);self.assertEqual(h['counts']['total'],1);self.assertTrue(self.history.list()[0]['search_started'])
        self.assertEqual(h['scope']['queries'],[TMS])

    def test_invalid_manual_query_does_not_start_or_save_misleading_draft(self):
        with self.assertRaises(AppError):self.history.save({'prompt':'TMS','scope':{'queries':['TMS OR']}})
        self.assertEqual(self.history.list(),[])

    def test_failed_source_is_partial_not_successful_no_matches(self):
        hid=self.history.save({'prompt':'TMS','scope':{'field_en':'TMS','queries':['TMS neuronavigation']},'config':{'sources':['arxiv'],'analyze':False,'discovery_mode':'all'}})['id']
        with patch('academic_updater.history.historical_page',side_effect=AppError('network_error','arXiv unavailable')):
            job=self.service.start_job('history_search',hid);self.wait()
        self.assertEqual(self.store.job(job)['status'],'partial')
        h=self.history.get(hid);self.assertEqual(h['progress']['streams'][0]['error'],'network_error');self.assertEqual(h['counts']['total'],0)

    def test_resuming_legacy_query_retains_papers_and_saved_analysis(self):
        hid=self.history.save({'prompt':'TMS','scope':{'field_en':'TMS','queries':[TMS]},'config':{'sources':['crossref'],'limit':100,'discovery_mode':'all'}})['id']
        page=([fixtures.history_record(1)],{'position':1,'total':1,'done':True})
        with patch('academic_updater.history.historical_page',return_value=page):
            job=self.service.start_job('history_search',hid);self.wait()
        before=self.history.get(hid);self.ai.calls=[]
        old={'source':'crossref','query':TMS,'sort':'score','position':100,'cursor':'old-cursor','done':True,'limit':100}
        self.history.update(hid,status='paused',progress={'search_started':True,'streams':[old]})
        with self.store.db() as c:c.execute("UPDATE runs SET status='paused' WHERE id=?",(job,))
        with patch('academic_updater.history.historical_page',return_value=page) as remote:
            self.service.resume(job);self.wait()
        after=self.history.get(hid)
        self.assertEqual(remote.call_count,3);self.assertEqual(after['items'],before['items'])
        self.assertEqual(after['progress']['previous_query_streams'],[old]);self.assertTrue(after['progress']['query_adapter_updated'])
        self.assertEqual(self.ai.calls,[])


if __name__=='__main__':unittest.main()
