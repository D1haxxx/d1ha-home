"""Google Identity Services ID-token verification; no client secret is needed."""
from pathlib import Path
import hashlib
import json
import os
import re
import secrets
import time
from google.oauth2 import id_token
from google.auth.transport.requests import Request


class AuthError(Exception):
    pass


def client_id():
    value=os.environ.get('GOOGLE_CLIENT_ID','').strip()
    path=Path(__file__).with_name('auth_config.json')
    if not value and path.exists():
        try: value=json.loads(path.read_text(encoding='utf-8-sig')).get('google_client_id','').strip()
        except (ValueError,AttributeError,OSError): return ''
    return value if re.fullmatch(r'[A-Za-z0-9_-]+\.apps\.googleusercontent\.com',value) else ''


def certificate_request(url,method='GET',body=None,headers=None,**kwargs):
    return Request()(url,method=method,body=body,headers=headers,timeout=10)


def verify_credential(credential,audience,nonce):
    if not isinstance(credential,str) or not 100<=len(credential)<=7000:
        raise AuthError('Invalid Google credential.')
    try:
        claims=id_token.verify_oauth2_token(credential,certificate_request,audience=audience)
        valid=(claims.get('iss') in ('accounts.google.com','https://accounts.google.com')
               and claims.get('aud')==audience and float(claims.get('exp',0))>time.time()
               and isinstance(claims.get('sub'),str) and 0<len(claims['sub'])<=255
               and claims.get('email_verified') is True
               and isinstance(claims.get('email'),str)
               and isinstance(claims.get('nonce'),str)
               and secrets.compare_digest(claims['nonce'],nonce))
        if not valid: raise AuthError('Google credential did not pass verification.')
    except AuthError: raise
    except Exception as error:
        raise AuthError('Google sign-in could not be verified. Try again.') from error
    return {'account_key':hashlib.sha256((audience+':'+claims['sub']).encode()).hexdigest()[:32],
            'name':str(claims.get('name') or claims['email'].split('@')[0])[:80],
            'email':claims['email'][:254]}, min(float(claims['exp']),time.time()+3600)
