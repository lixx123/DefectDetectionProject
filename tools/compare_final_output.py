"""Compare final J5 output (per-defect pixel size + exact masks) between the
baseline 283ce12 run and an optimized run, byte/field exact.

This is the definitive check the earlier object-level/count checks did not
cover: every defect's source_area_px2, Feret, grade, bbox, band_id, and its
exact mask bytes must match the baseline.
"""
import os, sys, json, hashlib
from pathlib import Path

BASE = Path(sys.argv[1] if len(sys.argv) > 1 else r'D:\疵病检测\DefectDetectionProject_baseline\outputs\run_26_1_baseline')
OPT = Path(sys.argv[2] if len(sys.argv) > 2 else r'D:\疵病检测\DefectDetectionProject_opt\outputs\run_26_1_opt3_v2')

# locate the FAST_V3 output dir (sample folder name has a space)
def find_dir(root, pattern):
    hits = list(root.rglob(pattern))
    assert len(hits) == 1, (root, pattern, hits)
    return hits[0]

base_dir = find_dir(BASE, 'MEDIUM_LARGE_FINAL_OBJECTS.csv').parent
opt_dir = find_dir(OPT, 'MEDIUM_LARGE_FINAL_OBJECTS.csv').parent

def csv_rows(d):
    import csv
    p = d / 'MEDIUM_LARGE_FINAL_OBJECTS.csv'
    with p.open(encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

b_rows = csv_rows(base_dir)
o_rows = csv_rows(opt_dir)
print(f'defect count: baseline={len(b_rows)} optimized={len(o_rows)}')

# index by new_id (DEFECT_xxxxx)
def idx(rows):
    m = {r['new_id']: r for r in rows}
    assert len(m) == len(rows), 'duplicate new_id'
    return m
b = idx(b_rows); o = idx(o_rows)

fields = ['source_area_px2', 'baseline_Feret_px', 'grade', 'bbox_xyxy_exclusive',
          'band_id', 'baseline_source_area_px2', 'EVAL_source_area_px2']
mismatch = 0
total_base = total_opt = 0
for nid in sorted(set(b) | set(o)):
    if nid not in b or nid not in o:
        print('MISSING', nid, 'base' if nid not in b else '', 'opt' if nid not in o else '')
        mismatch += 1
        continue
    rb, ro = b[nid], o[nid]
    total_base += int(rb['source_area_px2']); total_opt += int(ro['source_area_px2'])
    for f in fields:
        if rb.get(f) != ro.get(f):
            print('FIELD MISMATCH', nid, f, repr(rb.get(f)), '!=', repr(ro.get(f)))
            mismatch += 1

print(f'total source_area_px2: baseline={total_base} optimized={total_opt} '
      f'{"MATCH" if total_base==total_opt else "MISMATCH"}')

# exact mask bytes comparison
def mask_hashes(d):
    p = d / 'MEDIUM_LARGE_FINAL_EXACT_MASKS'
    out = {}
    for f in sorted(p.glob('*.npz')):
        out[f.stem] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out
bh = mask_hashes(base_dir); oh = mask_hashes(opt_dir)
print(f'exact masks: baseline={len(bh)} optimized={len(oh)}')
for nid in sorted(set(bh) | set(oh)):
    if nid not in bh or nid not in oh:
        print('MASK MISSING', nid); mismatch += 1
    elif bh[nid] != oh[nid]:
        print('MASK BYTES MISMATCH', nid); mismatch += 1

print('RESULT:', 'PASS (identical defect count + per-defect pixel size + exact masks)'
      if mismatch == 0 and total_base == total_opt else f'FAIL ({mismatch} mismatches)')
