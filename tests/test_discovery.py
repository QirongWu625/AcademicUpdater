import copy,json,tempfile,unittest
from unittest.mock import Mock,patch
from academic_updater.discovery import normalize_plan,resolve_author,discovery_page,abstract_text
from academic_updater.storage import Store
from academic_updater.service import Service
from academic_updater.history import HISTORY_PLAN_SCHEMA
from academic_updater.network import AppError
from test_core import scope
from test_history import ControlledAI,answer

AUTHOR='https://openalex.org/A1234'
def author_plan(**extra):
    return normalize_plan({'mode':'author','author_name':'Luca Cocchi','institution':'QIMR / QIMR Berghofer',**extra})
def identity(identifier=AUTHOR,name='Luca Cocchi',institution='QIMR Berghofer Medical Research Institute'):
    return {'id':identifier,'display_name':name,'orcid':'https://orcid.org/0000-0003-3651-2676','affiliations':[{'institution':{'display_name':institution}}],'works_count':135}
def work(n=1,author=AUTHOR):
    return {'id':f'https://openalex.org/W{n}','title':f'Study {n}','doi':f'https://doi.org/10.1234/{n}','publication_date':'2009-01-01','cited_by_count':12,
            'authorships':[{'author':{'id':author,'display_name':'Luca Cocchi'},'institutions':[{'display_name':'University of Lausanne'}]}],
            'primary_location':{'source':{'type':'journal','display_name':'Example Journal','issn':['1234-5678']}},'abstract_inverted_index':{'Target':[0],'effect':[1]}}

class DiscoveryTests(unittest.TestCase):
    def test_name_and_institution_resolve_person_not_topic(self):
        with patch('academic_updater.discovery.openalex',return_value={'results':[identity('https://openalex.org/A999','L. Cocchi','Geophysics Institute'),identity()]}) as api:
            resolved=resolve_author(author_plan())
        self.assertEqual(resolved['id'],AUTHOR);self.assertEqual(resolved['works_count'],135)
        self.assertEqual(api.call_args.args[1]['search'],'Luca Cocchi')

    def test_ambiguous_identity_is_not_guessed(self):
        with patch('academic_updater.discovery.openalex',return_value={'results':[identity(),identity('https://openalex.org/A5678')]}):
            with self.assertRaises(AppError) as error:resolve_author(author_plan())
            self.assertEqual(error.exception.code,'author_identity_ambiguous')

    def test_orcid_can_disambiguate_and_wrong_institution_fails(self):
        other=identity('https://openalex.org/A5678');other['orcid']='https://orcid.org/0000-0001-7835-1116'
        with patch('academic_updater.discovery.openalex',return_value={'results':[identity(),other]}):
            self.assertEqual(resolve_author(author_plan(orcid='0000-0003-3651-2676'))['id'],AUTHOR)
            with self.assertRaises(AppError):resolve_author(author_plan(institution='Unrelated Institute'))

    def test_author_pages_enforce_id_and_include_earlier_institutions(self):
        state={'mode':'author','author_id':AUTHOR}
        with patch('academic_updater.discovery.openalex',return_value={'meta':{'count':3},'results':[work(1),work(2,'https://openalex.org/A999')]}) as api:
            records,next_state=discovery_page('Luca Cocchi',{},state,2)
        self.assertEqual(len(records),1);self.assertEqual(records[0]['published_at'],'2009-01-01');self.assertEqual(next_state['identity_rejected'],1)
        params=api.call_args.args[1];self.assertEqual(params['filter'],'authorships.author.id:A1234');self.assertEqual(params['page'],1)
        with patch('academic_updater.discovery.openalex',return_value={'meta':{'count':3},'results':[work(3)]}) as api:
            records,last=discovery_page('Luca Cocchi',{}, {**state,**next_state},1)
        self.assertEqual(api.call_args.args[1]['per_page'],2);self.assertEqual(api.call_args.args[1]['page'],2);self.assertTrue(last['done'])

    def test_semantic_query_keeps_full_question_and_reports_source_cap(self):
        question='How does individualized MRI guidance improve the targeting of transcranial magnetic stimulation?'
        with patch('academic_updater.discovery.openalex',return_value={'meta':{'count':50},'results':[work(n) for n in range(50)]}) as api:
            records,state=discovery_page(question,{'year_from':2000},{},100)
        self.assertEqual(api.call_args.args[1]['search.semantic'],question);self.assertEqual(api.call_args.args[1]['per_page'],50)
        self.assertTrue(api.call_args.kwargs['semantic']);self.assertTrue(state['source_limited']);self.assertTrue(state['done']);self.assertEqual(len(records),50)

    def test_abstract_reconstruction_and_invalid_plan(self):
        self.assertEqual(abstract_text({'two':[1],'one':[0],'ignored':[50000]}),'one two')
        for invalid in ({'mode':'author'},{'mode':'random'},{'semantic_queries':['x']*4},{'orcid':'random'}):
            with self.assertRaises(AppError):normalize_plan(invalid)

    def test_author_workflow_disables_landmark_and_preserves_identity_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);ai=ControlledAI();service=Service(store,ai)
            s=scope();s.update(retrieval=author_plan(),queries=['Luca Cocchi'])
            h=service.history.save({'prompt':'Luca Cocchi QIMR; no topic restrictions','scope':s,'config':{'sources':['crossref'],'discovery_mode':'landmark','analyze':True}})
            self.assertEqual(h['config']['discovery_mode'],'author');self.assertEqual(h['config']['sources'],['openalex'])
            captured=[]
            original=ai.generate
            def generate(task,instructions,payload,spec,settings=None):
                if task=='history_papers':
                    captured.extend(payload['papers']);return {'papers':[{**answer(p),'relevance':'low'} for p in payload['papers']]}
                return original(task,instructions,payload,spec,settings)
            ai.generate=generate
            row=work();row['abstract_inverted_index']=None
            with patch('academic_updater.history.resolve_author',return_value={**identity(),'name':'Luca Cocchi'}),patch('academic_updater.discovery.openalex',return_value={'meta':{'count':1},'results':[row]}):
                with store.db() as c:job=c.execute("INSERT INTO runs(kind,status,started_at) VALUES('history_search','running','2026-10-27')").lastrowid
                service.history.search(h['id'],store.settings(),job)
            saved=service.history.get(h['id']);paper=saved['items'][0]
            self.assertEqual(captured[0]['matched_author_id'],AUTHOR);self.assertEqual(captured[0]['authors'],['Luca Cocchi'])
            self.assertEqual(paper['history_analysis']['relevance'],'high');self.assertEqual(paper['history_analysis']['role'],'uncertain')
            self.assertIn('No abstract',paper['history_analysis']['contribution_en']);self.assertEqual(paper['citation_source'],'OpenAlex')

    def test_ai_interpretation_uses_retrieval_schema_and_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);ai=Mock();service=Service(store,ai);result={**scope(),'retrieval':author_plan()};ai.generate.return_value=result
            h=service.history.save({'prompt':'Luca Cocchi QIMR, all topics'})
            with patch('academic_updater.history.resolve_author',return_value={'id':AUTHOR,'name':'Luca Cocchi'}):service.history.plan(h['id'],store.settings())
            saved=service.history.get(h['id'],False)
            self.assertEqual(ai.generate.call_args.args[3],HISTORY_PLAN_SCHEMA);self.assertEqual(saved['scope']['queries'],['Luca Cocchi'])
            self.assertEqual(saved['scope']['retrieval']['topic_constraint'],'');self.assertEqual(saved['config']['discovery_mode'],'author')
