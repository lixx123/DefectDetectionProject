"""Source-safe RAW/BlackHat diagnostics for retargeted clicks and undersegmented box.

These statistics are descriptive and do not establish a physical filter defect.
"""
from pathlib import Path
import csv
import sys
import json
import numpy as np
import cv2

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config
from src.detection.thresholding import load_packed_mask

SRC=ROOT/"outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v1"
NPZS=ROOT/"outputs/case03c_revision/run_20261009_reference_feature_review/patches"
SPath=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1/fused_S_TL230_TH230.npz"
HPath=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1/fused_H_TL170_TH230.npz"
raw_path=user_config.DATA_ROOT/"26 (1).raw"
response_path=ROOT/"outputs/case02/run_20260930_153727/samples/sample_26_frame_1/responses/blackhat_fused.npz"

def readcsv(path):
 with path.open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def writecsv(path,rows):
 with path.open("w",encoding="utf-8-sig",newline="") as f:
  fields=list(dict.fromkeys(k for item in rows for k in item))
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def clip_window(x,y,rad,shape):
 h,w=shape
 return max(0,x-rad),max(0,y-rad),min(w,x+rad+1),min(h,y+rad+1)
def roi_summ(raw,bhat,s,h):
 return {
  "pixels":int(s.size),"raw_median_dn":float(np.median(raw)),
  "raw_p5_dn":float(np.percentile(raw,5)),
  "raw_p95_dn":float(np.percentile(raw,95)),
  "response_max_dn":int(np.max(bhat)),
  "response_median_dn":float(np.median(bhat)),
  "response_p90_dn":float(np.percentile(bhat,90)),
  "response_p99_dn":float(np.percentile(bhat,99)),
  "response_over_170_px":int(np.count_nonzero(bhat>=170)),
  "response_over_230_px":int(np.count_nonzero(bhat>=230)),
  "S230_count":int(s.sum()),"H170_count":int(h.sum()),
 }
def write_png(path,im):
 ok,buf=cv2.imencode(".png",im)
 if not ok:raise IOError(path)
 path.write_bytes(buf.tobytes())
