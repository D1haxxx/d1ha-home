"""D1ha web interface."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from event_sink import visitor, safe_record
from feedback import save_feedback
from runtime import D1haChat
from google_signin import client_id, verify_credential, AuthError

HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', '8000'))
PUBLIC_ORIGIN = os.environ.get('PUBLIC_ORIGIN', '').rstrip('/')
PUBLIC_HOST = urlsplit(PUBLIC_ORIGIN).netloc
LOCAL_HOSTS = (f'127.0.0.1:{PORT}', f'localhost:{PORT}')
STATIC = Path(__file__).parent / 'website' / 'dist'
FILES = {'/logo.png': ('logo.png', 'image/png'), '/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
         '/styles.css': ('styles.css', 'text/css')}
MODEL = None
MODEL_LOCK = threading.Lock()
SESSION_LOCK = threading.Lock()
SESSIONS = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not log conversation text or cookies.

    def host_ok(self):
        return self.headers.get('Host') in LOCAL_HOSTS or bool(PUBLIC_HOST and self.headers.get('Host') == PUBLIC_HOST)

    def send(self, code, payload, content_type='application/json', cookie=None):
        if code>=500:
            safe_record('app_error','Website server returned HTTP '+str(code))
        data = json.dumps(payload).encode() if content_type=='application/json' else payload
        self.send_response(code)
        self.send_header('Content-Type', content_type+('; charset=utf-8' if not content_type.startswith('image/') else ''))
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' https://accounts.google.com/gsi/client; style-src 'self' https://accounts.google.com/gsi/style; connect-src 'self' https://accounts.google.com/gsi/; frame-src https://accounts.google.com/gsi/; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin-allow-popups')
        if cookie:
            secure = '; Secure' if PUBLIC_ORIGIN.startswith('https://') else ''
            self.send_header('Set-Cookie', f'd1ha_session={cookie}; HttpOnly; SameSite=Strict; Path=/{secure}')
        self.end_headers()
        self.wfile.write(data)

    def session(self):
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
            token = jar['d1ha_session'].value if 'd1ha_session' in jar else None
        except Exception:
            token = None
        now = time.monotonic()
        with SESSION_LOCK:
            for key in list(SESSIONS):
                if now-SESSIONS[key]['seen']>3600 or (SESSIONS[key].get('user') and time.time()>=SESSIONS[key].get('auth_until',0)):
                    del SESSIONS[key]
            if token not in SESSIONS:
                if len(SESSIONS)>=128:
                    oldest=min(SESSIONS,key=lambda k:SESSIONS[k]['seen'])
                    del SESSIONS[oldest]
                token=secrets.token_urlsafe(24)
                SESSIONS[token]=new_session()
            session=SESSIONS[token]
            session['seen']=now
        return token, session

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {'error':'Invalid host.'})
        path=urlsplit(self.path).path
        if path=='/healthz':
            return self.send(200, {'ok': True})
        if path=='/api/auth':
            token,session=self.session()
            return self.send(200,{'configured':bool(client_id()),'client_id':client_id(),
                'csrf':session['csrf'],'nonce':session['nonce'],'user':session.get('user')},cookie=token)
        if path=='/api/info':
            return self.send(200, {'version':MODEL.version, 'models':MODEL.MODEL_NAMES})
        if path not in FILES:
            return self.send(404, {'error':'Not found.'})
        name, content_type=FILES[path]
        self.send(200,(STATIC/name).read_bytes(),content_type)

    def do_POST(self):
        if not self.host_ok():
            return self.send(403, {'error':'Invalid host.'})
        origin=self.headers.get('Origin')
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.send(415, {'error':'JSON is required.'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192:
                return self.send(413, {'error':'Request is too large.'})
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):
                raise ValueError()
        except (ValueError,UnicodeError):
            return self.send(400, {'error':'Invalid request.'})
        if not origin or origin not in (PUBLIC_ORIGIN, *(f'http://{host}' for host in LOCAL_HOSTS)):
            return self.send(403, {'error':'Use the D1ha website.'})
        path=urlsplit(self.path).path
        if path in ('/api/auth/google','/api/auth/logout'):
            return self.authenticate(path,body)
        if path=='/api/event':
            token,session=self.session()
            csrf=body.get('csrf')
            if not isinstance(csrf,str) or not csrf.isascii() or not secrets.compare_digest(csrf,session['csrf']):
                return self.send(403,{'error':'Invalid event session.'},cookie=token)
            code=body.get('code')
            if code=='visit':
                identifier=body.get('visitor_id')
                if not isinstance(identifier,str) or not re.fullmatch(r'[a-f0-9-]{36}',identifier):
                    return self.send(400,{'error':'Invalid visitor identifier.'})
                try:visitor('website_visit',identifier)
                except (OSError,sqlite3.Error):return self.send(503,{'error':'Event logging unavailable.'})
            elif code in ('javascript_error','unhandled_promise','chat_request_failed'):
                safe_record('app_error','Website: '+code)
            else:return self.send(400,{'error':'Unknown event.'})
            return self.send(200,{'ok':True},cookie=token)
        if path=='/api/feedback':
            token,session=self.session()
            csrf=body.get('csrf')
            if not isinstance(csrf,str) or not csrf.isascii() or not secrets.compare_digest(csrf,session['csrf']):
                return self.send(403,{'error':'Refresh the page before submitting feedback.'},cookie=token)
            with session['lock']:
                if time.monotonic()-session.get('feedback_at',-30)<30:
                    return self.send(429,{'error':'Please wait 30 seconds before sending more feedback.'},cookie=token)
                model=body.get('model','d1ha')
                if not isinstance(model,str) or model not in MODEL.MODEL_NAMES:
                    return self.send(400,{'error':'Choose a valid model.'},cookie=token)
                try:
                    identifier=save_feedback(body.get('message'),body.get('rating'),body.get('category'),model)
                except ValueError as error:
                    return self.send(400,{'error':str(error)},cookie=token)
                except (OSError,sqlite3.Error):
                    return self.send(500,{'error':'Could not save feedback. Please try again.'},cookie=token)
                session['feedback_at']=time.monotonic()
            return self.send(201,{'ok':True,'id':identifier},cookie=token)
        if path not in ('/api/chat','/api/reset'):
            return self.send(404, {'error':'Not found.'})
        chat_id=body.get('chat_id','default')
        if not isinstance(chat_id,str) or (chat_id!='default' and not re.fullmatch(r'[a-f0-9-]{36}',chat_id)):
            return self.send(400,{'error':'Invalid conversation identifier.'})
        token, session=self.session()
        if 'account_key' in body and body['account_key']!=(session.get('user') or {}).get('account_key'):
            return self.send(401,{'error':'Your sign-in session changed or expired. Refresh the page to continue.'},cookie=token)
        if path=='/api/reset':
            with session['lock']:
                if chat_id=='default':
                    session['memory'].clear()
                else:
                    session.setdefault('conversations',{}).pop(chat_id,None)
            return self.send(200,{'ok':True},cookie=token)
        message=body.get('message','')
        model=body.get('model','d1ha')
        mode=body.get('mode','deep')
        if not isinstance(message,str) or not message.strip() or len(message)>1000:
            return self.send(400,{'error':'Send a message between 1 and 1,000 characters.'})
        if not isinstance(model,str) or model not in MODEL.MODEL_NAMES or mode not in ('light','deep'):
            return self.send(400,{'error':'Choose a valid model and mode.'})
        try:
            with session['lock'], MODEL_LOCK:
                if chat_id=='default':
                    memory=session['memory']
                else:
                    conversations=session.setdefault('conversations',{})
                    if chat_id not in conversations and len(conversations)>=25:
                        conversations.pop(next(iter(conversations)))
                    memory=conversations.setdefault(chat_id,{})
                memory.update(model=model,mode=mode)
                reply=MODEL.reply(message.strip(),memory)
                usage=dict(memory.get('usage',{}))
            self.send(200,{'reply':reply,'usage':usage,'unlimited':True},cookie=token)
        except Exception as error:
            print('Web request failed:',type(error).__name__,flush=True)
            self.send(500,{'error':'I could not finish that reply. Please try again.'},cookie=token)


    def authenticate(self,path,body):
        token,session=self.session()
        csrf=body.get('csrf')
        if not isinstance(csrf,str) or not csrf.isascii() or not secrets.compare_digest(csrf,session['csrf']):
            return self.send(403,{'error':'Sign-in request expired. Refresh the page and try again.'},cookie=token)
        if path=='/api/auth/logout':
            replacement=new_session()
        else:
            audience=client_id()
            if not audience:
                return self.send(503,{'error':'Google sign-in needs a Web client ID configured by the site owner.'})
            with session['lock']:
                if time.monotonic()-session.get('auth_attempt',0)<1:
                    return self.send(429,{'error':'Please wait a moment before trying sign-in again.'})
                session['auth_attempt']=time.monotonic()
                try:
                    user,until=verify_credential(body.get('credential'),audience,session['nonce'])
                except AuthError:
                    return self.send(401,{'error':'Google sign-in could not be verified. Try again.'})
            replacement=new_session()
            replacement.update(user=user,auth_until=until)
        # Rotate rather than upgrading an existing guest cookie. Guest chat
        # memory is not silently inherited by a different Google account.
        fresh=secrets.token_urlsafe(32)
        with SESSION_LOCK:
            SESSIONS.pop(token,None)
            SESSIONS[fresh]=replacement
        self.send(200,{'user':replacement.get('user')},cookie=fresh)


def new_session():
    return {'seen':time.monotonic(),'memory':{},'lock':threading.Lock(),
            'csrf':secrets.token_urlsafe(32),'nonce':secrets.token_urlsafe(32)}


def main():
    global MODEL
    MODEL=D1haChat()
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    server.daemon_threads=True
    print(f'D1ha {MODEL.version} website: http://{HOST}:{PORT}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    main()
