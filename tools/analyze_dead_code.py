"""Analyse the formal project for dead code (modules/scripts not reachable from
the active entry points). Reports, for src/ and scripts/, which .py files are
(a) orphan (never imported anywhere) and (b) unreachable from the active roots.
"""
import ast, os, sys
from pathlib import Path
from collections import defaultdict, deque

ROOT = Path(r'D:\疵病检测\DefectDetectionProject')
ACTIVE_ROOTS = ['main.py', 'scripts/h3_b151/staging_entry.py']

# collect .py files (exclude venv/outputs/pycache/pytest)
all_py = []
for p in ROOT.rglob('*.py'):
    parts = set(p.parts)
    if any(x in parts for x in ('.venv', 'outputs', '__pycache__', '.pytest_cache')) or '.pytest_tmp' in str(p):
        continue
    if 'archive' in parts:
        continue
    all_py.append(p)

rel = {p: p.relative_to(ROOT).as_posix() for p in all_py}

# module path keyed by importable dotted name
# e.g. src/detection/case03a.py -> src.detection.case03a
def dotted(relp):
    r = relp[:-3].replace('/', '.') if relp.endswith('.py') else relp
    return r

by_dotted = {}
for p, rp in rel.items():
    d = dotted(rp)
    by_dotted[d] = p
    # also index by basename for sibling (bare) imports
    by_dotted[Path(rp).stem] = p  # may collide; last wins

# parse imports of a file, resolve to local module paths
def local_imports(p):
    try:
        tree = ast.parse(p.read_text(encoding='utf-8'), filename=str(p))
    except Exception:
        return set()
    out = set()
    for node in ast.walk(tree):
        mod = None
        if isinstance(node, ast.Import):
            for a in node.names:
                mod = a.name
                break
        elif isinstance(node, ast.ImportFrom):
            mod = node.module
        if not mod:
            continue
        # only local modules (src./scripts./config./bare)
        cands = [mod]
        if mod and (mod.startswith('src.') or mod.startswith('scripts.') or mod.startswith('config.')):
            cands.append(mod)
        for c in cands:
            if c in by_dotted:
                out.add(by_dotted[c])
    return out

# build import graph (file -> imported local files)
graph = defaultdict(set)
rev = defaultdict(set)
for p in all_py:
    for tgt in local_imports(p):
        if tgt == p:
            continue
        graph[p].add(tgt)
        rev[tgt].add(p)

# active closure from roots
roots = [ROOT / r for r in ACTIVE_ROOTS if (ROOT / r).exists()]
seen = set(roots)
q = deque(roots)
while q:
    f = q.popleft()
    for tgt in graph.get(f, ()):
        if tgt not in seen:
            seen.add(tgt)
            q.append(tgt)

# classify
orphan = [p for p in all_py if p not in rev]
# exclude __init__.py from "orphan" (packages)
orphan = [p for p in orphan if p.name != '__init__.py']

unreachable = [p for p in all_py if p not in seen and p not in roots]

def scope(p):
    rp = rel[p]
    if rp.startswith('scripts/h3_b151'):
        return 'scripts/h3_b151 (ACTIVE CHAIN)'
    if rp.startswith('src/detection/'):
        return 'src/detection'
    if rp.startswith('src/'):
        return 'src/other'
    if rp.startswith('scripts/'):
        return 'scripts/legacy'
    return 'root'

print(f'total .py files: {len(all_py)}; active closure size: {len(seen)}')

print('\n=== UNREACHABLE (not in active closure), by scope ===')
from collections import Counter
by_scope = defaultdict(list)
for p in unreachable:
    by_scope[scope(p)].append(rel[p])
for s in sorted(by_scope):
    print(f'\n[{s}]  {len(by_scope[s])} files')
    for r in sorted(by_scope[s]):
        print('   ', r)

print('\n=== ORPHAN (never imported by any .py), count =', len(orphan), '===')
for p in sorted(orphan, key=lambda x: rel[x]):
    print('   ', rel[p])
