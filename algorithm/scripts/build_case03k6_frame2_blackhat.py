"""Case03-K6: create exact multiscale BH max-response for 26 FRAME 2.

Memory-bounded tiled closing on original big-endian RAW, using halo=32
(>= 2*(31//2) for dilation->erosion) and core=512. Validated against
frozen FIRST frame's exact full-frame Case02 BH before processing FRAME2.
Source RAW read-only. No original data/config/output overwritten.
"""
from __future__ import annotations
import argparse,hashlib,json,os,sys,time
from pathlib import Path
import cv2,numpy as np
from numpy.lib.format import open_memmap
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.blackhat import black_hat_uint16
FROM=cfg.DATA_ROOT/"26 (2).raw"
OUT=cfg.OUTPUT_ROOT/"case03k6_frame2_fused_blackhat/run_20261012_frame26_2_frozen_kernels_v1"
DEST=OUT/"frame26_2_fused_blackhat_exact.npy"
INCOMPLETE=OUT/"frame26_2_fused_blackhat_exact.incomplete.npy"
PROGRESS=OUT/"progress.json"
PREF=cfg.OUTPUT_ROOT/"case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy"
STEP=512
HALO=32


def atomic_write(p:Path,obj:dict):
    tmp=p.with_name(p.name+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(tmp,p)


def calc(tile:np.ndarray,kernels:tuple[int,...])->np.ndarray:
    fused=np.zeros(tile.shape,np.uint16)
    for k in kernels:
        r=black_hat_uint16(tile,k,"ellipse")
        np.maximum(fused,r,out=fused)
    return fused


def test_against_reference(kernels):
    src=cfg.DATA_ROOT/"26 (1).raw"
    old=np.memmap(src,mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    bh=np.load(PREF,allow_pickle=False,mmap_mode="r")
    checks=[(50,80),(1905,3207),(7303,1463),(8500,10430),
            (8999,11200)]
    details=[]
    for y,x in checks:
        ay=max(0,y-HALO);by=min(cfg.RAW_HEIGHT,y+192+HALO)
        ax=max(0,x-HALO);bx=min(cfg.RAW_WIDTH,x+192+HALO)
        patch=np.asarray(old[ay:by,ax:bx],dtype=np.uint16)
        current=calc(patch,kernels)
        valid=current[y-ay:min(y+192,cfg.RAW_HEIGHT)-ay,
                      x-ax:min(x+192,cfg.RAW_WIDTH)-ax]
        truth=bh[y:min(y+192,cfg.RAW_HEIGHT),x:min(x+192,cfg.RAW_WIDTH)]
        error=int(np.abs(valid.astype(np.int32)-truth.astype(np.int32)).max())
        details.append({"origin_yx":[y,x],"compared_pixels":int(truth.size),
                        "max_diff_DN":error})
        if error:
            raise AssertionError(f"tiled BH not exact at {(y,x)}: {error} DN")
    print("K6_BH_EXACT_SAME_AS_PRIOR_FIRST_FRAME",details,flush=True)
    return details


def run(resume:bool=False):
    kernels=tuple(int(k) for k in cfg.BLACKHAT_KERNEL_SIZES_PX)
    assert kernels==(3,5,9,15,31)
    assert HALO>=2*(max(kernels)//2)
    assert FROM.stat().st_size==cfg.RAW_WIDTH*cfg.RAW_HEIGHT*2
    tested=test_against_reference(kernels)
    if DEST.exists():raise FileExistsError(DEST)
    if not OUT.exists():
        OUT.mkdir(parents=True)
    elif not resume:
        raise FileExistsError("Output exists; invoke --resume to continue if needed")
    yy=list(range(0,cfg.RAW_HEIGHT,STEP))
    xx=list(range(0,cfg.RAW_WIDTH,STEP))
    total=len(yy)*len(xx)
    if resume:
        meta=json.loads(PROGRESS.read_text(encoding="utf-8"))
        assert (meta["frame"]=="26 (2).raw" and meta["kernels"]==list(kernels)
            and meta["step"]==STEP and meta["halo"]==HALO
            and meta["total_tiles"]==total)
        offset=int(meta["completed_tiles"])
        mmap=np.load(INCOMPLETE,mmap_mode="r+",allow_pickle=False)
    else:
        offset=0
        mmap=open_memmap(INCOMPLETE,mode="w+",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH),dtype=np.uint16)
        meta={"stage":"K6_FUSED_RUNNING","frame":"26 (2).raw",
              "shape":[cfg.RAW_HEIGHT,cfg.RAW_WIDTH],
              "kernels":list(kernels),"step":STEP,"halo":HALO,
              "total_tiles":total,"completed_tiles":0,
              "frame1_fullframe_response_check":tested,
              "effective_bits":cfg.EFFECTIVE_BITS,
              "read_original_RAW_only":True}
        atomic_write(PROGRESS,meta)
    raw=np.memmap(FROM,dtype=">u2",mode="r",
                 shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    t=time.perf_counter()
    for n in range(offset,total):
        iy,ix=divmod(n,len(xx))
        y=yy[iy];x=xx[ix]
        h=min(STEP,cfg.RAW_HEIGHT-y);w=min(STEP,cfg.RAW_WIDTH-x)
        ay=max(0,y-HALO);by=min(cfg.RAW_HEIGHT,y+h+HALO)
        ax=max(0,x-HALO);bx=min(cfg.RAW_WIDTH,x+w+HALO)
        src=np.asarray(raw[ay:by,ax:bx],dtype=np.uint16)
        out=calc(src,kernels)[y-ay:y-ay+h,x-ax:x-ax+w]
        mmap[y:y+h,x:x+w]=out
        if (n+1)%12==0 or n+1==total:
            mmap.flush()
            meta["completed_tiles"]=n+1
            meta["total_elapsed_this_call_s"]=round(time.perf_counter()-t,2)
            atomic_write(PROGRESS,meta)
            print("K6_BH_PROGRESS",n+1,total,"elapsed",meta["total_elapsed_this_call_s"],flush=True)
    mmap.flush();del mmap
    mm=np.load(INCOMPLETE,allow_pickle=False,mmap_mode="r")
    assert mm.shape==(cfg.RAW_HEIGHT,cfg.RAW_WIDTH) and mm.dtype==np.uint16
    values=np.array([int(mm[y,x]) for y,x in
                     [(170,90),(2000,1500),(4500,8200),(8999,11200)]])
    if not np.any(values>=0):raise AssertionError("invalid output probe")
    del mm
    INCOMPLETE.rename(DEST)
    meta["stage"]="K6_BH_COMPLETE"
    meta["complete"]=True
    meta["output_file"]=str(DEST)
    meta["output_size_bytes"]=DEST.stat().st_size
    meta["elapsed_current_session_s"]=round(time.perf_counter()-t,2)
    atomic_write(OUT/"summary.json",meta)
    atomic_write(PROGRESS,meta)
    print("K6_BH_SUCCESS",json.dumps(meta,ensure_ascii=False),flush=True)
    return DEST

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--resume",action="store_true")
    args=ap.parse_args()
    run(args.resume)
