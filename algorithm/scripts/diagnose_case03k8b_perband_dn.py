"""Read-only diagnostic distribution of BlackHat per independent workband."""
from pathlib import Path
import sys
import cv2,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as c
a=c.OUTPUT_ROOT/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"
h={1:c.OUTPUT_ROOT/"case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",
2:c.OUTPUT_ROOT/"case03k6_frame2_fused_blackhat/run_20261012_frame26_2_frozen_kernels_v1/frame26_2_fused_blackhat_exact.npy"}
for frame in (1,2):
    ids=cv2.imdecode(np.frombuffer((a/f"frame26_{frame}/band_id_fullres.png").read_bytes(),np.uint8),
                     cv2.IMREAD_UNCHANGED)[::8,::8]
    bh=np.load(h[frame],mmap_mode="r",allow_pickle=False)[::8,::8]
    raw=np.memmap(c.DATA_ROOT/f"26 ({frame}).raw",dtype=">u2",
                  mode="r",shape=(c.RAW_HEIGHT,c.RAW_WIDTH))[::8,::8]
    print("FRAME",frame,flush=True)
    for band in range(1,int(ids.max())+1):
        v=np.asarray(bh[ids==band],np.float64)
        rv=np.asarray(raw[ids==band],np.float64)
        med=np.median(v)
        mad=1.4826*np.median(abs(v-med))
        print("BAND",band,"raw med",int(np.median(rv)),
            "BH med/mad",round(med,2),round(mad,2),
            "BH percentiles 90,95,99,99.5,99.9",np.percentile(v,[90,95,99,99.5,99.9]).round(2).tolist(),
            "BH >170/230",round(np.mean(v>=170),5),round(np.mean(v>=230),5),
            flush=True)
