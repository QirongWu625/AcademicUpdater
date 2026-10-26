import base64
import copy
import contextlib
import datetime as dt
import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch,Mock

from academic_updater.storage import Store
from academic_updater.network import AppError,canonical_url,doi,plain,validate_url
from academic_updater.sources import feed_records,arxiv_records,parse_xml,crossref_record
from academic_updater.ai import AI,EMPTY_UNDERSTANDING,PROFILE_SCHEMA,ANALYSIS_SCHEMA,validate_scope,parse_stream
from academic_updater.credentials import Vault,OAuth,validate_id_token,protect
from academic_updater.service import Service
from academic_updater.server import Application,make_server


def scope():
    value=copy.deepcopy(EMPTY_UNDERSTANDING)
    value.update(field_en='Quantum sensing',field_zh='量子传感',keywords_en=['quantum sensing'],queries=['quantum sensing'])
    return value


def record(**kw):
    return {'title':'A real-looking test record','abstract':'Measurement noise was reduced in a laboratory.','kind':'paper','url':'https://example.org/paper','doi':'10.1234/EXAMPLE','external_id':'source-one','authors':['A. Researcher'],'version':'v1','source_updated':'2025-01-01T00:00:00Z',**kw}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def apply_scope(self):
        p=self.store.save_profile({'revision':0,'prompt':'Track quantum sensing.'})
        return self.store.apply_profile(p['revision'],scope())

    def test_repeat_import_is_idempotent(self):
        first=self.store.ingest(1,record());second=self.store.ingest(1,record())
        self.assertTrue(first['new']);self.assertTrue(second['duplicate']);self.assertEqual(first['id'],second['id'])
        self.assertEqual(self.store.stats()['versions'],1)

    def test_cross_source_identity_preserves_feedback(self):
        i=self.store.ingest(1,record())['id'];self.store.feedback(i,{'saved':True,'notes':'My 中文 note'})
        r=self.store.ingest(2,record(url='https://another.example/p',external_id='other',doi='https://doi.org/10.1234/example'))
        self.assertEqual(i,r['id']);self.assertEqual(self.store.stats()['total'],1)
        detail=self.store.item(i);self.assertEqual(len(detail['sources']),2);self.assertEqual(detail['notes'],'My 中文 note');self.assertEqual(detail['saved'],1)

    def test_new_version_retains_history(self):
        i=self.store.ingest(1,record())['id']
        result=self.store.ingest(1,record(version='v2',abstract='New abstract',source_updated='2025-02-01T00:00:00Z'))
        self.assertTrue(result['updated']);self.assertEqual(self.store.item(i)['abstract'],'New abstract');self.assertEqual(len(self.store.item(i)['versions']),2)

    def test_unseen_old_version_cannot_regress_primary(self):
        i=self.store.ingest(1,record(version='v2',abstract='Latest',source_updated='2025-02-01T00:00:00Z'))['id']
        result=self.store.ingest(1,record())
        self.assertFalse(result['updated']);self.assertEqual(self.store.item(i)['abstract'],'Latest');self.assertEqual(len(self.store.item(i)['versions']),2)
        self.store.ingest(1,record(version='v3',abstract='Newest',source_updated='2025-03-01T00:00:00Z'))
        self.assertEqual(self.store.item(i)['abstract'],'Newest')

    def test_noncontent_metadata_does_not_create_version(self):
        self.store.ingest(1,record(raw_metadata={'citations':5}))
        result=self.store.ingest(1,record(raw_metadata={'citations':10},source_updated='2025-02-01T00:00:00Z'))
        self.assertTrue(result['duplicate']);self.assertEqual(self.store.stats()['versions'],1)

    def test_identifier_conflict_is_atomic(self):
        self.store.ingest(1,record())
        self.store.ingest(2,record(doi='10.1234/second',url='https://example.org/second',external_id='second'))
        with self.assertRaises(AppError) as error:self.store.ingest(3,record(doi='10.1234/EXAMPLE',url='https://example.org/second'))
        self.assertEqual(error.exception.code,'identifier_conflict');self.assertEqual(self.store.stats()['total'],2);self.assertEqual(self.store.stats()['versions'],2)

    def test_draft_does_not_change_active_scope(self):
        p=self.apply_scope();p=self.store.save_profile({'revision':p['revision'],'prompt':'Track biological sensing.'})
        self.assertEqual(p['active']['prompt'],'Track quantum sensing.')
        with self.assertRaises(AppError):self.store.set_understanding(1,scope(),'ai')
        self.assertEqual(self.store.get('profile')['active']['version'],1)

    def test_persistence_and_locale(self):
        p=self.apply_scope();i=self.store.ingest(1,record())['id'];self.store.feedback(i,{'notes':'Persistent note'})
        s=self.store.settings();s['language']='zh-CN';self.store.put('settings',s)
        reopened=Store(self.tmp.name);self.assertEqual(reopened.item(i)['notes'],'Persistent note');self.assertEqual(reopened.get('profile'),p)

    def test_daily_budget_serialized_across_threads(self):
        s=self.store.settings();s['daily_ai_limit']=3;self.store.put('settings',s)
        def reserve(_):
            try:self.store.reserve_ai('test');return True
            except AppError:return False
        with ThreadPoolExecutor(max_workers=8) as pool:self.assertEqual(sum(pool.map(reserve,range(12))),3)

    def test_digest_does_not_duplicate_versions(self):
        self.apply_scope();self.store.ingest(1,record());service=Service(self.store,Mock())
        self.assertEqual(service.digest(),service.digest())
        with self.store.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM delivered').fetchone()[0],1)

    def test_backup_restores_library_without_credentials(self):
        self.store.ingest(1,record());destination=self.store.backup()
        import sqlite3
        with contextlib.closing(sqlite3.connect(destination)) as c:self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],1)

    def test_ai_rejects_unsupported_quotes(self):
        self.apply_scope();i=self.store.ingest(1,record())['id'];ai=AI(self.store,Mock(),Mock())
        result={k:[] if v['type']=='array' else '' for k,v in ANALYSIS_SCHEMA['properties'].items()};result.update(relevance='high',evidence_quotes=['fabricated result'])
        with patch.object(ai,'generate',return_value=result):
            with self.assertRaises(AppError) as error:ai.analyze(i)
        self.assertEqual(error.exception.code,'ungrounded_evidence');self.assertEqual(self.store.item(i)['analyses'],[])

    def test_ai_cache_and_scope_versions(self):
        self.apply_scope();i=self.store.ingest(1,record())['id'];ai=AI(self.store,Mock(),Mock())
        result={k:[] if v['type']=='array' else '' for k,v in ANALYSIS_SCHEMA['properties'].items()};result.update(relevance='high',evidence_quotes=['Measurement noise'])
        with patch.object(ai,'generate',return_value=result) as generate:ai.analyze(i);ai.analyze(i);self.assertEqual(generate.call_count,1)
        self.assertIsNotNone(self.store.items()[0]['analysis'])
        changed=scope();changed['question_en']='How does it apply to navigation?'
        self.store.apply_profile(1,changed);self.assertIsNone(self.store.items()[0]['analysis'])

    def test_reapplying_same_scope_does_not_invalidate_analysis(self):
        first=self.apply_scope();second=self.store.apply_profile(1,scope())
        self.assertEqual(first,second)

    def test_scheduler_once_per_day_and_disabled(self):
        self.apply_scope();service=Service(self.store,Mock())
        current=dt.datetime(2026,1,1,23,0,tzinfo=dt.timezone.utc)
        with patch.object(service,'start_job') as start:
            service.schedule_tick(current);service.schedule_tick(current);self.assertEqual(start.call_count,1)
            service.schedule_tick(current+dt.timedelta(days=1));self.assertEqual(start.call_count,2)
            settings=self.store.settings();settings['schedule_enabled']=False;self.store.put('settings',settings)
            service.schedule_tick(current+dt.timedelta(days=2));self.assertEqual(start.call_count,2)

