"""User-bound Windows DPAPI storage and OIDC validation."""
from __future__ import annotations
import base64
import ctypes
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.parse
import uuid
from pathlib import Path
from .network import AppError,get_json,post_form,request


class Blob(ctypes.Structure):
    _fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_ubyte))]


def protect(value,decrypt=False):
    if os.name!='nt':raise AppError('secure_storage_unavailable','Use environment credentials on this platform.')
    buffer=ctypes.create_string_buffer(value)
    src=Blob(len(value),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));out=Blob()
    fn=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(src),None,None,None,None,1,ctypes.byref(out)):raise AppError('credential_storage_error')
    try:return ctypes.string_at(out.data,out.size)
    finally:ctypes.windll.kernel32.LocalFree(out.data)


class Vault:
    def __init__(self,directory):
        self.path=Path(directory)/'credentials.dpapi';self.lock=threading.RLock()
        self.memory={}
        if self.path.exists():
            try:self.memory=json.loads(protect(self.path.read_bytes(),True))
            except Exception:raise AppError('credential_storage_error','Credentials belong to another OS account or cannot be decrypted.')

    def get(self,key,default=None):
        with self.lock:return self.memory.get(key,default)

    def set(self,key,value):
        with self.lock:
            changed={**self.memory,key:value}
            blob=protect(json.dumps(changed).encode())
            temporary=self.path.with_suffix('.tmp');temporary.write_bytes(blob);os.replace(temporary,self.path)
            self.memory=changed


def b64(value):return base64.urlsafe_b64decode(value+'='*(-len(value)%4))


def validate_id_token(token,jwks,client_id,nonce,expected_sub=None):
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa,padding,ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        head,payload,sig=token.split('.')
        header=json.loads(b64(head));claims=json.loads(b64(payload));signature=b64(sig)
        key=next(k for k in jwks['keys'] if k.get('kid')==header.get('kid') and k.get('use','sig')=='sig')
        algorithm=header['alg']
        if key.get('alg',algorithm)!=algorithm:raise ValueError()
        if algorithm=='RS256' and key['kty']=='RSA':
            public=rsa.RSAPublicNumbers(int.from_bytes(b64(key['e']),'big'),int.from_bytes(b64(key['n']),'big')).public_key()
            public.verify(signature,(head+'.'+payload).encode(),padding.PKCS1v15(),hashes.SHA256())
        elif algorithm=='ES256' and key['kty']=='EC' and key['crv']=='P-256' and len(signature)==64:
            public=ec.EllipticCurvePublicNumbers(int.from_bytes(b64(key['x']),'big'),int.from_bytes(b64(key['y']),'big'),ec.SECP256R1()).public_key()
            public.verify(encode_dss_signature(int.from_bytes(signature[:32],'big'),int.from_bytes(signature[32:],'big')),(head+'.'+payload).encode(),ec.ECDSA(hashes.SHA256()))
        else:raise ValueError()
        aud=claims.get('aud',[]);aud=[aud] if isinstance(aud,str) else aud
        if claims.get('iss')!='https://auth.openai.com' or client_id not in aud or claims.get('exp',0)<=time.time() or claims.get('nbf',0)>time.time()+30 or claims.get('nonce')!=nonce or not claims.get('sub'):raise ValueError()
        if len(aud)>1 and claims.get('azp')!=client_id:raise ValueError()
        if expected_sub and claims['sub']!=expected_sub:raise ValueError()
        return claims
    except ImportError as exc:raise AppError('crypto_dependency_missing','Install the requirements file to enable ChatGPT sign-in.') from exc
    except Exception as exc:raise AppError('invalid_identity_token','OpenAI identity could not be verified.',401) from exc


