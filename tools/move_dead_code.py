"""Move the dead-code plan (dead_code_plan.json) into archive/legacy_stages_20261123/,
preserving the directory structure, and write a SHA256 manifest for traceability.
Reversible: each source path -> archive path is recorded.
"""
import json, hashlib, shutil
from pathlib import Path

ROOT = Path(r'D:\疵病检测\DefectDetectionProject')
ARCHIVE = ROOT / 'archive' / 'legacy_stages_20261123'

plan = json.loads(Path(r'D:\疵病检测\DefectDetectionProject_opt\dead_code_plan.json').read_text(encoding='utf-8'))
files = plan['dead'] + plan['dead_tests']

def sha256(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

manifest = []
moved = 0
missing = []
for relp in files:
    src = ROOT / relp
    if not src.exists():
        missing.append(relp)
        continue
    dst = ARCHIVE / relp
    dst.parent.mkdir(parents=True, exist_ok=True)
    h = sha256(src)
    shutil.move(str(src), str(dst))
    manifest.append({'original': relp, 'archive': dst.relative_to(ROOT).as_posix(), 'sha256': h})
    moved += 1

# manifest
m = ARCHIVE / 'MANIFEST.json'
m.write_text(json.dumps({'moved': manifest, 'missing': missing,
                         'count_moved': len(manifest), 'count_missing': len(missing)},
                        ensure_ascii=False, indent=2), encoding='utf-8')

print(f'moved={len(manifest)} missing={len(missing)}')
for x in missing:
    print('  MISSING:', x)
print('manifest:', m)
