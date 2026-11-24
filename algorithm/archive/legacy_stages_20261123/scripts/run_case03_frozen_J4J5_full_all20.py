"""Frozen unmodified J4/J5 full-frame replay for all 20 RAWs.

Preserves J4 H170/230 + bounded Gaussian/Closing, F/G/H RAW/MAD/DoG
gates, scratch J1/J2 object grouping, J5 seam joining; never changes J4
or J5 algorithms. Each new frame gets a freshly computed exact full RAW
5-kernel uint16 BlackHat (.npy) with 32px halo and a stage ledger.

This runner does NOT claim K8D/E experimental contours or K8A/C workband
bookkeeping are identical to J5; follow frozen supplemental B separately.
Usage: --only 26_3 --tile-batch 32  ; then --only 26_3  (resume)
"""
from pathlib import Path
import sys,hashlib,json,argparse,time,traceback
from collections import Counter
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_case03frozen_all20_robustness import inputs
from scripts.run_case03j4_fullscan import run as run_j4
from scripts.run_case03j5_global_merge import run as run_j5
from src.detection.blackhat import black_hat_uint16
OUT=C.OUTPUT_ROOT/"CASE03_FROZEN_FULL_J4J5_20RAW_20261019_v1"
J4ROOT=C.OUTPUT_ROOT/"case03j4_fullframe"
J5ROOT=C.OUTPUT_ROOT/"case03j5_global"
KERNELS=[3,5,9,15,31]
ROW_CHUNK=512
HALO=32
def writejson(p,x):
 temp=p.with_name(p.name+".tmp")
 temp.write_text(json.dumps(x,indent=2,ensure_ascii=False,default=str),encoding="utf8")
 temp.replace(p)
