"""Local-only WeChat login prototype. No dashboard access restrictions are changed."""
from pathlib import Path
import html
import io
import json
import base64
import gzip
import re
import secrets
import sys
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from auth import Auth, AuthError
from supabase_auth import SupabaseAuth, private_config

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
import qrcode
import qrcode.image.svg


def settings():
    values = {}
    for line in (ROOT / 'private/wechat-test.env').read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    if values.get('WECHAT_APP_SECRET', '') in ('', 'PASTE_APPSECRET_HERE'):
        raise RuntimeError('WeChat private configuration incomplete')
    if values.get('WECHAT_CALLBACK_URL') != 'https://lcorp.msofttek.com/auth/wechat/callback':
        raise RuntimeError('Unexpected callback URL')
    return values


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # OAuth query strings contain short-lived codes; never log them.
        print(self.command, urlsplit(self.path).path, flush=True)

    def cookie(self, key):
        try:
            value = SimpleCookie(self.headers.get('Cookie', '')).get(key)
            return value.value if value else ''
        except Exception:
            return ''

    def set_cookie(self, key, value, age, path=None):
        cookie = SimpleCookie()
        cookie[key] = value
        cookie[key]['path'] = path or ('/' if key=='wx_session' else '/auth/wechat')
        cookie[key]['httponly'] = True
        cookie[key]['samesite'] = 'Lax' if key == 'wx_phone' else 'Strict'
        cookie[key]['max-age'] = age
        if self.server.origin.startswith('https://'):
            cookie[key]['secure'] = True
        return cookie.output(header='').strip()

    def send(self, code, data, kind='application/json; charset=utf-8', headers=None):
        body = json.dumps(data).encode() if isinstance(data, dict) else data.encode() if isinstance(data, str) else data
        compressed=False
        if len(body)>1024 and any(p.strip().split(';')[0]=='gzip' and not re.search(r';\s*q=0(?:\.0*)?\s*$',p) for p in self.headers.get('Accept-Encoding','').split(',')):
            body=gzip.compress(body,compresslevel=5,mtime=0)
            compressed=True
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Vary','Accept-Encoding')
        if compressed:self.send_header('Content-Encoding','gzip')
        self.send_header('Cache-Control', 'no-store')
        # Form navigation POSTs serialize Origin as null under no-referrer.
        # Keep the origin for the phone confirmation, without exposing OAuth query strings.
        self.send_header('Referrer-Policy', 'strict-origin')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def page(self, title, content):
        return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><link rel="stylesheet" href="/auth/wechat/style.css"><main class="panel"><div class="brand">Q4 RESOURCE PLANNING</div><h1>'+html.escape(title)+'</h1>'+content+'</main></html>'

    def qr_svg(self,attempt):
        image=qrcode.make(self.server.public_origin+'/auth/wechat/start?attempt='+attempt,
                          image_factory=qrcode.image.svg.SvgPathFillImage)
        out=io.BytesIO();image.save(out)
        return out.getvalue()

    def do_HEAD(self):
        self.send(405, {'error': 'method_not_allowed'})

    def do_GET(self):
        path = urlsplit(self.path).path
        query = parse_qs(urlsplit(self.path).query)
        value = lambda key: query.get(key, [''])[0]
        auth = self.server.auth
        try:
            if path in ('/', '/auth/wechat/login'):
                return self.send(200, (ROOT/'login.html').read_bytes(), 'text/html; charset=utf-8')
            if path in ('/auth/wechat/style.css', '/auth/wechat/login.js','/auth/wechat/navigation.js','/auth/wechat/navigation.css'):
                filename, mime = (path.rsplit('/',1)[1], 'text/css' if path.endswith('.css') else 'text/javascript')
                return self.send(200, (ROOT/filename).read_bytes(), mime+'; charset=utf-8')
            if path == '/auth/wechat/config':
                return self.send(200, {'configured': True, 'mode': 'test', 'callbackDeployed': bool(getattr(self.server, 'callback_ready', False))})
            if path == '/auth/wechat/qr':
                attempt = value('attempt')
                auth.status(attempt, self.cookie('wx_browser'))
                return self.send(200, self.qr_svg(attempt), 'image/svg+xml')
            if path == '/auth/wechat/start':
                if 'MicroMessenger' not in self.headers.get('User-Agent', ''):
                    return self.send(400, self.page('Open in WeChat', '<p>Scan the QR code with WeChat on your phone.</p>'), 'text/html; charset=utf-8')
                phone = secrets.token_urlsafe(32)
                url = auth.start(value('attempt'), phone)
                return self.send(302, b'', headers=[('Location', url), ('Set-Cookie', self.set_cookie('wx_phone', phone, 180))])
            if path == '/auth/wechat/callback':
                attempt, nonce = auth.callback_result(value('state'), value('code'), self.cookie('wx_phone'))
                form = '<p>Approve signing in to the computer that displayed this QR code. Only confirm if you started this login.</p><form method="post" action="/auth/wechat/confirm"><input type="hidden" name="attempt" value="'+html.escape(attempt,quote=True)+'"><input type="hidden" name="nonce" value="'+html.escape(nonce,quote=True)+'"><button>Confirm computer sign-in</button></form><p>You can close this page to cancel.</p>'
                return self.send(200, self.page('Confirm sign-in', form), 'text/html; charset=utf-8')
            if path == '/auth/wechat/status':
                info = auth.status_info(value('attempt'),self.cookie('wx_browser')) if hasattr(auth,'status_info') else {'status':auth.status(value('attempt'),self.cookie('wx_browser'))}
                return self.send(200, info)
            if path == '/auth/wechat/me':
                user = auth.user(self.cookie('wx_session'))
                return self.send(200, {'authenticated': bool(user), 'user': user})
            return self.send(404, {'error': 'not_found'})
        except AuthError as error:
            if path in ('/auth/wechat/callback', '/auth/wechat/start'):
                return self.send(400, self.page('Login could not complete', '<p>The QR code has expired, was already used, or authorization failed. Generate a new code on your computer.</p>'), 'text/html; charset=utf-8')
            return self.send(400, {'error': str(error)})
        except Exception:
            return self.send(500, {'error': 'login_service_unavailable'})

    def do_POST(self):
        path = urlsplit(self.path).path
        # Bind changes to this browser origin; never accept cross-site completion.
        if self.headers.get('Origin') != self.server.origin:
            return self.send(403, {'error': 'origin_not_allowed'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 4096:
                return self.send(413, {'error': 'request_too_large'})
            raw = self.rfile.read(size).decode()
            form = path in ('/auth/wechat/confirm','/auth/wechat/request-access')
            data = {key: values[0] for key, values in parse_qs(raw).items()} if form else json.loads(raw or '{}')
            if not isinstance(data, dict):
                raise ValueError()
            auth = self.server.auth
            if path == '/auth/wechat/attempt':
                if auth.user(self.cookie('wx_session')):
                    return self.send(200,{'authenticated':True})
                browser = self.cookie('wx_browser') or secrets.token_urlsafe(32)
                attempt = auth.new(browser)
                return self.send(200, {'attempt': attempt, 'expiresIn': 180,
                    'callbackDeployed':bool(getattr(self.server,'callback_ready',False)),
                    'qrBase64':base64.b64encode(self.qr_svg(attempt)).decode('ascii')},
                    headers=[('Set-Cookie', self.set_cookie('wx_browser', browser, 180))])
            if path == '/auth/wechat/confirm':
                auth.confirm(data.get('attempt', ''), data.get('nonce', ''), self.cookie('wx_phone'))
                if getattr(auth,'enforce_access',False):
                    access = auth.phone_session(data.get('attempt',''),self.cookie('wx_phone'))
                    headers=[]
                    if access['status']!='approved':
                        if access['status'] in ('revoked','rejected'):
                            return self.send(403,self.page('Access unavailable','<p>Your access has been declined or disabled. Contact Nick Han.</p>'),'text/html; charset=utf-8')
                        message = '<p>Your WeChat sign-in request has been received. Nick Han will assign your account and approve access in the administration page.</p><p>No email or request code is needed from you. After approval, scan again to enter the dashboard.</p>'
                        return self.send(200,self.page('Waiting for administrator approval',message),'text/html; charset=utf-8',headers)
                    headers.extend([('Set-Cookie',self.set_cookie('wx_phone','',0)),('Set-Cookie',self.set_cookie('wx_session','',0,path='/auth/wechat')),('Set-Cookie',self.set_cookie('wx_session',access['session'],14400))])
                    return self.send(200,self.page('Sign-in approved','<meta http-equiv="refresh" content="1;url=/"><p>Opening your dashboard…</p><p><a href="/">Continue to dashboard</a></p>'),'text/html; charset=utf-8',headers)
                return self.send(200, self.page('Sign-in approved', '<p>Return to your computer. The dashboard will open automatically there. You can close this page.</p>'), 'text/html; charset=utf-8', [('Set-Cookie', self.set_cookie('wx_phone', '', 0))])
            if path == '/auth/wechat/request-access':
                return self.send(200,self.page('Waiting for administrator approval','<p>Email entry is no longer required. Nick Han manages account assignment and approval in the administration page.</p>'),'text/html; charset=utf-8')
            if path == '/auth/wechat/complete':
                session = auth.complete(data.get('attempt', ''), self.cookie('wx_browser'))
                return self.send(200, {'authenticated': True}, headers=[('Set-Cookie', self.set_cookie('wx_session','',0,path='/auth/wechat')),('Set-Cookie', self.set_cookie('wx_session', session, 14400)), ('Set-Cookie', self.set_cookie('wx_browser', '', 0))])
            if path == '/auth/wechat/logout':
                auth.logout(self.cookie('wx_session'))
                return self.send(200, {'authenticated': False}, headers=[('Set-Cookie',self.set_cookie('wx_session','',0,path='/auth/wechat')),('Set-Cookie', self.set_cookie('wx_session', '', 0))])
            return self.send(404, {'error': 'not_found'})
        except AuthError as error:
            return self.send(400, {'error': str(error)})
        except Exception:
            return self.send(400, {'error': 'invalid_request'})


if __name__ == '__main__':
    config = settings()
    server = ThreadingHTTPServer(('127.0.0.1', 8110), Handler)
    server.origin = 'http://127.0.0.1:8110'
    callback = urlsplit(config['WECHAT_CALLBACK_URL'])
    server.public_origin = callback.scheme+'://'+callback.netloc
    shared = private_config(ROOT/'private/supabase.env')
    server.auth = SupabaseAuth(shared.get('SUPABASE_URL', ''), shared.get('SUPABASE_SECRET_KEY', ''),
                               config['WECHAT_APP_ID'], config['WECHAT_APP_SECRET'], config['WECHAT_CALLBACK_URL'])
    if server.auth.health() != {'version': 1, 'ready': True}:
        raise RuntimeError('Shared login store not ready')
    print('Local WeChat login prototype: http://127.0.0.1:8110/auth/wechat/login', flush=True)
    print('Cloud callback is not deployed. This prototype does not restrict dashboard access.', flush=True)
    server.serve_forever()
