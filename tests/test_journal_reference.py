import tempfile,unittest
from unittest.mock import Mock,patch
from academic_updater.journal_reference import verify_reference,resolve_issns
from academic_updater.storage import Store
from academic_updater.service import Service
from academic_updater.network import AppError
from test_core import record

URL='https://www.bioxbio.com/journal/EXAMPLE'
HTML='''<h1>Example Journal</h1><p>Journal ISSN: 1234-567X</p><table><tr><th>Year</th><th>Impact Factor (IF)</th><th>Total Cites</th></tr><tr><td>2025 (2026 update)</td><td>5.3</td><td>12345</td></tr></table>'''
def reference():return {'status':'found','journal':'Example Journal','issn':'1234-567X','metric_type':'JIF','impact_factor':'5.3','year':'2025','source':'Bioxbio','source_url':URL,'evidence_quote':'2025 (2026 update) | 5.3 | 12345','metric_label_quote':'Impact Factor (IF)','identity_quote':'Journal ISSN: 1234-567X','year_quote':'','_web_opened':[URL]}

class JournalReferenceTests(unittest.TestCase):
    def test_print_electronic_identifiers_require_registry_match(self):
        with patch('academic_updater.journal_reference.openalex',return_value={'results':[{'display_name':'Example Journal','issn':['1234-567X','1234-5678']},{'display_name':'Different Journal','issn':['9876-5432']}]}):
            self.assertEqual(resolve_issns('Example Journal',['1234-567X']),['1234-567X','1234-5678'])
            self.assertEqual(resolve_issns('Example Journal',[]),['1234-567X','1234-5678'])
        with patch('academic_updater.journal_reference.openalex',side_effect=AppError('network_error')):self.assertEqual(resolve_issns('Example Journal',['1234-567X']),['1234-567X'])

    def test_table_reference_retains_metric_year_source_and_distinct_tier(self):
        with patch('academic_updater.journal_reference.validate_url'),patch('academic_updater.journal_reference.request',return_value=HTML.encode()):
            m=verify_reference(reference(),'Example Journal',['1234-567X'])
        self.assertEqual((m['impact_factor'],m['year'],m['verification']),(5.3,2025,'third_party'))
        self.assertEqual(m['source_url'],URL);self.assertEqual(m['reference_evidence_method'],'page_text')

    def test_release_year_wrong_metric_wrong_identity_and_unopened_url_are_rejected(self):
        with patch('academic_updater.journal_reference.validate_url'),patch('academic_updater.journal_reference.request',return_value=HTML.encode()):
            changes=[{'year':'2026'},{'impact_factor':'12345'},{'metric_type':'CiteScore'},{'metric_label_quote':'CiteScore'},
                     {'metric_label_quote':'5-year Impact Factor'},{'evidence_quote':'2025 estimated Impact Factor 5.3'},
                     {'journal':'Similar Journal'},{'issn':'9876-5432'},{'identity_quote':''},{'_web_opened':[]},
                     {'source_url':'https://127.0.0.1/metrics'},{'source_url':'https://bioxbio.com.evil.example/journal/EXAMPLE'}]
            for change in changes:
                with self.subTest(change=change),self.assertRaises(AppError):verify_reference({**reference(),**change},'Example Journal',['1234-567X'])

    def test_access_blocked_web_read_is_reference_only_not_official_verification(self):
        with patch('academic_updater.journal_reference.validate_url'),patch('academic_updater.journal_reference.request',side_effect=AppError('upstream_http_error','HTTP 403')):
            m=verify_reference(reference(),'Example Journal',['1234-567X'])
        self.assertEqual(m['verification'],'third_party');self.assertEqual(m['reference_evidence_method'],'ai_web')

    def test_absent_or_conflicting_page_evidence_is_not_accepted(self):
        for html in (HTML.replace('5.3','5.4'),HTML.replace('1234-567X','9876-5432'),HTML.replace('Impact Factor (IF)','CiteScore')):
            with patch('academic_updater.journal_reference.validate_url'),patch('academic_updater.journal_reference.request',return_value=html.encode()),self.assertRaises(AppError):verify_reference(reference(),'Example Journal',['1234-567X'])

    def test_fallback_respects_opt_out_and_authentication_and_prefers_official(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);service=Service(store,Mock())
            with patch.object(service.journals,'find_official',return_value={'verification':'publisher_text'}),patch('academic_updater.journal_reference.find_reference') as fallback:
                self.assertEqual(service.journals.find(1,store.settings(),'Example Journal',[])['verification'],'publisher_text');fallback.assert_not_called()
            for code,enabled,expected in [('publisher_access_denied',True,True),('journal_homepage_unresolved',True,True),('publisher_access_denied',False,False),('ai_not_connected',True,False)]:
                store.put('settings',{**store.settings(),'reference_if':enabled})
                with patch.object(service.journals,'find_official',side_effect=AppError(code)),patch('academic_updater.journal_reference.find_reference',return_value={'verification':'third_party'}) as fallback:
                    if expected:self.assertEqual(service.journals.find(1,store.settings(),'Example Journal',[])['verification'],'third_party')
                    else:
                        with self.assertRaises(AppError):service.journals.find(1,store.settings(),'Example Journal',[])
                    self.assertEqual(fallback.called,expected)

    def test_same_year_reference_cannot_replace_official_or_manual_value(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);item=store.ingest(1,record(journal='Example Journal',issns=['1234-567X'],venue_type='journal'))['id']
            m={**reference(),'issns':['1234-567X'],'verification':'third_party'}
            store.save_metrics([m],automatic=True);self.assertEqual(store.item(item)['if_status'],'reference')
            store.save_metrics([{**m,'verification':'publisher_text','impact_factor':5.4}],automatic=True)
            store.save_metrics([m],automatic=True)
            self.assertEqual(store.item(item)['impact_factor'],5.4);self.assertEqual(store.item(item)['if_status'],'automatic')
            store.save_metrics([{**m,'impact_factor':5.5}]);store.save_metrics([m],automatic=True)
            self.assertEqual(store.item(item)['impact_factor'],5.5);self.assertEqual(store.item(item)['if_status'],'provided')

    def test_reference_results_are_counted_separately_in_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);service=Service(store,Mock());store.ingest(1,record(journal='Example Journal',issns=['1234-567X'],venue_type='journal'))
            with store.db() as c:job=c.execute("INSERT INTO runs(kind,status,started_at) VALUES('journal_metrics','running','2026-10-27')").lastrowid
            with patch.object(service.journals,'find',return_value={**reference(),'issns':['1234-567X'],'verification':'third_party'}):counts=service.journals.run(job,store.settings())
            self.assertEqual(counts['reference'],1);self.assertEqual(counts['found'],0);self.assertEqual(store.metric_status(),{'reference':1})
