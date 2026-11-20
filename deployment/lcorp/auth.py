"""WeChat test-account flow. SQLite store is for local development only."""
import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class AuthError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Auth:
    def __init__(self, database, appid, secret, callback, exchange=None, clock=time.time):
        self.database, self.appid, self.secret, self.callback = str(database), appid, secret, callback
        self.exchange, self.clock = exchange or self._exchange, clock
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY, browser_hash TEXT NOT NULL, phone_hash TEXT,
                oauth_hash TEXT, confirm_hash TEXT, expires REAL NOT NULL,
                status TEXT NOT NULL, principal TEXT);
                CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, principal TEXT NOT NULL, expires REAL NOT NULL);''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def new(self, browser_secret):
        attempt = secrets.token_urlsafe(24)
        with self.connect() as db:
            db.execute('DELETE FROM attempts WHERE expires < ?', (self.clock() - 300,))
            db.execute('DELETE FROM sessions WHERE expires < ?', (self.clock(),))
            count = db.execute('SELECT count(*) FROM attempts WHERE browser_hash=? AND expires>?',
                               (digest(browser_secret), self.clock())).fetchone()[0]
            if count >= 10:
                raise AuthError('too_many_attempts')
            db.execute('INSERT INTO attempts(id,browser_hash,expires,status) VALUES(?,?,?,?)',
                       (attempt, digest(browser_secret), self.clock() + 180, 'pending'))
        return attempt

    def row(self, db, attempt):
        row = db.execute('SELECT * FROM attempts WHERE id=?', (attempt,)).fetchone()
        if not row or row['expires'] <= self.clock():
            raise AuthError('expired')
        return row

    def start(self, attempt, phone_secret):
        state = secrets.token_urlsafe(24)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.row(db, attempt)
            if row['status'] != 'pending' or row['oauth_hash']:
                raise AuthError('already_scanned')
            db.execute('UPDATE attempts SET oauth_hash=?,phone_hash=? WHERE id=?',
                       (digest(state), digest(phone_secret), attempt))
        return 'https://open.weixin.qq.com/connect/oauth2/authorize?' + urlencode({
            'appid': self.appid, 'redirect_uri': self.callback, 'response_type': 'code',
            'scope': 'snsapi_base', 'state': state}) + '#wechat_redirect'

    def _exchange(self, code):
        params = urlencode({'appid': self.appid, 'secret': self.secret, 'code': code,
                            'grant_type': 'authorization_code'})
        req = Request('https://api.weixin.qq.com/sns/oauth2/access_token?' + params,
                      headers={'Accept': 'application/json'})
        try:
            with build_opener(NoRedirect).open(req, timeout=15) as response:
                data = json.load(response)
            openid = data.get('openid', '')
            if data.get('errcode') or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', openid):
                raise AuthError('wechat_authorization_failed')
            return openid
        except Exception:
            raise AuthError('wechat_authorization_failed') from None

    def callback_result(self, state, code, phone_secret):
        if not state or len(state) > 128 or not code or len(code) > 512:
            raise AuthError('invalid_callback')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM attempts WHERE oauth_hash=?', (digest(state),)).fetchone()
            if not row or row['expires'] <= self.clock() or row['status'] != 'pending' or not secrets.compare_digest(row['phone_hash'] or '', digest(phone_secret)):
                raise AuthError('invalid_callback')
            attempt = row['id']
            db.execute("UPDATE attempts SET status='authorizing',oauth_hash=NULL WHERE id=?", (attempt,))
        try:
            principal = digest(self.appid + '|' + self.exchange(code))
        except Exception:
            with self.connect() as db:
                db.execute("UPDATE attempts SET status='failed' WHERE id=?", (attempt,))
            raise AuthError('wechat_authorization_failed') from None
        confirm = secrets.token_urlsafe(24)
        with self.connect() as db:
            self.row(db, attempt)
            db.execute("UPDATE attempts SET status='confirm',principal=?,confirm_hash=? WHERE id=?",
                       (principal, digest(confirm), attempt))
        return attempt, confirm

    def confirm(self, attempt, nonce, phone_secret):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.row(db, attempt)
            if row['status'] != 'confirm' or not secrets.compare_digest(row['confirm_hash'] or '', digest(nonce)) or not secrets.compare_digest(row['phone_hash'] or '', digest(phone_secret)):
                raise AuthError('invalid_confirmation')
            db.execute("UPDATE attempts SET status='approved',confirm_hash=NULL WHERE id=?", (attempt,))

    def status(self, attempt, browser_secret):
        with self.connect() as db:
            row = self.row(db, attempt)
            if not secrets.compare_digest(row['browser_hash'], digest(browser_secret)):
                raise AuthError('wrong_browser')
            return row['status']

    def complete(self, attempt, browser_secret):
        session = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.row(db, attempt)
            if row['status'] != 'approved' or not secrets.compare_digest(row['browser_hash'], digest(browser_secret)):
                raise AuthError('login_not_approved')
            db.execute("UPDATE attempts SET status='consumed' WHERE id=?", (attempt,))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (digest(session), row['principal'], self.clock() + 14400))
        return session

    def user(self, session):
        with self.connect() as db:
            row = db.execute('SELECT principal FROM sessions WHERE token_hash=? AND expires>?',
                             (digest(session), self.clock())).fetchone()
        return {'id': row['principal']} if row else None

    def logout(self, session):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (digest(session),))
