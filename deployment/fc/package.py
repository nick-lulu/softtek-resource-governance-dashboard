"""Build an FC code ZIP from the validated Q4 static release."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--revision', required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[2]
output = Path(args.output).resolve()
subprocess.run([sys.executable, str(repo / 'deployment/q4/package.py'),
                '--output', str(output / 'validated'), '--revision', args.revision], check=True)
site = output / 'validated/q4-planning-server/site'
archive = output / 'Q4-Planning-FC.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
    for name in ['server.py', 'app.py', 'bootstrap', 'timesheet.py']:
        data = (repo / 'deployment/fc' / name).read_bytes().replace(b'\r\n', b'\n')
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = (0o100755 if name == 'bootstrap' else 0o100644) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        package.writestr(info, data)
    for path in site.rglob('*'):
        if path.is_file():
            package.write(path, 'site/' + path.relative_to(site).as_posix())
sha = hashlib.sha256(archive.read_bytes()).hexdigest()
(output / 'SHA256SUMS.txt').write_text(sha + '  ' + archive.name + '\n', encoding='ascii')
(output / 'deployment.json').write_text(json.dumps({
    'revision': args.revision, 'runtime': 'custom.debian10', 'port': 9000,
    'command': ['python3', 'app.py'], 'archive': archive.name, 'sha256': sha
}, indent=2), encoding='utf8')
print(json.dumps({'archive': str(archive), 'sha256': sha}))