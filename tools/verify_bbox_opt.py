"""Verify the bbox-limited stats_mask/max_hull_distance optimization is
pixel- and metadata-identical to the legacy full-window path.

For a set of real tiles it runs detect_window_H_seeded twice:
  - optimized: stage_refine calls stats_mask/max_hull_distance with a bbox
  - reference: the same functions monkeypatched to ignore bbox (full window)
and asserts every object's mask, bbox, centroid, area, Feret, status and flags
match exactly, plus a synthetic helper-equivalence test.
"""
import os, sys, json
from pathlib import Path

ALG = Path(r'D:\疵病检测\DefectDetectionProject_opt\algorithm')
V3 = ALG / 'scripts' / 'h3_b151' / 'scripts_v3'
sys.path.insert(0, str(ALG))
sys.path.insert(0, str(V3))

INPUT_JSON = r'D:\疵病检测\DefectDetectionProject_opt\outputs\input_26_1\inputs.json'
RUN_OUT = r'D:\疵病检测\DefectDetectionProject_opt\outputs\input_26_1'
N_TILES = int(os.environ.get('N_TILES', '40'))
IYS = {int(x) for x in os.environ.get('IYS', '9,11,18,21,25').split(',') if x.strip()}

os.environ['B151_RUN_OUTPUT'] = RUN_OUT
os.environ['B151_RAW'] = r'D:\疵病检测\疵病实测数据\260624批次表观（5片）\26 (1).raw'
Path(RUN_OUT, 'analysis_cache').mkdir(parents=True, exist_ok=True)

import numpy as np
import cv2
import detector
import stage_j4 as J4
import stage_refine as SR
import src.detection.case03e2_multicandidate as MC
import src.detection.local_boundary_refinement as LBR
from stage_process import policies
from fast_state import STATE
from early_rules import before_refinement
from src.detection.case03t_adaptive_hysteresis import hysteresis_window
from src.detection.j4_filter_context import filter_context
from config import user_config as cfg

# ---- 1) synthetic helper equivalence (bbox vs full window) ----
rng = np.random.default_rng(0)
for _ in range(200):
    H, W = rng.integers(40, 200, 2)
    mask = rng.random((H, W)) < rng.uniform(0.001, 0.1)
    yy, xx = np.nonzero(mask)
    if len(xx) == 0:
        continue
    x0, y0 = int(xx.min()), int(yy.min())
    x1, y1 = int(xx.max()) + 1, int(yy.max()) + 1
    bbox = (x0, y0, x1, y1)
    s_bbox = MC.stats_mask(mask, bbox)
    s_full = MC.stats_mask(mask)
    assert s_bbox[0] == s_full[0], (s_bbox, s_full)
    assert abs(s_bbox[1] - s_full[1]) < 1e-6 and abs(s_bbox[2] - s_full[2]) < 1e-6
    assert s_bbox[3] == s_full[3] and s_bbox[4] == s_full[4]
    assert abs(LBR.max_hull_distance(mask, bbox) - LBR.max_hull_distance(mask)) < 1e-4
print('synthetic helper equivalence: PASS')

# ---- 2) real-tile object equivalence ----
data = json.loads(Path(INPUT_JSON).read_text(encoding='utf-8-sig'))
inp = data['input']
plan = [t for t in data['plan'] if t['iy'] in IYS][:N_TILES]

pp, policies, grade, j1, j2 = detector.init(inp, 'MEDIUM_LARGE_FAST')
refine, seed, f, g, h = policies

raw = np.memmap(inp['raw'], dtype='>u2', mode='r', shape=(9200, 11276))
response = np.load(inp['response'], mmap_mode='r')
spec = {'bands': inp['specs']['A1'], 'fallback': [65536., 65536.],
        'pixel_band_ids': inp['ids']}


def detect_tile(tile, full_window):
    if full_window:
        SR.stats_mask = lambda m, bbox=None: MC.stats_mask(m)
        SR.max_hull_distance = lambda m, bbox=None: LBR.max_hull_distance(m)
    else:
        SR.stats_mask = MC.stats_mask
        SR.max_hull_distance = LBR.max_hull_distance
    x0, y0, x1, y1 = tile['core_xyxy']
    l, t, r, b = J4.halo_rect([x0, y0, x1, y1], raw.shape, 64)
    local = np.asarray(raw[t:b, l:r], np.uint16)
    resp = np.asarray(response[t:b, l:r], np.uint16)
    wlo, whi, _ = J4.threshold_maps(spec, l, t, r, b)
    STATE.geometry([x0, y0, x1, y1], (l, t, r, b))
    H, S, seeds = hysteresis_window(resp, wlo, whi)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(H.astype(np.uint8), 8)
    skip_ids = before_refinement(labels, stats, seed) if STATE.early else set()
    if os.environ.get('VERIFY_DEBUG'):
        print('  DEBUG', tile['tile_id'], 'H_components=', n - 1,
              'skip_ids=', len(skip_ids), 'H_pixels=', int(H.sum()),
              'wlo_range=', float(wlo.min()), float(wlo.max()), flush=True)
    if STATE.early and n > 1 and len(skip_ids) == n - 1:
        return None
    if n == 1:
        return None
    ctx = filter_context(raw, (l, t, r, b), cfg.CASE03J4_FILTER_CONTEXT_PX, h)
    return SR.detect_window_H_seeded(
        local, H, S, resp, cfg=refine, policy=seed, skip_ids=skip_ids,
        residuals=ctx['residuals'],
        h_low_threshold_map=wlo, h_high_threshold_map=whi)


mismatch = 0
checked = 0
for tile in plan:
    d_opt = detect_tile(tile, False)
    d_ref = detect_tile(tile, True)
    assert (d_opt is None) == (d_ref is None)
    if d_opt is None:
        continue
    oo, rr = d_opt['objects'], d_ref['objects']
    assert len(oo) == len(rr)
    for a, b in zip(oo, rr):
        if a is None or b is None:
            assert a is None and b is None
            continue
        checked += 1
        ok = (
            np.array_equal(a.mask, b.mask)
            and a.bbox == b.bbox
            and abs(a.center_x - b.center_x) < 1e-6
            and abs(a.center_y - b.center_y) < 1e-6
            and a.area_px == b.area_px
            and abs(a.max_span_px - b.max_span_px) < 1e-5
            and abs(a.eq_diameter_px - b.eq_diameter_px) < 1e-5
            and a.status == b.status
            and a.flags == b.flags
            and a.sources == b.sources
        )
        if not ok:
            mismatch += 1
            print('MISMATCH', tile['tile_id'], a.object_id,
                  'bbox', a.bbox, b.bbox, 'area', a.area_px, b.area_px,
                  'span', a.max_span_px, b.max_span_px, 'status', a.status, b.status)
    # also verify the returned audit / counts match
    assert d_opt['num_output_objects'] == d_ref['num_output_objects']
    assert d_opt['num_review_objects'] == d_ref['num_review_objects']

print(f'real-tile object equivalence: checked {checked} objects across {len(plan)} tiles, mismatch={mismatch}')
print('RESULT:', 'PASS' if mismatch == 0 else 'FAIL')
