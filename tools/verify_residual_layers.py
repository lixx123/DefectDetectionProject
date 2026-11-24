"""Verify precomputed full-frame residual/DoG layers match filter_context's
guarded-window compute exactly (bit-identical or near-bit-identical), so the
per-tile crop is a safe drop-in replacement.
"""
import os, sys, json
from pathlib import Path

ALG = Path(r'D:\疵病检测\DefectDetectionProject_opt\algorithm')
V3 = ALG / 'scripts' / 'h3_b151' / 'scripts_v3'
sys.path.insert(0, str(ALG))
sys.path.insert(0, str(V3))

INPUT_JSON = r'D:\疵病检测\DefectDetectionProject_opt\outputs\input_26_1_opt2\inputs.json'
RUN_OUT = r'D:\疵病检测\DefectDetectionProject_opt\outputs\input_26_1_opt2'
N_TILES = int(os.environ.get('N_TILES', '12'))
IYS = {int(x) for x in os.environ.get('IYS', '9,11,18,21,25').split(',') if x.strip()}

os.environ['B151_RUN_OUTPUT'] = RUN_OUT
os.environ['B151_RAW'] = r'D:\疵病检测\疵病实测数据\260624批次表观（5片）\26 (1).raw'
Path(RUN_OUT, 'analysis_cache').mkdir(parents=True, exist_ok=True)

import numpy as np
import detector
import stage_j4 as J4
from stage_process import policies
from src.detection.j4_filter_context import filter_context
from config import user_config as cfg

data = json.loads(Path(INPUT_JSON).read_text(encoding='utf-8-sig'))
inp = data['input']
plan = [t for t in data['plan'] if t['iy'] in IYS][:N_TILES]

pp, policies, grade, j1, j2 = detector.init(inp, 'MEDIUM_LARGE_FAST')
refine, seed, f, g, h = policies

raw = np.memmap(inp['raw'], dtype='>u2', mode='r', shape=(9200, 11276))
g22 = np.load(inp['residual_gaussian22'], mmap_mode='r')
c61 = np.load(inp['residual_closing61'], mmap_mode='r')
dog = np.load(inp['dog'], mmap_mode='r')

max_g22 = max_c61 = max_dog = 0.0
for tile in plan:
    x0, y0, x1, y1 = tile['core_xyxy']
    l, t, r, b = J4.halo_rect([x0, y0, x1, y1], raw.shape, 64)
    # precomputed crop (what the optimized context_provider returns)
    p_g = np.asarray(g22[t:b, l:r], np.float32)
    p_c = np.asarray(c61[t:b, l:r], np.float32)
    p_d = np.asarray(dog[t:b, l:r], np.float32)
    # legacy guarded-window compute
    ctx = filter_context(raw, (l, t, r, b), cfg.CASE03J4_FILTER_CONTEXT_PX, h)
    d_g = np.abs(p_g - ctx['residuals']['gaussian22']).max()
    d_c = np.abs(p_c - ctx['residuals']['closing61']).max()
    d_d = np.abs(p_d - ctx['dog']).max()
    max_g22 = max(max_g22, d_g); max_c61 = max(max_c61, d_c); max_dog = max(max_dog, d_d)
    bit = np.array_equal(p_g, ctx['residuals']['gaussian22']) and \
          np.array_equal(p_c, ctx['residuals']['closing61']) and \
          np.array_equal(p_d, ctx['dog'])
    print(f'{tile["tile_id"]}: bit_identical={bit} max|g22|={d_g:.3e} max|c61|={d_c:.3e} max|dog|={d_d:.3e}')

print(f'OVERALL max abs diff: g22={max_g22:.3e} c61={max_c61:.3e} dog={max_dog:.3e}')
print('RESULT:', 'PASS' if max(max_g22, max_c61, max_dog) == 0.0 else 'CHECK_TOLERANCE')
