"""Deploy the verified executive analytics bundle; retain previous assets and verify every copy."""
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUILD = Path('/tmp/toolsauto-executive-analytics-dist').resolve()
TARGET = (ROOT / 'app/static/admin').resolve()
assert ROOT == Path('/home/vu/toolsauto') and TARGET.is_relative_to(ROOT)
assert BUILD.is_dir() and (BUILD / 'index.html').is_file()
BACKUP = Path('/tmp') / ('toolsauto-executive-backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
BACKUP.mkdir(exist_ok=False)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


apps = json.loads(subprocess.run(['pm2', 'jlist'], capture_output=True, text=True, check=True).stdout)
proof = {'deployed_at': datetime.now(timezone.utc).isoformat(), 'backup': str(BACKUP), 'files': [],
         'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
         'processes_before': {row['name']: {'pid': row['pid'], 'status': row['pm2_env']['status'],
                              'restarts': row['pm2_env']['restart_time']} for row in apps}}
web = next(row for row in apps if row['name'] == 'Web_Dashboard')
assert web['pm2_env']['pm_cwd'] == str(ROOT) and web['pm2_env']['status'] == 'online'
files = sorted(path for path in BUILD.rglob('*') if path.is_file())
assert len(files) == 9
for source in files:
    relative = source.relative_to(BUILD)
    target = TARGET / relative
    assert target.resolve().is_relative_to(TARGET)
    if target.exists():
        destination = BACKUP / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)
        assert sha(target) == sha(destination)
        proof['files'].append({'path': relative.as_posix(), 'previous_sha256': sha(target), 'sha256': sha(source)})
    else:
        proof['files'].append({'path': relative.as_posix(), 'previous_sha256': None, 'sha256': sha(source)})
(BACKUP / 'executive.py').write_bytes(subprocess.check_output(['git', 'show', 'HEAD:app/platform/admin_api/executive.py'], cwd=ROOT))
for source in files:
    relative = source.relative_to(BUILD)
    if relative == Path('index.html'):
        continue
    target = TARGET / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    assert sha(source) == sha(target)
index = TARGET / 'index.html'
temporary = TARGET / 'index.executive-next.tmp'
assert temporary.resolve().parent == TARGET and not temporary.exists()
shutil.copy2(BUILD / 'index.html', temporary)
assert sha(temporary) == sha(BUILD / 'index.html')
os.replace(temporary, index)
assert not temporary.exists() and index.is_file() and sha(index) == sha(BUILD / 'index.html')
proof['atomic_index_verified'] = True
for item in proof['files']:
    assert sha(TARGET / item['path']) == item['sha256']
proof['status'] = 'STATIC_DEPLOYED_RESTART_PENDING'
(ROOT / 'reports/ui175/executive-analytics/deployment.json').write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps({'status': proof['status'], 'backup': str(BACKUP), 'files_verified': len(files),
                  'previous_web': proof['processes_before']['Web_Dashboard'], 'index_sha256': sha(index)}))
