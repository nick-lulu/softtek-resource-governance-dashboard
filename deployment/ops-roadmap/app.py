"""Standalone SCM Ops dashboard for Alibaba FC, Python 3.10+, port 9000."""
import gzip
import hashlib
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent / 'site'
FILES = {}
for path in ROOT.iterdir():
    if path.is_file():
        raw = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        if path.suffix == '.js':
            mime = 'text/javascript'
        if mime.startswith('text/') or mime == 'application/json':
            mime += '; charset=utf-8'
        FILES['/' + path.name] = (raw, gzip.compress(raw, mtime=0), mime,
                                 '"' + hashlib.sha256(raw).hexdigest() + '"')


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        target = unquote(urlsplit(self.path).path)
        if target == '/healthz':
            entry = (b'ok\n', None, 'text/plain', '"health"')
        else:
            entry = FILES.get('/index.html' if target == '/' else target)
        if not entry:
            self.send_error(404)
            return
        raw, compressed, mime, etag = entry
        use_gzip = compressed and 'gzip' in self.headers.get('Accept-Encoding', '')
        body = compressed if use_gzip else raw
        etag = etag[:-1] + '-gzip"' if use_gzip else etag
        match = self.headers.get('If-None-Match') == etag
        self.send_response(304 if match else 200)
        self.send_header('ETag', etag)
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Vary', 'Accept-Encoding')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if not match:
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            if use_gzip:
                self.send_header('Content-Encoding', 'gzip')
        self.end_headers()
        if not match and self.command != 'HEAD':
            self.wfile.write(body)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '9000'))), Handler).serve_forever()
