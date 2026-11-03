import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock,patch
from academic_updater.storage import Store,encode,now
from academic_updater.service import Service,JobPaused
from academic_updater.network import AppError
from test_core import record,scope
from test_upgrade import save_analysis

TEXT='We studied personalized brain stimulation using neurophysiological measurements in a prospective controlled study. The abstract reports methods and outcomes for assessing treatment response.'


class AbstractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name)
        p=self.store.save_profile({'revision':0,'prompt':'Brain stimulation'});self.store.apply_profile(p['revision'],scope())
        self.ai=Mock();self.service=Service(self.store,self.ai);self.abstracts=self.service.abstracts
        with self.store.db() as c:self.job=c.execute("INSERT INTO runs(kind,status,started_at) VALUES('abstract_retrieval','running',?)",(now(),)).lastrowid
    def tearDown(self):self.temp.cleanup()
    def add(self,n=1,**kwargs):return self.store.ingest(1,record(doi=f'10.1234/{n}',external_id=str(n),url=f'https://example.org/{n}',abstract='',**kwargs))['id']
    def evidence(self):return {'abstract':TEXT,'source':'Europe PMC','url':'https://europepmc.org/article/MED/123','retrieved_at':now(),'attempts':[]}

    def test_doi_mismatch_rejected_and_openalex_fallback(self):
        item=self.store.item(self.add())
        index={word:[i for i,w in enumerate(TEXT.split()) if w==word] for word in TEXT.split()}
        replies=[{'resultList':{'result':[{'doi':'10.1234/wrong','abstractText':TEXT}]}},{'doi':'https://doi.org/10.1234/1','abstract_inverted_index':index}]
        with patch('academic_updater.abstracts.get_json',side_effect=replies),patch('academic_updater.abstracts.request') as page:
            evidence,attempts=self.abstracts.lookup(item,lambda:None)
        self.assertEqual(evidence['source'],'OpenAlex');self.assertEqual(evidence['abstract'],TEXT);page.assert_not_called()
        self.assertEqual(len(attempts),2)

    def test_publisher_requires_identity_and_explicit_abstract(self):
        item=self.store.item(self.add())
        for html in [f'<meta name="citation_doi" content="10.1234/wrong"><meta name="citation_abstract" content="{TEXT}">',f'<meta name="citation_doi" content="10.1234/1"><meta name="description" content="{TEXT}">']:
            with patch('academic_updater.abstracts.get_json',return_value={}),patch('academic_updater.abstracts.request',return_value=html.encode()):
                self.assertIsNone(self.abstracts.lookup(item,lambda:None)[0])
        html=f'<meta name="citation_doi" content="10.1234/1"><meta name="citation_abstract" content="{TEXT}">'
        with patch('academic_updater.abstracts.get_json',return_value={}),patch('academic_updater.abstracts.request',return_value=html.encode()):
            self.assertEqual(self.abstracts.lookup(item,lambda:None)[0]['abstract'],TEXT)

    def test_enrichment_preserves_feedback_sources_and_old_analysis(self):
        item_id=self.add();self.store.feedback(item_id,{'saved':True,'notes':'Keep 中文','is_read':True});save_analysis(self.store,item_id,'uncertain')
        before=self.store.item(item_id)
        with patch.object(self.abstracts,'lookup',return_value=(self.evidence(),[])) as lookup:
            with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(lambda _:self.abstracts.enrich(item_id,self.job),range(2)))
        self.assertEqual(sum(out),1);self.assertEqual(lookup.call_count,1)
        after=self.store.item(item_id)
        for key in ('id','title','url','authors','journal','saved','notes','is_read','history_only','first_seen'):self.assertEqual(after[key],before[key])
        self.assertNotEqual(after['current_version'],before['current_version']);self.assertEqual(len(after['versions']),2)
        self.assertEqual(after['analyses'],before['analyses']);self.assertEqual(after['abstract_lookup']['status'],'found')
        self.assertEqual(after['sources'][0],before['sources'][0]);self.assertEqual(after['sources'][1]['name'],'Europe PMC')
        self.store.ingest(1,record(doi='10.1234/1',external_id='1',url='https://example.org/1',abstract=''))
        self.assertEqual(self.store.item(item_id)['abstract'],TEXT)

    def test_unavailable_backoff_and_new_version_retry(self):
        item_id=self.add()
        with patch.object(self.abstracts,'lookup',return_value=(None,[])) as lookup:
            self.abstracts.enrich(item_id,self.job);self.abstracts.enrich(item_id,self.job)
            self.assertEqual(lookup.call_count,1);self.assertNotIn(item_id,self.abstracts.pending())
            self.store.ingest(1,record(doi='10.1234/1',external_id='1',url='https://example.org/1',abstract='',title='A changed title'))
            self.assertIn(item_id,self.abstracts.pending());self.abstracts.enrich(item_id,self.job)
            self.assertEqual(lookup.call_count,2)

    def test_pause_and_restart_recover_queue_without_duplicate_version(self):
        item_id=self.add()
        with patch.object(self.abstracts,'lookup',side_effect=JobPaused()):
            with self.assertRaises(JobPaused):self.abstracts.enrich(item_id,self.job)
        self.assertEqual(self.store.item(item_id)['abstract_lookup']['status'],'pending')
        with self.store.db() as c:c.execute("UPDATE abstract_lookups SET status='running'")
        reopened=Store(self.temp.name);self.assertEqual(reopened.item(item_id)['abstract_lookup']['status'],'pending')
        self.assertEqual(len(reopened.item(item_id)['versions']),1)

    def test_trash_not_retrieved_or_restored(self):
        item_id=self.add();self.store.set_deleted('items',item_id,True)
        with patch.object(self.abstracts,'lookup') as lookup:self.abstracts.enrich(item_id,self.job)
        lookup.assert_not_called();self.assertEqual(self.abstracts.pending(),[])
        self.assertTrue(self.store.item(item_id,include_deleted=True)['deleted_at'])

    def test_reassessment_uses_new_version_and_digest_only_confirmed(self):
        item_id=self.add();save_analysis(self.store,item_id,'uncertain')
        other=self.add(2);save_analysis(self.store,other,'uncertain')
        payload={'profile':self.store.get('profile')['active'],'settings':self.store.settings()}
        self.ai.analyze.side_effect=lambda iid,**kw:save_analysis(self.store,iid,'medium',kw['profile'],kw['settings'])
        with patch.object(self.abstracts,'lookup',side_effect=lambda item,check:(self.evidence(),[]) if item['id']==item_id else (None,[])):
            result=self.abstracts.run(self.job,payload)
        self.assertEqual(result['found'],1);self.assertEqual(self.service.digest()['ids'],[item_id])
        self.assertEqual(len(self.store.item(item_id)['analyses']),2)
        self.assertEqual(self.ai.analyze.call_args.kwargs['expected_version'],self.store.item(item_id)['current_version'])

    def test_stale_digest_excludes_uncertain_low_unanalyzed_ignored_and_old_scope(self):
        ids=[self.add(i) for i in range(1,6)]
        for iid,relevance in zip(ids,['high','medium','low','uncertain']):save_analysis(self.store,iid,relevance)
        day=self.service.local_day()
        with self.store.db() as c:c.execute('INSERT INTO digests VALUES(?,?,?)',(day,encode(ids),now()))
        self.assertEqual(set(self.service.digest()['ids']),set(ids[:2]))
        self.store.feedback(ids[0],{'ignored':True});self.assertEqual(self.service.digest()['ids'],[ids[1]])
        p=self.store.save_profile({'revision':self.store.get('profile')['revision'],'prompt':'New scope'});self.store.apply_profile(p['revision'],scope())
        self.assertEqual(self.service.digest()['ids'],[])

    def test_history_snapshot_refresh_and_stale_analysis_guard(self):
        item_id=self.add();hid=self.service.history.save({'prompt':'History','scope':{'field_en':'Science','queries':['science']},'config':{'analyze':True,'discovery_mode':'all'}})['id']
        item=self.store.item(item_id);snapshot={**item,'matched_author_id':'A123','citation_count':20}
        with self.store.db() as c:
            c.execute("INSERT INTO history_items(history_id,item_id,version_id,snapshot,status,result) VALUES(?,?,?,?,'completed',?)",(hid,item_id,item['current_version'],encode(snapshot),encode({'relevance':'uncertain'})))
            c.execute("UPDATE histories SET report=? WHERE id=?",(encode({'overview_en':'old report'}),hid))
        with patch.object(self.abstracts,'lookup',return_value=(self.evidence(),[])):self.abstracts.enrich(item_id,self.job)
        h=self.service.history.get(hid);paper=h['items'][0]
        self.assertEqual(paper['abstract'],TEXT);self.assertEqual(paper['matched_author_id'],'A123');self.assertEqual(paper['citation_count'],20)
        self.assertEqual(h['report'],{});self.assertEqual(h['counts']['pending'],1)
        from test_history import answer
        self.ai.generate.return_value={'papers':[answer(snapshot)]}
        self.service.history.analyze_batch(hid,h['scope'],[snapshot],self.store.settings())
        self.assertEqual(self.service.history.get(hid)['counts']['pending'],1)
        self.ai.generate.return_value={'papers':[answer(paper)]}
        self.service.history.analyze_batch(hid,h['scope'],[paper],self.store.settings())
        self.assertEqual(self.service.history.get(hid)['counts']['completed'],1)

    def test_scheduler_respects_manual_pause_and_clear_removes_lookup_data(self):
        item_id=self.add()
        with self.store.db() as c:c.execute("UPDATE runs SET status='paused' WHERE id=?",(self.job,))
        with patch.object(self.service,'start_job') as start:self.service.abstracts_tick()
        start.assert_not_called()
        with patch.object(self.abstracts,'lookup',return_value=(None,[])):self.abstracts.enrich(item_id,self.job)
        self.store.clear_dataset()
        self.assertEqual(self.abstracts.status()['missing'],0)
        with self.store.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM abstract_lookups').fetchone()[0],0)


if __name__=='__main__':unittest.main()