def image_for_area(raw,rsp,S,H,center,pt=None,box=None):
 gray=raw.astype(np.float32)
 lo,hi=np.percentile(gray,[1,99.5]);hi=max(hi,lo+1)
 base=np.uint8(np.clip((gray-lo)/(hi-lo)*255,0,255))
 overlay=np.stack([base,base,base],axis=2)
 overlay[S]=np.array([255,222,30],dtype=np.uint8)
 overlay[H & ~S]=np.array([31,230,232],dtype=np.uint8)
 if pt:
  cv2.drawMarker(overlay,pt,(16,16,255),markerType=cv2.MARKER_CROSS,markerSize=11,thickness=1)
 if box:cv2.rectangle(overlay,box[0],box[1],(17,228,88),1)
 out=np.concatenate([np.stack([base,base,base],axis=2),overlay],axis=1)
 scale=max(1,int(560//max(out.shape[:2])))
 if scale>1:out=cv2.resize(out,None,fx=scale,fy=scale,interpolation=cv2.INTER_NEAREST)
 return out

def main():
 rows=readcsv(SRC/"pixel_retarget_associations.csv")
 raw=np.memmap(raw_path,mode="r",dtype=">u2",shape=(9200,11276))
 with np.load(response_path,allow_pickle=False) as f:
  response=np.asarray(f["fused_response_dn"])
 S=load_packed_mask(SPath)
 H=load_packed_mask(HPath)
 assert S.shape==H.shape==response.shape==raw.shape
 source_metas={str(p):[p.stat().st_size,p.stat().st_mtime_ns] for p in (raw_path,response_path,SPath,HPath)}
 details=[]
 (SRC/"diagnostic_figures").mkdir(exist_ok=True)
 for i,r in enumerate(rows,1):
  if r["mode"]=="point":
   x=int(r["raw_global_x"]);y=int(r["raw_global_y"])
   click_raw=int(raw[y,x]);click_rsp=int(response[y,x])
   x0,y0,x1,y1=clip_window(x,y,16,S.shape)
   winr=np.asarray(raw[y0:y1,x0:x1],dtype=np.uint16)
   winb=response[y0:y1,x0:x1]
   ws=S[y0:y1,x0:x1];wh=H[y0:y1,x0:x1]
   z=roi_summ(winr,winb,ws,wh)
   z.update(annotation_id=r["annotation_id"],review_id=r["review_id"],
            mode="point",global_x=x,global_y=y,center_RAW_DN=click_raw,
            center_BlackHat_DN=click_rsp,raw_median_in_33px=float(np.median(winr)),
            H_distance_if_nohit=r.get("nearest_H_distance_px",""),
            nearest_H_ID_for_inspection_only=r.get("nearest_H_candidate_id_suggestion",""),
            full_component_ID_exact=r.get("exact_H_candidate_id",""))
   details.append(z)
   # image row point +/-32 (max 65 px): center RAW and overlay
   bx0,by0,bx1,by1=clip_window(x,y,32,S.shape)
   viz=image_for_area(np.asarray(raw[by0:by1,bx0:bx1],dtype=np.uint16),
          response[by0:by1,bx0:bx1],S[by0:by1,bx0:bx1],H[by0:by1,bx0:bx1],
          (x,y),pt=(x-bx0,y-by0))
   write_png(SRC/"diagnostic_figures"/f"{i:02d}_{r['review_id']}_target_point.png",viz)
  else:
   x0,y0,x1,y1=(int(r[k]) for k in ("raw_global_x0","raw_global_y0","raw_global_x1","raw_global_y1"))
   wr=np.asarray(raw[y0:y1,x0:x1],dtype=np.uint16)
   rsp=response[y0:y1,x0:x1];ws=S[y0:y1,x0:x1];wh=H[y0:y1,x0:x1]
   data=roi_summ(wr,rsp,ws,wh)
   # Outer rectangular band (10px), excluding complete box and all H candidate pixels
   bx0,by0,bx1,by1=max(0,x0-10),max(0,y0-10),min(11276,x1+10),min(9200,y1+10)
   rr=np.asarray(raw[by0:by1,bx0:bx1],dtype=np.uint16)
   ring=np.ones(rr.shape,dtype=bool)
   ring[y0-by0:y1-by0,x0-bx0:x1-bx0]=False
   ring &= ~H[by0:by1,bx0:bx1]
   vals=rr[ring]
   rmedian=float(np.median(vals)) if len(vals) else None
   d=rmedian-float(np.median(wr)) if len(vals) else None
   data.update(annotation_id=r["annotation_id"],review_id=r["review_id"],
        mode="box",global_x0=x0,global_y0=y0,global_x1=x1,global_y1=y1,
        ring_eligible_count=int(len(vals)),raw_reference_median_dn=rmedian,
        box_minus_ring_delta_dn=d,
        note="Rectangle not pixel-level defect truth; no H candidate in selected ROI" if not wh.any() else "some threshold pixels in ROI")
   details.append(data)
   bx0,by0,bx1,by1=max(0,x0-32),max(0,y0-32),min(11276,x1+32),min(9200,y1+32)
   viz=image_for_area(np.asarray(raw[by0:by1,bx0:bx1],dtype=np.uint16),response[by0:by1,bx0:bx1],
         S[by0:by1,bx0:bx1],H[by0:by1,bx0:bx1],(x0,y0),box=((x0-bx0,y0-by0),(x1-bx0,y1-by0)))
   write_png(SRC/"diagnostic_figures"/f"{i:02d}_{r['review_id']}_target_box.png",viz)
 for row in details:
  if row["mode"]=="point":
   print(row["review_id"],row["global_x"],row["global_y"],"raw",row["center_RAW_DN"],
         "bhat",row["center_BlackHat_DN"],"S/H(33px)",row["S230_count"],row["H170_count"],
         "Hdist",row["H_distance_if_nohit"],flush=True)
  else:
   print(row["review_id"],"BOX",row,flush=True)
 writecsv(SRC/"point_box_local_response_diagnostics.csv",details)
 end={str(p):[p.stat().st_size,p.stat().st_mtime_ns] for p in (raw_path,response_path,SPath,HPath)}
 assert end==source_metas
 print("LOCAL_DIAGNOSTIC_PNG",len(list((SRC/"diagnostic_figures").glob("*.png"))))
if __name__=="__main__":
 main()
