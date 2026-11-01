#!/usr/bin/env python3
"""Build the standalone Q4 deployment from the same public pages used on GitHub Pages."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile
from urllib.parse import urlsplit, unquote
import posixpath

ROUTES = ('summary', 'resources', 'corporate', 'upstream-scm-mdm', 'mpa',
          'fulfillment', 'qa', 'q4-ops', 'q4-ops-plan-b', 'project-labels')
CONFIG = ('compose.yaml', 'Caddyfile', '.env.example', 'deploy.sh', 'check.py',
          'nginx.conf.example', 'README.md')

def data(page, ident='data'):
    match = re.search(r'<script id="'+ident+r'" type="application/json">(.*?)</script>', page, re.S)
    if not match:
        raise ValueError('Missing embedded dataset: '+ident)
    return json.loads(match[1])

def validate(site):
    count = 0
    for route in ROUTES:
        page = site / route / 'index.html'
        text = page.read_text(encoding='utf-8')
        if not text.rstrip().endswith('</html>'):
            raise ValueError('Incomplete page: '+route)
        for match in re.finditer(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', text, re.S):
            json.loads(match[1]); count += 1
        # Navigation, scripts and fixed fetch URLs must resolve inside the standalone package.
        urls = re.findall(r'(?:href|src)=["\']([^"\']+)["\']', text)
        urls += re.findall(r'fetch\(["\']([^"\']+)["\']', text)
        for url in urls:
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc or not parsed.path or '${' in url or url.startswith('#'):
                continue
            path = unquote(parsed.path)
            target = posixpath.normpath(path.lstrip('/') if path.startswith('/') else route+'/'+path)
            if target.startswith('..'):
                raise ValueError('Path escapes site: '+url)
            dest = site / target
            if not dest.exists():
                raise ValueError('Broken local URL in '+route+': '+url)
        if 'lululemon.atlassian.net' in text:
            pass  # Existing source reference URLs are links, not an API integration.
    corporate = data((site/'corporate/index.html').read_text(encoding='utf-8'))
    upstream = data((site/'upstream-scm-mdm/index.html').read_text(encoding='utf-8'))
    qa = data((site/'qa/index.html').read_text(encoding='utf-8'), 'qa-plan')
    nichole = sum(a['md'] for a in upstream['allocations'] if a['person']=='Nichole Yu')
    for domain in (corporate,upstream):
        for resource in domain['consolidation']['resources']:
            md=resource.get('md')
            if md is not None and (not isinstance(md,(int,float)) or md<0):
                raise ValueError('Invalid resource MD: '+resource['name'])
    return {'routes':len(ROUTES), 'datasets':count, 'corporateQ4Projects':len(corporate['items']),
            'upstreamNicholeMD':nichole, 'finalQAMD':sum(p['md'] for p in qa['projects'])}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--revision', default='working-tree')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[2]
    out=Path(args.output).resolve()
    # Refuse reuse to avoid deleting or accidentally packaging unrelated files.
    out.mkdir(parents=True,exist_ok=False)
    package=out/'q4-planning-server';site=package/'site';site.mkdir(parents=True)
    for route in ROUTES:
        (site/route).mkdir();shutil.copyfile(repo/'public'/route/'index.html',site/route/'index.html')
    shutil.copytree(repo/'public/assets',site/'assets')
    (site/'index.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=summary/"><title>Q4 Resource Planning</title></head><body><a href="summary/">Open Q4 Resource Planning</a></body></html>\n',encoding='utf-8')
    (site/'healthz').write_text('ok\n',encoding='utf-8')
    for name in CONFIG:
        content=(repo/'deployment/q4'/name).read_text(encoding='utf-8').replace('\r\n','\n')
        (package/name).write_text(content,encoding='utf-8',newline='\n')
    result=validate(site)
    hashes={str(p.relative_to(site)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(site.rglob('*')) if p.is_file()}
    (package/'manifest.json').write_text(json.dumps({'revision':args.revision,'entry':'/summary/','checks':result,'sha256':hashes},indent=2)+'\n',encoding='utf-8')
    archive=out/'Q4-Planning-Aliyun-Ready.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(out))
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    (out/'SHA256SUMS.txt').write_text(sha+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps({'archive':str(archive),'sha256':sha,**result}))

if __name__=='__main__':main()
