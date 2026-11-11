"""Create the independent Ops FC ZIP; never includes credentials or raw source."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[2]
source = repo / 'public' / 'ops-roadmap'
files = ['index.html', 'app.js', 'style.css', 'data.json']
data = json.loads((source / 'data.json').read_text(encoding='utf8'))
assert len([r for r in data['records'] if r['group'] == 'wuhan' and not r['placeholder']]) == 13
assert len([r for r in data['records'] if r['placeholder']]) == 1
assert len([r for r in data['records'] if r['group'] == 'enhancements']) == 14
output = Path(args.output).resolve()
output.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    archive.write(Path(__file__).with_name('app.py'), 'app.py')
    for name in files:
        archive.write(source / name, 'site/' + name)
print(json.dumps({'path': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'sourceVersion': data['version'], 'files': 5}))
