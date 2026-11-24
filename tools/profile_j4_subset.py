"""Profile J4 on a subset of tiles from a prepared input (26(1)).

Reads the prepared inputs.json, replicates detector.one's J4 loop for the
first N tiles, and reports a cProfile cumulative summary so the real hot
path (per-component loop vs residual compute) is measured, not guessed.
"""
import os, sys, json, cProfile, pstats, io, time
from pathlib import Path

ALG = Path(r'D:\疵病检测\DefectDetectionProject_opt\algorithm')
V3 = ALG / 'scripts' / 'h3_b151' / 'scripts_v3'
sys.path.insert(0, str(ALG))
sys.path.insert(0, str(V3))

INPUT_JSON = r'D:\疵病检测\DefectDetectionProject_opt\outputs\input_26_1\inputs.json'
# Run output = the input dir itself, so the prepared npy inputs sit inside the
# guard's allowed OUT tree (guard only lets the detector read data under OUT).
RUN_OUT = r'D:\疵病检测\DefectDetectionProject_opt\outputs\input_26_1'
PROFILE_DIR = r'D:\疵病检测\DefectDetectionProject_opt\outputs\input_26_1\profile'
N_TILES = int(os.environ.get('N_TILES', '30'))

data = json.loads(Path(INPUT_JSON).read_text(encoding='utf-8-sig'))
inp = data['input']
# Sample work-band CORE rows (not the shield edges): band1 ~iy10-12, band2 ~iy17-19,
# band3 ~iy21-22, band4 ~iy25-26. iy filter lets us target dense tiles.
_iys = {int(x) for x in os.environ.get('IYS', '11').split(',') if x.strip()}
_selected = [t for t in data['plan'] if t['iy'] in _iys]
plan = _selected[:N_TILES]
print('sampling %d tiles at iy=%s (of %d matches)' % (len(plan), sorted(_iys), len(_selected)))

os.environ['B151_RUN_OUTPUT'] = RUN_OUT
os.environ['B151_RAW'] = inp['raw']

# guard.activate creates OUT/analysis_cache/{temp,...}; create the parent first
Path(RUN_OUT, 'analysis_cache').mkdir(parents=True, exist_ok=True)

import numpy as np
import detector
import stage_j4 as J4
import memory_store
from fast_state import STATE

pp, policies, grade, j1, j2 = detector.init(inp, 'MEDIUM_LARGE_FAST')
folder = Path(PROFILE_DIR)
folder.mkdir(parents=True, exist_ok=True)
memory_store.reset('FAST', folder)

raw = np.memmap(inp['raw'], dtype='>u2', mode='r', shape=(9200, 11276))
response = np.load(inp['response'], mmap_mode='r')
spec = {'bands': inp['specs']['A1'], 'fallback': [65536., 65536.],
        'pixel_band_ids': inp['ids']}


def run_subset():
    statuses = []
    for tile in plan:
        st = J4.run_tile(tile, raw, response, policies, grade, j1, j2, 64,
                         folder, image_enabled=False, frame_label=inp['sample_id'],
                         threshold_mode='b15_pixel', perband_spec=spec)
        statuses.append(st)
    return statuses


# warm-up one tile so mmap / imports are already cached before profiling
run_subset()

pr = cProfile.Profile()
pr.enable()
tic = time.perf_counter()
statuses = run_subset()
wall = time.perf_counter() - tic
pr.disable()

s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
ps.print_stats(40)
print('=== wall seconds for %d tiles = %.3f (%.1f ms/tile) ===' % (len(plan), wall, 1000 * wall / len(plan)))
print('=== cumulative profile (top 40) ===')
print(s.getvalue())

# also dump to file for later reference
out = Path(PROFILE_DIR) / 'profile_cumulative.txt'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(s.getvalue(), encoding='utf-8')
print('profile written to', out)
