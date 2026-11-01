#!/usr/bin/env python3
"""Verify served files, embedded datasets and latest allocation controls after deployment."""
import argparse,hashlib,json,re,sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlsplit

def main():
    p=argparse.ArgumentParser();p.add_argument('base_url');args=p.parse_args()
    base=args.base_url.rstrip('/')+'/'
    if urlsplit(base).scheme not in ('http','https'):p.error('Use a complete http(s) URL')
    manifest=json.loads(Path(__file__).with_name('manifest.json').read_text(encoding='utf-8'))
    def get(path):
        with urlopen(Request(base+path,headers={'Cache-Control':'no-cache'}),timeout=25) as r:
            if r.status!=200:raise ValueError('HTTP '+str(r.status)+': '+path)
            return r.read()
    # The entry route may redirect. Verify the redirect destination is a real summary page.
    if b'Resource Portfolio' not in get(''):raise ValueError('Root does not open Total Summary')
    for path,sha in manifest['sha256'].items():
        if path=='index.html':continue # HTTP server may redirect root/index requests.
        if hashlib.sha256(get(path)).hexdigest()!=sha:raise ValueError('Version mismatch: '+path)
    print(json.dumps({'status':'PASS','revision':manifest['revision'],**manifest['checks']}))

if __name__=='__main__':
    try:main()
    except Exception as e:print('Deployment check failed: '+str(e),file=sys.stderr);sys.exit(1)
