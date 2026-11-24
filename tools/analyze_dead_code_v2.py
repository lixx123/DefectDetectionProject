"""Corrected dead-code analysis + move plan for the formal project.

Fixes the earlier import-resolution gaps (multi-name `import a,b`,
`from config import x`, bare sibling imports). Produces a reversible move plan:
  archive/legacy_stages_20261123/{scripts,src,detection,tests}/...

Does NOT move anything: only prints the plan and writes plan.json.
"""
import ast, os, sys, json
from pathlib import Path
from collections import defaultdict, deque

ROOT = Path(r'D:\疵病检测\DefectDetectionProject')
ARCHIVE = ROOT / 'archive' / 'legacy_stages_20261123'
ACTIVE_ROOTS = ['main.py', 'scripts/h3_b151/staging_entry.py']

all_py = []
for p in ROOT.rglob('*.py'):
    parts = set(p.parts)
    if any(x in parts for x in ('.venv', 'outputs', '__pycache__', '.pytest_cache', 'archive')):
        continue
    if '.pytest_tmp' in str(p):
        continue
    all_py.append(p)
all_py_set = set(all_py)
rel = {p: p.relative_to(ROOT).as_posix() for p in all_py}

# resolve a dotted import name to a file, given the importing file's directory
SCRIPT_V3 = ROOT / 'scripts' / 'h3_b151' / 'scripts_v3'
def resolve(name, pdir):
    if not name:
        return None
    parts = name.split('.')
    for i in range(len(parts), 0, -1):
        cand = ROOT.joinpath(*parts[:i]).with_suffix('.py')
        if cand in all_py_set:
            return cand
    sib = pdir / (parts[-1] + '.py')
    if sib in all_py_set:
        return sib
    # bare imports inside the h3_b151 chain resolve via sys.path.insert(scripts_v3)
    sv = SCRIPT_V3 / (parts[-1] + '.py')
    if sv in all_py_set:
        return sv
    return None

def local_imports(p):
    try:
        tree = ast.parse(p.read_text(encoding='utf-8'), filename=str(p))
    except Exception:
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                continue
            base = node.module or ''
            if base:
                names.add(base)
            for a in node.names:
                names.add((base + '.' + a.name) if base else a.name)
    out = set()
    for n in names:
        r = resolve(n, p.parent)
        if r:
            out.add(r)
    return out

graph = defaultdict(set)
rev = defaultdict(set)
for p in all_py:
    for tgt in local_imports(p):
        if tgt == p:
            continue
        graph[p].add(tgt)
        rev[tgt].add(p)

roots = [ROOT / r for r in ACTIVE_ROOTS]
# the whole h3_b151 chain is the active production code: seed the closure with it
roots += [p for p in all_py if rel[p].startswith('scripts/h3_b151/')]
seen = set(roots)
q = deque(roots)
while q:
    f = q.popleft()
    for tgt in graph.get(f, ()):
        if tgt not in seen:
            seen.add(tgt)
            q.append(tgt)

def is_test(p):
    return rel[p].startswith('tests/')

def is_init(p):
    return p.name == '__init__.py'

# dead candidates: not reachable, not a test, not __init__, not an active root
dead = [p for p in all_py if p not in seen and not is_test(p) and not is_init(p) and p not in roots]

# dead tests: tests that import a dead module/script (or reach nothing local)
dead_tests = []
for p in all_py:
    if not is_test(p) or p in seen:
        continue
    imported = graph.get(p, set())
    imported_dead = [t for t in imported if t not in seen]
    if imported_dead:
        dead_tests.append(p)

plan = {}
for p in dead:
    rp = rel[p]
    plan[rp] = 'archive/legacy_stages_20261123/' + rp
for p in dead_tests:
    rp = rel[p]
    plan[rp] = 'archive/legacy_stages_20261123/' + rp

# print summary
print(f'total={len(all_py)} closure={len(seen)} dead_src_scripts={len(dead)} dead_tests={len(dead_tests)}')
print('\n=== dead scripts / src modules (move) ===')
for p in sorted(dead, key=lambda x: rel[x]):
    print('   ', rel[p])
print('\n=== dead tests (move) ===')
for p in sorted(dead_tests, key=lambda x: rel[x]):
    print('   ', rel[p])

Path(r'D:\疵病检测\DefectDetectionProject_opt\dead_code_plan.json').write_text(
    json.dumps({'dead': sorted(rel[p] for p in dead), 'dead_tests': sorted(rel[p] for p in dead_tests)},
               ensure_ascii=False, indent=2), encoding='utf-8')
print('\nplan written to dead_code_plan.json')