class ParsingTests(unittest.TestCase):
    def test_canonical_identifiers(self):
        self.assertEqual(doi('https://doi.org/10.1234/ABC'),'10.1234/abc')
        self.assertEqual(canonical_url('https://EXAMPLE.org/a?utm_source=r&x=1#top'),'https://example.org/a?x=1')
        self.assertEqual(plain('<script>bad()</script><p>Safe &amp; clean</p>'),'Safe & clean')
    def test_rss_and_atom(self):
        rss=b'<rss><channel><item><title>News</title><link>https://example.org/n</link><description>&lt;b&gt;Result&lt;/b&gt;</description><guid>x</guid></item></channel></rss>'
        item=feed_records(rss,'industry','https://example.org/feed')[0];self.assertEqual(item['abstract'],'Result');self.assertEqual(item['kind'],'industry')
        atom=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Talk</title><id>event-1</id><link href="/talk"/><summary>Findings</summary></entry></feed>'
        self.assertEqual(feed_records(atom,'conference','https://example.org/feed')[0]['url'],'https://example.org/talk')
    def test_arxiv_version_parsing(self):
        data=b'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:op="http://a9.com/-/spec/opensearch/1.1/"><op:totalResults>1</op:totalResults><entry><id>http://arxiv.org/abs/2401.12345v2</id><title>Test</title><summary>Result</summary></entry></feed>'
        rows,total=arxiv_records(data);self.assertEqual(total,1);self.assertEqual(rows[0]['external_id'],'2401.12345');self.assertEqual(rows[0]['version'],'v2')
    def test_reject_xml_entities(self):
        with self.assertRaises(AppError):parse_xml(b'<!DOCTYPE x [<!ENTITY e "x">]><x>&e;</x>')
        with self.assertRaises(AppError):feed_records(b'<html><body>No feed</body></html>','industry','https://example.org')
    def test_scope_needs_field_and_query(self):
        with self.assertRaises(AppError):validate_scope(copy.deepcopy(EMPTY_UNDERSTANDING))
        self.assertEqual(validate_scope(scope()),scope())
    def test_stream_requires_completion(self):
        with self.assertRaises(AppError):parse_stream(io.BytesIO(b'data: {"type":"response.output_text.delta","delta":"{}"}\n\n'))
        body=b'data: {"type":"response.completed","response":{"output":[{"content":[{"type":"output_text","text":"{}"}]}]}}\n\n'
        self.assertEqual(parse_stream(io.BytesIO(body)),'{}')
    def test_private_source_rejected(self):
        with self.assertRaises(AppError):validate_url('https://127.0.0.1/feed')
        self.assertEqual(validate_url('http://127.0.0.1:11434/v1',True),'http://127.0.0.1:11434/v1')

