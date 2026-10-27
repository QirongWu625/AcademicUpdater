import copy,io,json,tempfile,unittest
from unittest.mock import Mock,patch
from academic_updater.ai import AI,schema,STR
from academic_updater.storage import Store
from academic_updater.service import Service
from academic_updater.journal_lookup import verify_result,publisher_pages
from academic_updater.network import AppError
from test_core import record

URL='https://www.nature.com/example/journal-metrics'
QUOTE='Journal Impact Factor 2025: 5.4'
def metric():return {'status':'found','journal':'Example Journal','issn':'1234-5678','metric_type':'JIF','impact_factor':'5.4','year':'2025','source':'Publisher metrics','source_url':URL,'evidence_quote':QUOTE,'_web_sources':[URL]}

class JournalLookupTests(unittest.TestCase):
    def test_publisher_discovery_follows_metrics_links_and_ignores_other_hosts(self):
        root='https://www.nature.com/example'
        html='<h1>Example Journal</h1><a href="/example/journal-metrics">Journal metrics</a><a href="https://127.0.0.1/impact">Impact factor</a>'
        with patch('academic_updater.journal_lookup.openalex',return_value={'results':[{'display_name':'Example Journal','issn':['1234-5678'],'homepage_url':root}]}),patch('academic_updater.journal_lookup.validate_url'),patch('academic_updater.journal_lookup.request',side_effect=[html.encode(),QUOTE.encode()]) as fetch:
            pages=publisher_pages('Example Journal',['1234-5678'])
        self.assertEqual([p['url'] for p in pages],[root,URL]);self.assertEqual(fetch.call_count,2)

    def test_missing_native_web_search_uses_public_pages_and_ai_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.put('settings',{**store.settings(),'model':'gpt-6.1-sol'});ai=Mock();service=Service(store,ai)
            ai.generate.side_effect=[AppError('web_search_unavailable'),metric()]
            with store.db() as c:job=c.execute("INSERT INTO runs(kind,status,started_at) VALUES('journal_metrics','running','2026-10-27')").lastrowid
            with patch('academic_updater.journal_lookup.publisher_pages',return_value=[{'url':URL,'text':QUOTE}]),patch('academic_updater.journal_lookup.verify_result',return_value={'impact_factor':5.4}) as verify:
                result=service.journals.find(job,store.settings(),'Example Journal',['1234-5678'])
            self.assertEqual(result['impact_factor'],5.4);self.assertEqual(ai.generate.call_count,2)
            self.assertEqual(ai.generate.call_args.args[0],'journal_if_extract');self.assertIn('pages',ai.generate.call_args.args[2])
            self.assertEqual(verify.call_args.args[0]['_web_sources'],[URL]);self.assertEqual(store.get('journal_lookup_blocked')['fallback'],'publisher_pages')

    def test_only_verified_publisher_evidence_is_accepted(self):
        with patch('academic_updater.journal_lookup.validate_url'),patch('academic_updater.journal_lookup.request',return_value=('<h1>Example Journal</h1><p>1234-5678</p><p>'+QUOTE+'</p>').encode()):
            m=verify_result(metric(),'Example Journal',['1234-5678']);self.assertEqual(m['impact_factor'],5.4);self.assertEqual(m['origin'],'automatic')
            for changes in ({'year':'2024'},{'impact_factor':'6.4'},{'metric_type':'CiteScore'},{'_web_sources':[]},{'journal':'Different Journal','issn':''},{'evidence_quote':'Five-year Journal Impact Factor 2025: 5.4'},{'evidence_quote':QUOTE+' invented'},{'source_url':'https://127.0.0.1/metrics'},{'source_url':'https://example.org/metrics'}):
                with self.subTest(changes=changes),self.assertRaises(AppError):verify_result({**metric(),**changes},'Example Journal',['1234-5678'])

    def test_page_must_match_journal_identity(self):
        with patch('academic_updater.journal_lookup.validate_url'),patch('academic_updater.journal_lookup.request',return_value=('<p>Unrelated journal '+QUOTE+'</p>').encode()):
            with self.assertRaises(AppError):verify_result(metric(),'Example Journal',['1234-5678'])

    def test_web_tool_must_complete_and_supply_cited_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.put('settings',{**store.settings(),'model':'gpt-6.1-sol'});vault=Mock();oauth=Mock();oauth.access_token.return_value='synthetic-test-token';ai=AI(store,vault,oauth)
            for called in (True,False):
                response={'output':[{'type':'message','content':[{'type':'output_text','text':'{"value":"ok"}'}]}]}
                if called:response['output'].insert(0,{'type':'web_search_call','status':'completed','action':{'sources':[{'url':URL}]}})
                stream=io.BytesIO(('data: '+json.dumps({'type':'response.completed','response':response})+'\n\n').encode())
                with patch('academic_updater.ai.request',return_value=stream) as req:
                    if called:
                        out=ai.generate('test','Find evidence',{},schema({'value':STR}),web_search=True)
                        self.assertEqual(out['_web_sources'],[URL]);self.assertEqual(json.loads(req.call_args.kwargs['data'])['tools'],[{'type':'web_search'}])
                    else:
                        with self.assertRaisesRegex(AppError,'web_search_unavailable'):ai.generate('test','Find evidence',{},schema({'value':STR}),web_search=True)

    def test_queue_is_deduplicated_backfilled_and_does_not_replace_manual_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);service=Service(store,Mock())
            item=store.ingest(1,record(journal='Example Journal',issns=['1234-5678'],venue_type='journal'))['id']
            store.ingest(1,record(doi='10.1234/second',external_id='second',journal='Example Journal',venue_type='journal'))
            self.assertEqual(len(service.journals.pending()),1)
            with store.db() as c:c.execute('DELETE FROM journal_lookups')
            store=Store(folder);self.assertEqual(store.metric_status()['pending'],1)
            manual={**metric(),'impact_factor':3.0};store.save_metrics([manual]);store.save_metrics([{**metric(),'impact_factor':5.4}],automatic=True)
            self.assertEqual(store.item(item)['impact_factor'],3.0);self.assertEqual(store.item(item)['if_status'],'provided')

    def test_failed_authentication_does_not_spawn_endless_lookup_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.put('settings',{**store.settings(),'model':'gpt-6.1-sol'});service=Service(store,Mock())
            store.ingest(1,record(journal='Example Journal',venue_type='journal'))
            with store.db() as c:c.execute("INSERT INTO runs(kind,status,started_at,error) VALUES('journal_metrics','paused','2026-10-27','ai_not_connected')")
            with patch.object(service,'start_job') as start:
                service.metrics_tick();service.metrics_tick();start.assert_not_called()
