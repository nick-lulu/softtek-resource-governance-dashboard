"""Backend-only shared WeChat state. Never expose the server key to the browser."""
import json
import re
import secrets
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from auth import Auth, AuthError, NoRedirect, digest


def private_config(path):
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class SupabaseAuth:
    _exchange = Auth._exchange

    def __init__(self, url, key, appid, secret, callback, exchange=None, enforce_access=False):
        if url.rstrip('/') != 'https://pxgygpodcgmvqfmkbmjb.supabase.co':
            raise ValueError('Unexpected Supabase project')
        if not key or not (key.startswith('sb_secret_') or key.startswith('eyJ')):
            raise ValueError('Supabase backend secret key missing or invalid')
        self.url, self.key = url.rstrip('/'), key
        self.appid, self.secret, self.callback = appid, secret, callback
        self.exchange = exchange or self._exchange
        self.enforce_access = enforce_access

    def _rpc(self, action, _function='wechat_login_rpc', **data):
        headers = {'apikey': self.key, 'Content-Type': 'application/json', 'Accept': 'application/json'}
        # New Supabase secret keys are not JWTs; only legacy JWT keys use Bearer.
        if self.key.startswith('eyJ'):
            headers['Authorization'] = 'Bearer ' + self.key
        assert _function in ('wechat_login_rpc','wechat_access_rpc','wechat_self_rpc','wechat_claim_rpc','wechat_admin_rpc')
        req = Request(self.url + '/rest/v1/rpc/' + _function,
                      data=json.dumps({'p_action': action, 'p_data': data}).encode(),
                      headers=headers, method='POST')
        try:
            with build_opener(NoRedirect).open(req, timeout=15) as response:
                return json.load(response)
        except HTTPError as error:
            # Do not leak upstream response details, keys or request headers.
            try:
                message = json.loads(error.read(4096)).get('message', '')
            except Exception:
                message = ''
            known = {'expired', 'wrong_browser', 'already_scanned', 'invalid_callback',
                     'invalid_confirmation', 'login_not_approved', 'too_many_attempts',
                     'invalid_attempt', 'invalid_browser', 'invalid_phone', 'invalid_state',
                     'invalid_session','access_not_approved','request_not_found',
                     'identity_already_bound','not_in_approved_cohort','admin_required','owner_protected',
                     'request_not_pending','email_not_allowed','invalid_email','invalid_name'}
            raise AuthError(message if message in known else 'login_store_unavailable') from None
        except Exception:
            raise AuthError('login_store_unavailable') from None

    def health(self):
        return self._rpc('health')

    def new(self, browser_secret):
        attempt = secrets.token_urlsafe(24)
        self._rpc('new', attempt=attempt, browser_hash=digest(browser_secret))
        return attempt

    def start(self, attempt, phone_secret):
        state = secrets.token_urlsafe(24)
        self._rpc('start', attempt=attempt, state_hash=digest(state), phone_hash=digest(phone_secret))
        return 'https://open.weixin.qq.com/connect/oauth2/authorize?' + urlencode({
            'appid': self.appid, 'redirect_uri': self.callback, 'response_type': 'code',
            'scope': 'snsapi_base', 'state': state}) + '#wechat_redirect'

    def callback_result(self, state, code, phone_secret):
        if not state or len(state) > 128 or not code or len(code) > 512:
            raise AuthError('invalid_callback')
        attempt = self._rpc('claim', state_hash=digest(state), phone_hash=digest(phone_secret))['attempt']
        try:
            openid = self.exchange(code)
            if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', openid):
                raise ValueError()
            principal = digest(self.appid + '|' + openid)
        except Exception:
            self._rpc('fail', attempt=attempt)
            raise AuthError('wechat_authorization_failed') from None
        nonce = secrets.token_urlsafe(24)
        self._rpc('finish', attempt=attempt, principal_hash=principal, confirm_hash=digest(nonce))
        if self.enforce_access:
            self._access('request', principal_hash=principal)
        return attempt, nonce

    def confirm(self, attempt, nonce, phone_secret):
        self._rpc('confirm', attempt=attempt, confirm_hash=digest(nonce), phone_hash=digest(phone_secret))

    def status(self, attempt, browser_secret):
        return self._rpc('status', attempt=attempt, browser_hash=digest(browser_secret))['status']

    def _access(self, action, **data):
        return self._rpc(action, _function='wechat_access_rpc', **data)

    def status_info(self, attempt, browser_secret):
        status = self.status(attempt, browser_secret)
        if self.enforce_access and status == 'approved':
            access = self._access('attempt', attempt=attempt, browser_hash=digest(browser_secret))
            if access['status'] != 'approved':
                return {'status': 'access_denied' if access['status'] in ('revoked','rejected') else 'access_pending',
                        'requestCode': access.get('requestCode','')}
        return {'status':status}

    def phone_session(self, attempt, phone_secret):
        if not self.enforce_access:
            return None
        access = self._access('phone', attempt=attempt, phone_hash=digest(phone_secret))
        if access['status'] != 'approved':
            return access
        session = secrets.token_urlsafe(32)
        self._access('phone_session', attempt=attempt, phone_hash=digest(phone_secret), session_hash=digest(session))
        return {'status':'approved','session':session}

    def complete(self, attempt, browser_secret):
        if self.enforce_access and self.status_info(attempt,browser_secret)['status'] != 'approved':
            raise AuthError('access_not_approved')
        session = secrets.token_urlsafe(32)
        self._rpc('complete', attempt=attempt, browser_hash=digest(browser_secret), session_hash=digest(session))
        return session

    def user(self, session):
        if self.enforce_access:
            return self._rpc('me',_function='wechat_self_rpc',session_hash=digest(session)) if session else None
        user = self._rpc('user', session_hash=digest(session)) if session else None
        return user

    def claim(self, attempt, phone_secret, email):
        return self._rpc('submit',_function='wechat_claim_rpc',attempt=attempt,
                         phone_hash=digest(phone_secret),email=email)

    def admin(self, action, session, **data):
        return self._rpc(action,_function='wechat_admin_rpc',session_hash=digest(session),**data)

    def logout(self, session):
        if session:
            self._rpc('logout', session_hash=digest(session))
