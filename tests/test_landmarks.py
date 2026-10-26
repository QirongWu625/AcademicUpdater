import copy
import json
import unittest
import urllib.parse
from unittest.mock import patch

import test_history as fixtures
from academic_updater.history import citation_evidence, historical_page, landmark_selection
from academic_updater.storage import encode, Store
from academic_updater.service import Service
from academic_updater.network import AppError


class LandmarkTests(unittest.TestCase):
    setUp=fixtures.HistoryTests.setUp
    tearDown=fixtures.HistoryTests.tearDown
    wait=fixtures.HistoryTests.wait

    def create(self,**config):
        return self.history.save({'prompt':'Foundations of measurement','scope':{'field_en':'Measurement','queries':['measurement']},
                                  'config':{'sources':['crossref'],'limit':100,**config}})['id']

    def test_new_search_defaults_to_focus_and_requires_analysis(self):
        h=self.history.get(self.create(analyze=False))
        self.assertEqual(h['config']['discovery_mode'],'landmark')
        self.assertEqual(h['config']['min_citations'],100)
        self.assertTrue(h['config']['analyze'])
        for threshold in (0,-1,100001,'bad'):
            with self.assertRaises(AppError):self.create(min_citations=threshold)

    def test_citation_evidence_never_invents_missing_values(self):
        for count in (None,'100',True,-1):
            self.assertEqual(citation_evidence({'raw_metadata':{'is-referenced-by-count':count}}),{})
        self.assertEqual(citation_evidence({'doi':'10.1234/demo','raw_metadata':{'is-referenced-by-count':0}})['citation_count'],0)
        self.assertEqual(citation_evidence({}),{})

    def test_relevance_and_abstract_evidence_gate_selection(self):
        p={'citation_count':1000,'citation_source':'Crossref','abstract':'We introduce a general framework for measurement.'}
        self.assertFalse(landmark_selection(p,{'relevance':'low','role':'foundation','evidence_quotes':[p['abstract']]},{})['selected'])
        self.assertEqual(landmark_selection(p,{'relevance':'high','role':'method'},{})['reasons'],['highly_cited'])
        missing={'abstract':p['abstract']}
        a={'relevance':'high','role':'foundation','evidence_quotes':['A foundation paper title']}
        self.assertFalse(landmark_selection(missing,a,{})['selected'])
        a['evidence_quotes']=[p['abstract']]
        self.assertEqual(landmark_selection(missing,a,{})['reasons'],['foundational_candidate'])
        self.assertFalse(landmark_selection({'abstract':''},a,{})['selected'])

    def test_two_search_orders_share_cap_and_timeline_only_uses_shortlist(self):
        hid=self.create();seen=[]
        records=[fixtures.history_record(n) for n in (1,2,3)]
        records[0]['raw_metadata']['is-referenced-by-count']=250
        records[1]['raw_metadata']['is-referenced-by-count']=3
        records[2]['abstract']='We introduce a general measurement framework and derive its operating principles.'
        def page(source,query,config,state,size):
            seen.append((state['sort'],size))
            return records,{'position':3,'total':3,'done':True}
        original=self.ai.generate
        def generate(task,instructions,payload,spec,settings=None):
            result=original(task,instructions,payload,spec,settings=settings)
            if task=='history_papers':
                for a,p in zip(result['papers'],payload['papers']):
                    if p['title']==records[2]['title']:
                        a['role']='foundation';a['evidence_quotes']=[p['abstract']]
            return result
        self.ai.generate=generate
        with patch('academic_updater.history.historical_page',side_effect=page):
            job=self.service.start_job('history_search',hid);self.wait()
        self.assertEqual(self.store.job(job)['status'],'complete')
        self.assertEqual(seen,[('is-referenced-by-count',50),('score',50)])
        self.assertEqual(self.history.papers(hid,{})['total'],2)
        self.assertEqual(self.history.papers(hid,{'filter':'all'})['total'],3)
        self.assertEqual(self.history.papers(hid,{'filter':'excluded'})['total'],1)
        h=self.history.get(hid)
        self.assertEqual(h['selection']['selected'],2)
        self.assertEqual(len(h['report']['references']),2)
        self.assertNotIn(records[1]['title'],[r['title'] for r in h['report']['references']])
        reopened=Service(Store(self.temp.name),self.ai).history
        self.assertEqual(reopened.papers(hid,{})['total'],2)
        self.assertEqual(reopened.get(hid)['report'],h['report'])

    def test_crossref_uses_requested_citation_or_relevance_order(self):
        for order in ('is-referenced-by-count','score'):
            with patch('academic_updater.history.get_json',return_value={'message':{'items':[],'total-results':0}}) as fetch:
                historical_page('crossref','measurement',{'discovery_mode':'landmark'},{'sort':order})
                query=urllib.parse.parse_qs(urllib.parse.urlsplit(fetch.call_args.args[0]).query)
                self.assertEqual(query['sort'],[order])

    def test_legacy_search_is_not_reclassified(self):
        hid=self.create(discovery_mode='all',analyze=False)
        with self.store.db() as c:
            config=self.history.get(hid,False)['config'];config.pop('discovery_mode');config.pop('min_citations')
            c.execute('UPDATE histories SET config=? WHERE id=?',(encode(config),hid))
        with patch('academic_updater.history.historical_page',return_value=([fixtures.history_record(1)],{'position':1,'total':1,'done':True})):
            self.service.start_job('history_search',hid);self.wait()
        self.assertEqual(self.history.papers(hid,{})['total'],1)
        self.assertNotIn('selection',self.history.get(hid))

    def test_empty_shortlist_does_not_generate_speculative_timeline(self):
        hid=self.create()
        with patch('academic_updater.history.historical_page',return_value=([fixtures.history_record(1)],{'position':1,'total':1,'done':True})):
            self.service.start_job('history_search',hid);self.wait()
        h=self.history.get(hid)
        self.assertEqual(h['report']['milestones'],[])
        self.assertEqual(h['selection']['selected'],0)
        self.assertNotIn('history_timeline',[call[0] for call in self.ai.calls])