class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cryptography.hazmat.primitives.asymmetric import rsa
        cls.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        def b64(v):return base64.urlsafe_b64encode(v).decode().rstrip('=')
        cls.b64=staticmethod(b64);p=cls.key.public_key().public_numbers()
        cls.jwks={'keys':[{'kid':'test','kty':'RSA','alg':'RS256','n':b64(p.n.to_bytes(256,'big')),'e':b64(p.e.to_bytes(3,'big'))}]}
    def token(self,**changes):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        claims={'iss':'https://auth.openai.com','aud':'oaiapp_test','exp':time.time()+1000,'nonce':'test-nonce','sub':'test-sub',**changes}
        body=self.b64(json.dumps({'kid':'test','alg':'RS256'}).encode())+'.'+self.b64(json.dumps(claims).encode())
        return body+'.'+self.b64(self.key.sign(body.encode(),padding.PKCS1v15(),hashes.SHA256()))
    def test_valid_identity(self):self.assertEqual(validate_id_token(self.token(),self.jwks,'oaiapp_test','test-nonce')['sub'],'test-sub')
    def test_identity_rejects_wrong_issuer_audience_nonce_expiry(self):
        for changes in [{'iss':'https://evil.example'},{'aud':'other'},{'nonce':'other'},{'exp':1}]:
            with self.subTest(changes=changes),self.assertRaises(AppError):validate_id_token(self.token(**changes),self.jwks,'oaiapp_test','test-nonce')
    def test_dpapi_round_trip(self):
        if os.name!='nt':self.skipTest('Windows DPAPI')
        secret=b'test-only-not-a-real-token';encrypted=protect(secret)
        self.assertNotIn(secret,encrypted);self.assertEqual(protect(encrypted,True),secret)
    def test_oauth_state_once_and_pkce(self):
        with tempfile.TemporaryDirectory() as directory:
            oauth=OAuth(Vault(directory),Store(directory));url=oauth.start(8765);q=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            self.assertEqual(q['code_challenge_method'],['S256'])
            self.assertTrue(q['ext_agent_host_id'][0].startswith('urn:uuid:'))
            self.assertEqual(uuid.UUID(q['ext_agent_host_id'][0]).version,4)
            args={'state':q['state'][0],'client_id':'oaiapp_test','error':'access_denied'}
            with self.assertRaises(AppError) as first:oauth.callback(args)
            with self.assertRaises(AppError) as second:oauth.callback(args)
            self.assertEqual(first.exception.code,'oauth_denied');self.assertEqual(second.exception.code,'invalid_oauth_state')

    def test_host_id_migration_preserves_uuid_and_user_data(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);legacy=str(uuid.uuid4());store.put('host_id',legacy)
            profile=store.save_profile({'revision':0,'prompt':'Keep my research prompt.'})
            item=store.ingest(1,record())['id'];store.feedback(item,{'notes':'Keep my notes.'})
            oauth=OAuth(Mock(),store)
            query=urllib.parse.parse_qs(urllib.parse.urlsplit(oauth.start(8765)).query)
            self.assertEqual(query['ext_agent_host_id'],['urn:uuid:'+legacy])
            self.assertEqual(store.get('host_id'),'urn:uuid:'+legacy)
            self.assertEqual(store.get('profile'),profile)
            self.assertEqual(store.item(item)['notes'],'Keep my notes.')

    def test_host_id_stable_across_restart_and_fresh_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            first=OAuth(Vault(directory),Store(directory))
            before=urllib.parse.parse_qs(urllib.parse.urlsplit(first.start(8765)).query)
            restarted=OAuth(Vault(directory),Store(directory))
            after=urllib.parse.parse_qs(urllib.parse.urlsplit(restarted.start(8765)).query)
            self.assertEqual(before['ext_agent_host_id'],after['ext_agent_host_id'])
            for key in ('state','nonce','code_challenge'):self.assertNotEqual(before[key],after[key])

    def test_registered_account_reuses_host_id_and_client(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);host=uuid.uuid4().urn;store.put('host_id',host)
            accounts={'oaiapp_existing':{'sub':'same-sub','email':'test@example.com'}}
            vault=Mock();vault.get.side_effect=lambda key,default=None:accounts if key=='accounts' else default
            oauth=OAuth(vault,store)
            query=urllib.parse.parse_qs(urllib.parse.urlsplit(oauth.start(8765,'oaiapp_existing')).query)
            self.assertEqual(query['client_id'],['oaiapp_existing'])
            self.assertEqual(query['ext_agent_host_id'],[host])
            self.assertNotIn('agent_name_hint',query)
            vault.set.assert_not_called()

    def test_alternative_host_uri_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            for host in ['urn:ietf:params:oauth:jwk-thumbprint:sha-256:test-thumbprint','did:key:test-key']:
                store.put('host_id',host);OAuth(Mock(),store)
                self.assertEqual(store.get('host_id'),host)

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name);self.server=make_server(self.app,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.app.port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def fetch(self,path,body=None,headers=None):
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
        with urllib.request.urlopen(req,timeout=4) as r:return r.status,r.read()
    def test_health_and_csrf(self):
        status,body=self.fetch('/api/health');self.assertEqual(status,200)
        with self.assertRaises(urllib.error.HTTPError) as error:self.fetch('/api/settings',{'language':'zh-CN'})
        self.assertEqual(error.exception.code,403)
        self.fetch('/api/settings',{'language':'zh-CN'},{'X-Academic-Token':self.app.csrf});self.assertEqual(self.app.store.settings()['language'],'zh-CN')
    def test_foreign_origin_and_host_denied(self):
        for headers in [{'Origin':'https://evil.example'},{'Host':'evil.example'}]:
            with self.subTest(headers=headers),self.assertRaises(urllib.error.HTTPError) as error:self.fetch('/api/bootstrap',headers=headers)
            self.assertEqual(error.exception.code,403)
    def test_exports_preserve_notes_and_escape_csv_formulas(self):
        i=self.app.store.ingest(1,record(title='=TEST'))['id'];self.app.store.feedback(i,{'notes':'=SUM(A1:A2)'})
        _,data=self.fetch('/api/export?format=csv');self.assertIn("'=TEST",data.decode());self.assertIn("'=SUM",data.decode())
        _,data=self.fetch('/api/export');self.assertEqual(json.loads(data)['notes'],'=SUM(A1:A2)')
    def test_static_page_and_secrets_not_exposed(self):
        _,body=self.fetch('/');self.assertIn(b'AcademicUpdater',body)
        _,body=self.fetch('/api/bootstrap');self.assertNotIn(b'access_token',body);self.assertNotIn(b'refresh_token',body)
        with self.assertRaises(urllib.error.HTTPError) as error:self.fetch('/../data/credentials.dpapi')
        self.assertEqual(error.exception.code,404)

    def test_signin_endpoint_sends_uuid_urn(self):
        _,body=self.fetch('/api/auth/start',{}, {'X-Academic-Token':self.app.csrf})
        result=json.loads(body);parsed=urllib.parse.urlsplit(result['url']);query=urllib.parse.parse_qs(parsed.query)
        self.assertEqual(parsed.netloc,'auth.openai.com')
        self.assertEqual(parsed.path,'/api/accounts/authorize')
        self.assertEqual(query['ext_agent_host_id'],[self.app.store.get('host_id')])
        self.assertTrue(query['ext_agent_host_id'][0].startswith('urn:uuid:'))
        self.assertEqual(uuid.UUID(query['ext_agent_host_id'][0]).version,4)
        self.assertEqual(query['redirect_uri'],[self.url+'/auth/callback'])

if __name__=='__main__':unittest.main()
