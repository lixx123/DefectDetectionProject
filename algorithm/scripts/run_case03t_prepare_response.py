"""Case03-T0 response preparation: exact 5-scale BlackHat for sample26 frame2.

New append-only run. The raw is read-only; output fused uint16 is a .npy
memmap, generated once. Use exact production black_hat_uint16, not a preview.
"""
from __future__ import annotations
import argparse, hashlib,json,sys,time
from pathlib import Path
import cv2,numpy as np

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.blackhat import black_hat_uint16

def run(run_id:str)->Path:
    out=cfg.OUTPUT_ROOT/"case03t_threshold_pilot"/run_id
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    raw_path=cfg.DATA_ROOT/"26 (2).raw"
    raw=np.memmap(raw_path,mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    if raw_path.stat().st_size != raw.size*2:raise ValueError("RAW file size mismatch")
    # cv2 accepts native-endian uint16 only. Raw data not modified.
    image=np.asarray(raw,dtype=np.uint16)
    fused_path=out/"fused_blackhat_26_frame2_uint16.npy"
    fused=np.lib.format.open_memmap(fused_path,mode="w+",dtype=np.uint16,
                                   shape=image.shape)
    fused[:]=0
    telemetry=[]
    tic=time.perf_counter()
    for kernel in cfg.BLACKHAT_KERNEL_SIZES_PX:
        started=time.perf_counter()
        response=black_hat_uint16(image,int(kernel),cfg.BLACKHAT_KERNEL_SHAPE)
        np.maximum(fused,response,out=fused)
        n=int(np.count_nonzero(response))
        telemetry.append({
            "kernel_px":int(kernel),"nonzero_response_pixels":n,
            "peak_response_DN":int(response.max()),
            "elapsed_seconds":round(time.perf_counter()-started,2)
        })
        del response
        fused.flush()
        print("SCALE_DONE",kernel,telemetry[-1],flush=True)
    # Existing source and new fused use raw 12-bit DN; no PNG remapping.
    sample=np.asarray(fused[::16,::16]).copy()
    maxval=int(sample.max())
    p=np.percentile(sample,[50,75,90,95,98,99,99.5,99.9])
    report={
        "raw_source":str(raw_path),"raw_size_bytes":raw_path.stat().st_size,
        "shape":list(image.shape),"dtype":"uint16","sample":26,"frame":2,
        "fused":str(fused_path),"scales_px":cfg.BLACKHAT_KERNEL_SIZES_PX,
        "kernel_shape":cfg.BLACKHAT_KERNEL_SHAPE,"fusion":"max",
        "response_sample_stride_px":16,
        "response_sample_quantiles_DN":dict(zip(
            ["P50","P75","P90","P95","P98","P99","P99_5","P99_9"],
            [round(float(v),4) for v in p])),
        "sample_max_DN":maxval,
        "per_scale":telemetry,
        "elapsed_seconds":round(time.perf_counter()-tic,2),
        "manual_locations_not_used":True
    }
    (out/"response_manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("RESPONSE_COMPLETE",json.dumps(report,ensure_ascii=False),flush=True)
    return out

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--run-id",default="run_20261010_sample26_frame2_response_v1")
    opts=a.parse_args()
    run(opts.run_id)
