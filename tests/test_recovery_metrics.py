import io,json,tempfile,unittest
from unittest.mock import Mock,patch
from academic_updater.ai import parse_stream
from academic_updater.journal_lookup import verify_result,web_metric,journal_homepages,publisher_pages
from academic_updater.network import AppError
from academic_updater.storage import Store
from academic_updater.service import Service
from test_journal_lookup import metric,URL,QUOTE
from test_core import record

def stream(events):return io.BytesIO(''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode())

class RecoveryMetricTests(unittest.TestCase):
    def test_completed_stream_items_survive_empty_final_output(self):
        call={'id':'tool1','type':'web_search_call','status':'completed','action':{'type':'open_page','url':URL}}
        message={'id':'msg1','type':'message','content':[{'type':'output_text','text':'{"ok":true}'}]}
        items=[{'type':'response.output_item.done','item':i,'output_index':n} for n,i in enumerate([call,message])]
        text,response=parse_stream(stream(items+[{'type':'response.completed','response':{'output':[]}}]),True)
        self.assertEqual(text,'{"ok":true}');self.assertEqual(response['output'],[call,message])
        text,response=parse_stream(stream(items+[{'type':'response.completed','response':{'output':[call,message]}}]),True)
        self.assertEqual(len(response['output']),2)
        with self.assertRaisesRegex(AppError,'ai_stream_interrupted'):parse_stream(stream(items))

    def test_publisher_table_uses_jif_column_metric_year_and_uppercase_issn(self):
        html='<h1>Example Journal</h1><p>1234-567X</p><p>Released in 2026: 2025 Journal Impact Factors</p><table><tr><th>Journal</th><th>Impact Factor</th><th>CiteScore</th></tr><tr><td>Example Journal</td><td>5.4</td><td>9.2</td></tr></table>'
        result={**metric(),'issn':'1234-567X','evidence_quote':'Example Journal 5.4 9.2','year_quote':'2025 Journal Impact Factors'}
        with patch('academic_updater.journal_lookup.validate_url'),patch('academic_updater.journal_lookup.request',return_value=html.encode()):
            m=verify_result(result,'Example Journal',['1234-567X']);self.assertEqual(m['impact_factor'],5.4)
            for change in ({'impact_factor':'9.2'},{'year':'2026','year_quote':'Released in 2026'},{'year_quote':'2025 Journal Impact Factors invented'}):
                with self.subTest(change=change),self.assertRaises(AppError):verify_result({**result,**change},'Example Journal',['1234-567X'])

    def test_same_publisher_identity_page_is_checked_separately(self):
        identity='https://www.nature.com/example/about'
        result={**metric(),'_web_sources':[URL,identity],'_identity_sources':[identity]}
        with patch('academic_updater.journal_lookup.validate_url'),patch('academic_updater.journal_lookup.request',side_effect=[('<h1>Example Journal</h1>'+QUOTE).encode(),b'Example Journal ISSN 1234-5678']):
            self.assertEqual(verify_result(result,'Example Journal',['1234-5678'])['identity_source_url'],identity)

    def test_known_homepage_migrations_and_access_error_are_reported(self):
        self.assertEqual(journal_homepages('http://brain.oxfordjournals.org/','Brain')[0],'https://academic.oup.com/brain/')
        self.assertEqual(journal_homepages('http://www.frontiersin.org/neuroscience','Frontiers in Neuroscience')[0],'https://www.frontiersin.org/journals/neuroscience')
        with patch('academic_updater.journal_lookup.openalex',return_value={'results':[{'display_name':'Brain','homepage_url':'http://brain.oxfordjournals.org/'}]}),patch('academic_updater.journal_lookup.validate_url'),patch('academic_updater.journal_lookup.request',side_effect=AppError('upstream_http_error','HTTP 403')):
            with self.assertRaisesRegex(AppError,'publisher_access_denied'):publisher_pages('Brain',[])

    def test_web_evidence_requires_real_page_open_identity_and_correct_metric(self):
        result={**metric(),'evidence_quote':'2025 Impact Factor | 5.4','identity_quote':'Print ISSN 1234-5678','_web_opened':[URL]}
        with patch('academic_updater.journal_lookup.validate_url'):
            self.assertEqual(web_metric(result,'Example Journal',['1234-5678'])['verification'],'ai_web')
            for change in ({'_web_opened':[]},{'identity_quote':''},{'year':'2026'},{'impact_factor':'9.2'},{'evidence_quote':'2025 5 Year Impact Factor | 5.4'},{'evidence_quote':'2025 CiteScore | 5.4'}):
                with self.subTest(change=change),self.assertRaises(AppError):web_metric({**result,**change},'Example Journal',['1234-5678'])

    def test_disagreeing_independent_web_reads_are_not_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);service=Service(store,Mock())
            first={**metric(),'evidence_quote':'2025 Impact Factor | 5.4','identity_quote':'ISSN 1234-5678','_web_opened':[URL]}
            second={**first,'impact_factor':'5.5','evidence_quote':'2025 Impact Factor | 5.5'}
            service.ai_call=Mock(side_effect=[first,second])
            with patch('academic_updater.journal_lookup.validate_url'),patch('academic_updater.journal_lookup.request',side_effect=AppError('upstream_http_error','HTTP 403')):
                with self.assertRaisesRegex(AppError,'metric_conflicting_evidence'):service.journals.find_official(1,store.settings(),'Example Journal',['1234-5678'])
            self.assertEqual(store.metrics(),[])

    def test_retry_and_one_time_migration_preserve_found_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.ingest(1,record(journal='Example Journal',issns=['1234-5678'],venue_type='journal'))
            store.put('journal_lookup_blocked',{'until':'2099'})
            with store.db() as c:
                c.execute("UPDATE journal_lookups SET status='unavailable',retry_at='2099-01-01',error='metric_not_found'")
                c.execute("DELETE FROM kv WHERE key='journal_lookup_v181'")
            store=Store(folder);self.assertEqual(store.metric_status(),{'pending':1});self.assertIsNone(store.get('journal_lookup_blocked'))
            with store.db() as c:c.execute("UPDATE journal_lookups SET status='error',retry_at='2099-01-01'")
            store=Store(folder);self.assertEqual(store.metric_status(),{'error':1})
            Service(store,Mock()).journals.retry_missing();self.assertEqual(store.metric_status(),{'pending':1})
            store.save_metrics([metric()]);Service(store,Mock()).journals.retry_missing();self.assertEqual(len(store.metrics()),1)

    def test_ai_web_provenance_is_saved_and_manual_override_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);item=store.ingest(1,record(journal='Example Journal',issns=['1234-5678'],venue_type='journal'))['id']
            store.save_metrics([{**metric(),'verification':'ai_web'}],automatic=True)
            self.assertEqual(store.item(item)['if_status'],'web_sourced')
            store.save_metrics([{**metric(),'impact_factor':6.0}]);store.save_metrics([metric()],automatic=True)
            self.assertEqual(store.item(item)['impact_factor'],6.0);self.assertEqual(store.item(item)['if_status'],'provided')
