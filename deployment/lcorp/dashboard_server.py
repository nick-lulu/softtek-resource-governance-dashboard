"""Dependency-free static dashboard service for an Alibaba FC custom runtime."""
import gzip
import hashlib
import mimetypes
import os
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from timesheet import PROJECT_MONTHS, TimesheetService
from portfolio_jira import JiraService

ROOT = Path(__file__).resolve().parent / 'site'
TIMESHEET = TimesheetService(ROOT)
JIRA = JiraService(ROOT)
FILES = {}
for path in ROOT.rglob('*'):
    if not path.is_file():
        continue
    raw = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    if path.suffix == '.js':
        mime = 'text/javascript'
    if mime.startswith('text/') or mime == 'application/json':
        mime += '; charset=utf-8'
    compressed = gzip.compress(raw, compresslevel=6, mtime=0) if len(raw) > 1024 else None
    FILES['/' + path.relative_to(ROOT).as_posix()] = (raw, compressed, mime)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def do_HEAD(self):
        self.do_GET()

    def timesheet_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_GET(self):
        request = urlsplit(self.path)
        target = unquote(request.path)
        if target == '/api/v1/portfolio/jira':
            body = json.dumps(JIRA.read(refresh=self.command != 'HEAD', wait=self.command != 'HEAD'), ensure_ascii=False, allow_nan=False).encode('utf8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
            return
        if target in ('/api/v1/timesheet/status', '/api/v1/timesheet/actuals'):
            data = TIMESHEET.read(fetch=target.endswith('/actuals') and self.command != 'HEAD')
            self.timesheet_response(data)
            return
        if target == '/api/v1/timesheet/projects':
            query = parse_qs(request.query, keep_blank_values=True)
            keys = query.get('resourceKey', [])
            if len(keys) != 1 or keys[0] not in TIMESHEET.roster:
                self.timesheet_response({'error': 'unknown_resource'}, 404)
                return
            months = query.get('month', [])
            if months and (len(months) != 1 or months[0] not in PROJECT_MONTHS):
                self.timesheet_response({'error': 'invalid_month'}, 400)
                return
            self.timesheet_response(TIMESHEET.read_projects(
                keys[0], fetch=self.command != 'HEAD', month=months[0] if months else None))
            return
        if target == '/':
            self.send_response(302)
            self.send_header('Location', '/summary/')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if any(p in ('.', '..') for p in target.split('/')) or '\\' in target:
            self.send_error(404)
            return
        if target == '/healthz':
            entry = FILES.get('/healthz', (b'ok\n', None, 'text/plain; charset=utf-8'))
        else:
            key = target + 'index.html' if target.endswith('/') else target
            if key not in FILES and target + '/index.html' in FILES:
                self.send_response(308)
                self.send_header('Location', target + '/')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            entry = FILES.get(key)
        if entry is None:
            self.send_error(404)
            return
        raw, compressed, mime = entry
        accepts_gzip = any(part.strip().split(';')[0] == 'gzip' and 'q=0' not in part
                           for part in self.headers.get('Accept-Encoding', '').split(','))
        use_gzip = compressed is not None and accepts_gzip
        body = compressed if use_gzip else raw
        etag = '"' + hashlib.sha256(body).hexdigest() + '"'
        unchanged = self.headers.get('If-None-Match') == etag
        self.send_response(304 if unchanged else 200)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('ETag', etag)
        self.send_header('Vary', 'Accept-Encoding')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        if use_gzip:
            self.send_header('Content-Encoding', 'gzip')
        if not unchanged:
            self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD' and not unchanged:
            self.wfile.write(body)


if __name__ == '__main__':
    port = int(os.environ.get('FC_SERVER_PORT', os.environ.get('PORT', '9000')))
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(f'Dashboard ready on port {port}; {len(FILES)} files', flush=True)
    server.serve_forever()