def file_hash(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
 return h.hexdigest()
def read_stage(p):
 return json.loads(p.read_text(encoding="utf8")) if p.is_file() else None
def fused_exact_global(raw_path,out,status,reference=None):
 existing=read_stage(status)
 if existing:
  assert existing["stage"]=="FULL_RAW_FUSED_5KERNEL_BLACKHAT_READY"
  assert out.is_file() and out.stat().st_size==existing["bytes"]
  assert existing["sha256"]==file_hash(out)
  return out
 if out.exists():raise FileExistsError("Incomplete fused NPY; do not trust or delete: "+str(out))
 out.parent.mkdir(parents=True,exist_ok=True)
 raw=np.memmap(raw_path,dtype=">u2",shape=(C.RAW_HEIGHT,C.RAW_WIDTH),mode="r")
 img=np.lib.format.open_memmap(out,mode="w+",dtype="uint16",shape=raw.shape)
 start=time.perf_counter()
 for y0 in range(0,raw.shape[0],ROW_CHUNK):
  y1=min(raw.shape[0],y0+ROW_CHUNK)
  a=max(0,y0-HALO);b=min(raw.shape[0],y1+HALO)
  roi=np.asarray(raw[a:b,:],dtype=np.uint16)
  fusion=np.zeros(roi.shape,np.uint16)
  for k in KERNELS:
   bh=black_hat_uint16(roi,k,"ellipse")
   np.maximum(fusion,bh,out=fusion)
  img[y0:y1,:]=fusion[y0-a:y1-a,:]
  img.flush()
  if y0==0 or y0//ROW_CHUNK%6==0:
   print("FROZEN_J4_FULL_BH",raw_path.name,"done",y1,"/",raw.shape[0],flush=True)
 img.flush();del img
 s={"stage":"FULL_RAW_FUSED_5KERNEL_BLACKHAT_READY",
    "input_raw":str(raw_path),"input_raw_bytes":raw_path.stat().st_size,
    "output":str(out),"bytes":out.stat().st_size,"sha256":file_hash(out),
    "band_masks_applied_before_blackhat":False,
    "kernels":KERNELS,"elliptic":True,"halo_px":HALO,
    "height":C.RAW_HEIGHT,"width":C.RAW_WIDTH,
    "elapsed_sec":round(time.perf_counter()-start,2)}
 if reference is not None:
  expected=np.load(reference,mmap_mode="r",allow_pickle=False)
  actual=np.load(out,mmap_mode="r",allow_pickle=False)
  # Compare every pixel in three disjoint full-width stripes, not sparse
  # sampled isolated pixels. Both compare original exact uint16 values.
  for starty in (0,4122,C.RAW_HEIGHT-300):
   assert np.array_equal(expected[starty:starty+128],
                         actual[starty:starty+128]),(
      "RAW fused global BH did not reproduce frozen source",starty)
  s["old_full_BH_regression_three_128row_stripes_exact"]=True
 writejson(status,s)
 return out

def status_all(infos):
 results=[]
 for info in infos:
  key=info["uid"]
  folder=OUT/key
  status=read_stage(folder/"stage.json")
  j4=J4ROOT/f"frozen_full20_{key}_J4_v1"
  j5=J5ROOT/f"frozen_full20_{key}_J5_v1"
  original=key in ("26_1","26_2")
  if original:
   j4=J4ROOT/("run_20261012_frame26_1_full_j4_v1" if key=="26_1" else
               "run_20261012_frame26_2_J4_independent_v1")
   j5=J5ROOT/("run_20261012_frame26_1_global_j5_v1" if key=="26_1" else
               "run_20261012_frame26_2_J5_independent_v1")
  a=read_stage(j4/"run_status.json")
  b=read_stage(j5/"summary.json")
  results.append({"uid":key,"sample":info["sample_id"],"frame":info["frame_id"],
      "baseline_archive":original,
      "input_raw_exists":Path(info["path"]).is_file(),
      "fused_exact_ready":bool((folder/"full_BlackHat_READY.json").is_file()) if not original else True,
      "J4_status":a.get("stage","UNKNOWN") if a else "NOT_RUN",
      "J4_done_tiles":a.get("completed_tiles",0) if a else 0,
      "J4_planned_tiles":a.get("planned_tiles",1620) if a else 1620,
      "J5_status":b.get("stage","UNKNOWN") if b else "NOT_RUN",
      "J5_original_candidate_count":b.get("global_candidate_objects",None) if b else None,
      "J5_area_preserved":b.get("source_area_unchanged",False) if b else False,
      "last_exception":status.get("last_exception","") if status else ""})
 df=pd.DataFrame(results)
 df.to_csv(OUT/"ALL20_J4J5_FULL_REPLAY_STAGE_LEDGER.csv",
            encoding="utf-8-sig",index=False)
 full=sum((x["J4_status"]=="J4_COMPLETE" and x["J5_status"]=="J5_COMPLETE")
          for x in results)
 writejson(OUT/"summary.json",{
   "stage":"FULL_J4_J5_ALL20_REPLAY_TRACKING",
   "num_raw":20,"J4_J5_both_done":full,"remaining":20-full,
   "K8D_E_expansion_and_J5_B_crosschannel_dedup_not_claimed":True,
   "all_frames":results})
 print("J4J5_FULL_STATE",full,"OF",20,"FRAMES",flush=True)
 return results

def run_one(info,tile_batch):
 key=info["uid"];dest=OUT/key
 dest.mkdir(parents=True,exist_ok=True)
 if key in ("26_1","26_2"):
  print("FROZEN_J4_J5_PREVIOUS_ALREADY_COMPLETE",key,flush=True)
  return
 raw=Path(info["path"])
 if not raw.is_file() or raw.stat().st_size!=C.RAW_HEIGHT*C.RAW_WIDTH*2:
  raise ValueError("Raw missing or wrong bytes: "+str(raw))
 runid=f"frozen_full20_{key}_J4_v1"
 j4=J4ROOT/runid
 fused=fused_exact_global(raw,dest/"full_fused_3_5_9_15_31_dn.npy",
                          dest/"full_BlackHat_READY.json")
 snapshot=read_stage(j4/"run_status.json")
 if snapshot and snapshot.get("stage")=="J4_COMPLETE":
  print("FROZEN_J4_ALREADY_COMPLETE",key,flush=True)
 else:
  resumed=j4.is_dir()
  print("FROZEN_J4_BEGIN",key,"resume",resumed,
        "batch",tile_batch if tile_batch else "FULL",flush=True)
  run_j4(runid,max_tiles=tile_batch,halo=64,
         resume=resumed,save_images=False,
         input_raw_file=raw,input_fused_npy=fused,frame_label=key)
 snapshot=read_stage(j4/"run_status.json")
 assert snapshot and snapshot.get("stage") in ("J4_COMPLETE","J4_PARTIAL")
 if snapshot["stage"]=="J4_PARTIAL":
  print("FROZEN_J4_PARTIAL",key,snapshot.get("completed_tiles"),"/1620",flush=True)
  return
 j5run=f"frozen_full20_{key}_J5_v1"
 j5=J5ROOT/j5run
 summ=read_stage(j5/"summary.json")
 if summ is None:
  if j5.exists():raise FileExistsError("Partial J5 output, audit manually "+str(j5))
  print("FROZEN_J5_BEGIN",key,flush=True)
  run_j5(j5run,review_limit=0,input_J4_run=j4,
         input_raw_file=raw,frame_label=key)
  summ=read_stage(j5/"summary.json")
 assert summ and summ.get("stage")=="J5_COMPLETE"
 assert summ["source_area_unchanged"]
 print("FROZEN_J5_FRAME_PASS",key,"global_object",summ["global_candidate_objects"],
       "pixels",summ["source_area_after_pixels"],flush=True)

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--only",nargs="*",default=[])
 p.add_argument("--tile-batch",type=int,default=0,
                help="max new J4 tiles per frame; 0=all")
 a=p.parse_args()
 allraw=inputs()
 if a.only and set(a.only)-set(x["uid"] for x in allraw):
  raise ValueError("unknown frame IDs "+str(a.only))
 OUT.mkdir(parents=True,exist_ok=True)
 for info in allraw:
  if a.only and info["uid"] not in set(a.only):continue
  try:
   run_one(info,a.tile_batch)
  except Exception as exc:
   print("FROZEN_J4J5_FAILED",info["uid"],type(exc).__name__,str(exc),flush=True)
   folder=OUT/info["uid"];folder.mkdir(exist_ok=True)
   writejson(folder/"stage.json",{
    "last_exception":repr(exc),"traceback":traceback.format_exc()})
  finally:
   status_all(allraw)
 status_all(allraw)
if __name__=="__main__":main()
