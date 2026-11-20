"""Private FC integration: test login routes alongside the existing dashboard."""
import os
from concurrent.futures import Future
from http.server import ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlsplit
from dashboard_server import Handler as DashboardHandler, FILES
from wx_http import Handler as WeChatHandler
from supabase_auth import SupabaseAuth
from access_http import AccessMixin

ORIGIN = 'https://lcorp.msofttek.com'
CALLBACK = ORIGIN + '/auth/wechat/callback'
_session_checks = {}
_session_lock = Lock()


def check_dashboard_session(auth, session):
    """Share only in-flight checks for simultaneous dashboard requests."""
    if auth is None or not session:
        return False
    key = (auth, session)
    with _session_lock:
        check = _session_checks.get(key)
        if check is None:
            check = Future()
            _session_checks[key] = check
            leader = True
        else:
            leader = False
    if not leader:
        return check.result()
    try:
        allowed = bool(auth.user(session))
    except Exception:
        allowed = False
    finally:
        with _session_lock:
            _session_checks.pop(key)
            check.set_result(allowed)
    return allowed


class Handler(AccessMixin, WeChatHandler, DashboardHandler):
    protocol_version = 'HTTP/1.1'

    def send_header(self, keyword, value):
        if self.server.enforce_access and keyword.lower()=='cache-control':
            value='private, no-store'
        super().send_header(keyword,value)

    def has_access(self):
        if not self.server.enforce_access:
            return True
        return check_dashboard_session(self.server.auth, self.cookie('wx_session'))

    def protected_get(self):
        target=urlsplit(self.path).path
        if target!='/healthz' and not self.has_access():
            if target.startswith('/api/'):
                return self.send(401,{'error':'authentication_required'})
            return self.send(302,b'',headers=[('Location','/auth/wechat/login')])
        return DashboardHandler.do_GET(self)

    def do_HEAD(self):
        if urlsplit(self.path).path.startswith('/auth/wechat/'):
            self.send(405, {'error': 'method_not_allowed'})
        else:
            self.protected_get()

    def do_GET(self):
        path=urlsplit(self.path).path
        if path in ('/access','/access/') or path.startswith('/access/') or path.startswith('/api/v1/access/'):
            return self.access_get(path)
        if urlsplit(self.path).path.startswith('/auth/wechat/'):
            if self.server.auth is None:
                return self.send(503, {'error': 'login_not_configured'})
            return WeChatHandler.do_GET(self)
        return self.protected_get()

    def do_POST(self):
        if urlsplit(self.path).path.startswith('/api/v1/access/'):
            return self.access_post(urlsplit(self.path).path)
        if not urlsplit(self.path).path.startswith('/auth/wechat/'):
            return self.send(404, {'error': 'not_found'})
        if self.server.auth is None:
            return self.send(503, {'error': 'login_not_configured'})
        return WeChatHandler.do_POST(self)


if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('FC_SERVER_PORT', os.environ.get('PORT', '9000')))), Handler)
    server.origin = server.public_origin = ORIGIN
    server.auth = None
    server.callback_ready = False
    server.enforce_access = os.environ.get('WECHAT_ENFORCE_ACCESS') == 'true'
    # Failed or missing login config must not take the existing dashboard offline.
    if os.environ.get('WECHAT_LOGIN_ENABLED') == 'true':
        try:
            if os.environ.get('WECHAT_CALLBACK_URL') != CALLBACK:
                raise ValueError('Unexpected callback')
            server.auth = SupabaseAuth(os.environ.get('SUPABASE_URL', ''), os.environ.get('SUPABASE_SECRET_KEY', ''),
                os.environ.get('WECHAT_APP_ID', ''), os.environ.get('WECHAT_APP_SECRET', ''), CALLBACK,
                enforce_access=server.enforce_access)
            if not server.auth.appid or not server.auth.secret:
                raise ValueError('Missing WeChat configuration')
            server.callback_ready = True
        except Exception:
            server.auth = None
    print('Dashboard ready; access enforcement '+('enabled' if server.enforce_access else 'disabled')+'.', flush=True)
    server.serve_forever()