class OAuth:
    RESOURCE='https://api.openai.com/v1'
    TOKEN='https://auth.openai.com/api/accounts/oauth/token'
    def __init__(self,vault,store):
        self.vault,self.store=vault,store;self.pending={};self.lock=threading.RLock()
        self.last_error=''
        host_id=store.get('host_id')
        if not host_id:
            # SIWC accepts UUID URNs, not bare UUID strings. Keep one per installation.
            store.put('host_id',uuid.uuid4().urn)
        elif isinstance(host_id,str) and not host_id.startswith(('urn:','did:')):
            try:legacy_id=uuid.UUID(host_id)
            except ValueError:pass
            else:
                # Migrate 1.0.0 without replacing the installation's UUID or accounts.
                store.put('host_id',legacy_id.urn)

    def accounts(self):
        result=[];active=self.vault.get('active_account')
        for client,r in self.vault.get('accounts',{}).items():
            result.append({'id':client,'label':r.get('email') or r.get('sub','Account'),'active':client==active,'connected':bool(r.get('access_token')),'plan_enabled':'chatgpt.tokens.use.direct' in r.get('scope','').split()})
        return result

    def start(self,port,account_id=None):
        with self.lock:
            account=self.vault.get('accounts',{}).get(account_id) if account_id else None
            if account_id and not account:raise AppError('unknown_account')
            verifier=secrets.token_urlsafe(48);state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32)
            callback=f'http://127.0.0.1:{port}/auth/callback'
            client=account_id or 'dynamic_agent_client'
            self.pending={k:v for k,v in self.pending.items() if v['expires']>time.time()}
            self.pending[state]={'verifier':verifier,'nonce':nonce,'callback':callback,'client':client,'sub':account.get('sub') if account else None,'expires':time.time()+600}
            query={'client_id':client,'ext_agent_host_id':self.store.get('host_id'),'response_type':'code','redirect_uri':callback,'scope':'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct','resource':self.RESOURCE,'state':state,'nonce':nonce,'code_challenge_method':'S256','code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
            if not account:query['agent_name_hint']='AcademicUpdater'
            elif account.get('email'):query['login_hint']=account['email']
            self.last_error=''
            return 'https://auth.openai.com/api/accounts/authorize?'+urllib.parse.urlencode(query)

    def callback(self,query):
        with self.lock:
            state=query.get('state','');attempt=self.pending.pop(state,None)
        if not attempt or attempt['expires']<time.time():raise AppError('invalid_oauth_state',status=401)
        if query.get('error'):raise AppError('oauth_denied','OpenAI authorization was declined or unavailable.',401)
        client=query.get('client_id') or attempt['client']
        if client=='dynamic_agent_client' or not client.startswith('oaiapp_') or (attempt['client']!='dynamic_agent_client' and client!=attempt['client']):raise AppError('invalid_oauth_client',status=401)
        token=post_form(self.TOKEN,{'grant_type':'authorization_code','client_id':client,'code':query.get('code',''),'code_verifier':attempt['verifier'],'redirect_uri':attempt['callback'],'resource':self.RESOURCE})
        claims=validate_id_token(token.get('id_token',''),get_json('https://auth.openai.com/.well-known/jwks.json'),client,attempt['nonce'],attempt['sub'])
        account={**token,'client_id':client,'sub':claims['sub'],'email':claims.get('email',''),'expires_at':time.time()+int(token.get('expires_in',3600))}
        with self.lock:
            accounts={**self.vault.get('accounts',{}),client:account};self.vault.set('accounts',accounts);self.vault.set('active_account',client)
        return 'chatgpt.tokens.use.direct' in account.get('scope','').split()

    def select(self,client):
        if client not in self.vault.get('accounts',{}):raise AppError('unknown_account')
        self.vault.set('active_account',client)

    def access_token(self):
        with self.lock:
            client=self.vault.get('active_account');accounts=self.vault.get('accounts',{});a=accounts.get(client)
            if not a or not a.get('access_token'):raise AppError('ai_not_connected')
            if 'chatgpt.tokens.use.direct' not in a.get('scope','').split():raise AppError('subscription_not_authorized')
            if a['expires_at']<time.time()+90:
                if not a.get('refresh_token'):raise AppError('sign_in_again',status=401)
                token=post_form(self.TOKEN,{'grant_type':'refresh_token','client_id':client,'refresh_token':a['refresh_token'],'resource':self.RESOURCE})
                a={**a,**token,'expires_at':time.time()+int(token.get('expires_in',3600))}
                if 'chatgpt.tokens.use.direct' not in a.get('scope','').split():raise AppError('subscription_not_authorized')
                self.vault.set('accounts',{**accounts,client:a})
            return a['access_token']

    def disconnect(self,client):
        with self.lock:
            accounts=self.vault.get('accounts',{});a=accounts.get(client)
            if not a:raise AppError('unknown_account')
            confirmed=False
            if a.get('refresh_token'):
                try:
                    endpoint=get_json('https://auth.openai.com/.well-known/openid-configuration').get('revocation_endpoint','')
                    if urllib.parse.urlsplit(endpoint).hostname!='auth.openai.com':raise AppError('invalid_auth_endpoint')
                    request(endpoint,data=urllib.parse.urlencode({'token':a['refresh_token'],'token_type_hint':'refresh_token','client_id':client}).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'})
                    confirmed=True
                except AppError:pass
            accounts[client]={k:v for k,v in a.items() if k not in ('access_token','refresh_token','id_token')}
            self.vault.set('accounts',accounts)
            if self.vault.get('active_account')==client:self.vault.set('active_account',None)
            return confirmed
