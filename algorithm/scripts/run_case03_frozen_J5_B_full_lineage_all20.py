"""New-frame unified no-loss J5 + K8B + K8DE source lineage and review.

No crosschannel physical dedup without exact J5 masks and human approval.
Per-frame frozen J5 object IDs, all experimental B source IDs, and every
priority RAW K8E review group retain their own source and primary layer.
The old two 26 frames keep their immutable reviewed release unchanged.
"""
from pathlib import Path
from collections import Counter,defaultdict
import sys,argparse,json
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03i_size_grade import SizeGradeConfig,grade_size,max_feret_centers_px
from src.detection.case03k8g_display_boxes import expand_bbox_xyxy,bbox_to_display_px
from scripts.run_case03frozen_all20_robustness import inputs,OUT as ABC
from scripts.run_case03_frozen_J4J5_full_all20 import status_all
from scripts.run_case03_frozen_K8DE_priority_all20 import OUT as DE
from scripts.run_case03k8g_1p5_display_boxes import write_lossless
OUT=C.OUTPUT_ROOT/"CASE03_FROZEN_CROSSCHANNEL_REVIEW_20RAW_20261019_v1"
J5ROOT=C.OUTPUT_ROOT/"case03j5_global"
SC=SizeGradeConfig()
def readpng(path):
 im=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
 if im is None:raise IOError(path)
 return im
def writejson(path,obj):
 path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
def rect(img,bbox,stride,color):
 expanded=expand_bbox_xyxy(bbox,(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
 a,b,c,d=bbox_to_display_px(expanded,(C.RAW_WIDTH,C.RAW_HEIGHT),
     (img.shape[1],img.shape[0]),stride)
 cv2.rectangle(img,(a,b),(c,d),color,1,cv2.LINE_8)
 return (a,b,c,d)
def run_frame(info,js):
 uid=info["uid"];dest=OUT/uid
 status=dest/"status.json"
 if status.exists():
  done=json.loads(status.read_text(encoding="utf-8"))
  if done.get("status")=="PASS":return done
  if done.get("status")!="WAITING_J5":raise RuntimeError("Existing nonPASS requires manual review")
 if uid in ("26_1","26_2"):
  dest.mkdir(parents=True,exist_ok=True)
  s={"uid":uid,"status":"PASS","source":"FROZEN_K8I_AND_USER_REVIEW_ALREADY_PUBLISHED",
     "history":"CASE03_FROZEN_RELEASE_20261019_v2",
     "do_not_rewrite_F1_F2_confirmed_masks":True}
  writejson(status,s);return s
 if js["J5_status"]!="J5_COMPLETE":
  dest.mkdir(parents=True,exist_ok=True)
  s={"uid":uid,"status":"WAITING_J5","J4_tiles":js["J4_done_tiles"],
    "J4_stage":js["J4_status"],"J5_stage":js["J5_status"],
    "K8ABC_and_K8DE_raw_sources_retained":True}
  writejson(status,s);return s
 # Frozen globally reconciled J5 objects and per-RAW stage B source ledger.
 j5file=J5ROOT/f"frozen_full20_{uid}_J5_v1"/"global_defects.csv"
 j5=pd.read_csv(j5file,encoding="utf-8-sig")
 b=pd.read_csv(ABC/uid/"ALL_B_SOURCE_CANDIDATE_LEDGER.csv",
               low_memory=False,encoding="utf-8-sig")
 groups=pd.read_csv(DE/uid/"K8E_EXACT_OR_GROUPS_PENDING.csv",
                    encoding="utf-8-sig")
 astatus=json.loads((ABC/uid/"status.json").read_text(encoding="utf-8"))
 assert len(j5)==js["J5_original_candidate_count"]
 assert len(b)==astatus["B_all_source_object_count"]
 reg=readpng(ABC/uid/"K8A_region_type_fullres.png")
 ids=readpng(ABC/uid/"K8A_band_id_fullres.png")
 assert reg.shape==ids.shape==(C.RAW_HEIGHT,C.RAW_WIDTH)
 dest.mkdir(parents=True,exist_ok=True)
 review=np.asarray(readpng(ABC/uid/"B_ALL_wholeframe_1to8.png"),np.uint8)
 main=review.copy()
 proposals=review.copy()
 entries=[]
 workmedium=0
 for v in j5.itertuples(index=False):
  x=float(v.center_x_global);y=float(v.center_y_global)
  iy=max(0,min(C.RAW_HEIGHT-1,int(round(y))))
  ix=max(0,min(C.RAW_WIDTH-1,int(round(x))))
  zone=int(reg[iy,ix]);band=int(ids[iy,ix])
  grade=str(v.grade)
  if zone==2:
   layer="J5_WORK_MEDLARGE" if grade in ("MEDIUM","LARGE") else "J5_WORK_SMALL"
  else:
   layer="J5_OUTSIDE_WORK_OR_EDGE_REFERENCE"
  if layer=="J5_WORK_MEDLARGE":
   bbox=(int(v.display_bbox_x_global),int(v.display_bbox_y_global),
      int(v.display_bbox_xmax_inclusive)+1,int(v.display_bbox_ymax_inclusive)+1)
   rect(main,bbox,8,(34,61,232) if grade=="LARGE" else (28,210,232))
   workmedium+=1
  entries.append({"stage":"J5","raw_uid":uid,
    "candidate_source_uid":f"J5:{uid}:{v.global_defect_id}",
    "original_source_id":str(v.global_defect_id),
    "band_id":band,"work_region_code_at_center":zone,
    "primary_review_layer":layer,
    "source_area_px2":int(v.source_area_px2),
    "raw_contour_trial_done":False,
    "crosschannel_link":"UNASSESSED_J5_TO_B",
    "human_confirmed":False,
    "source_ID_unchanged":True})
 byband=defaultdict(dict)
 for g in groups.itertuples(index=False):
  for label in str(g.source_B_labels).split(";"):
   if label:byband[int(g.band_id)][int(label)]=str(g.review_group_id)
 for v in b.itertuples(index=False):
  band=int(v.band_id);lid=int(v.band_component_label)
  group=byband[band].get(lid,"")
  layer=("B_K8DE_RAW_GROUP_PENDING" if group else
       "B_MICRO_HIDE_SUGGESTION_RETAINED"
       if str(v.classification)=="MICRO_HIDE_SUGGESTION" else
       "B_OTHER_SOURCE_RETAINED")
  entries.append({"stage":"K8B","raw_uid":uid,
    "candidate_source_uid":str(v.candidate_source_uid),
    "original_source_id":str(lid),"band_id":band,
    "work_region_code_at_center":2,
    "primary_review_layer":layer,
    "source_area_px2":int(v.candidate_area_px2),
    "raw_contour_trial_done":bool(group),
    "crosschannel_link":"UNASSESSED_J5_TO_B",
    "K8DE_review_group_id":group,
    "human_confirmed":False,"source_ID_unchanged":True})
 assert len(entries)==len(j5)+len(b)
 assert len({x["candidate_source_uid"] for x in entries})==len(entries)
 reviewed=0;main_groups=0;detail=[]
 for g in groups.itertuples(index=False):
  file=Path(g.mask_npz)
  with np.load(file,allow_pickle=False) as z:
   mask=z["exact_review_union"].astype(bool)
   rx0,ry0,rx1,ry1=map(int,z["RAW_global_bbox"])
  assert mask.sum()==int(g.exact_union_area_px2)
  yy,xx=np.where(mask)
  bbox=(rx0+int(xx.min()),ry0+int(yy.min()),
        rx0+int(xx.max())+1,ry0+int(yy.max())+1)
  length=max_feret_centers_px(np.column_stack((xx,yy)))
  grade,_=grade_size(len(xx),length,SC)
  rect(proposals,bbox,8,(22,161,241))
  if grade in ("MEDIUM","LARGE"):
   rect(main,bbox,8,(25,170,240))
   main_groups+=1
  detail.append({"review_group_id":g.review_group_id,
    "raw_uid":uid,"source_B_labels":g.source_B_labels,
    "exact_review_area_px2":int(len(xx)),
    "original_source_area_sum_px2":int(g.sum_source_outer_areas_px2),
    "detector_image_Feret_px":round(length,4),
    "detector_image_Feret_um_equiv":round(length*C.PIXEL_SIZE_UM,3),
    "grade_not_physical":grade,
    "review_bbox_global_xyxy":json.dumps(bbox),
    "cross_J5_same_defect_unresolved":True,
    "user_approved":False})
  reviewed+=1
 pd.DataFrame(entries).to_csv(dest/"ALL_J5_AND_B_SOURCE_LINEAGE_NO_LOSS.csv",
                              encoding="utf-8-sig",index=False)
 pd.DataFrame(detail).to_csv(dest/"RAW_REVIEW_GROUP_AREA_FERET_NOT_APPROVED.csv",
                             encoding="utf-8-sig",index=False)
 write_lossless(dest/"01_J5_WORK_MEDLARGE_plus_K8DE_MEDLARGE_PENDING_1to8.png",main)
 write_lossless(dest/"02_ALL_K8DE_RAW_GROUPS_PENDING_WITH_ALL_B_SOURCES_1to8.png",proposals)
 s={"uid":uid,"status":"PASS","all_J5_original_candidates":len(j5),
   "all_B_original_candidates":len(b),
   "combined_stage_source_UIDs":len(entries),
   "J5_WORK_MEDLARGE_provisional":workmedium,
   "K8DE_all_pending_groups":reviewed,
   "K8DE_MEDLARGE_pending_groups":main_groups,
   "original_J5_total_source_area_px2":int(j5.source_area_px2.sum()),
   "source_areas_and_IDs_unmodified":True,
   "true_crosschannel_dedup":False,
   "approval_automatically_assigned":0,
   "raw_detector_image_plane_magnification_uncalibrated":True}
 writejson(status,s)
 print("CROSSCHANNEL_STAGE_SOURCE_LINEAGE_PASS",uid,
       "J5",len(j5),"B",len(b),"GROUPS",reviewed,flush=True)
 return s
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--only",nargs="*",default=[])
 args=p.parse_args()
 raw=inputs()
 if args.only and set(args.only)-{x["uid"] for x in raw}:
  raise ValueError("Invalid --only uid")
 jmap={x["uid"]:x for x in status_all(raw)}
 OUT.mkdir(parents=True,exist_ok=True)
 for x in raw:
  if args.only and x["uid"] not in args.only:continue
  run_frame(x,jmap[x["uid"]])
 reports=[]
 for x in raw:
  path=OUT/x["uid"]/"status.json"
  reports.append(json.loads(path.read_text(encoding="utf-8"))
      if path.exists() else {"uid":x["uid"],"status":"NOT_RUN"})
 summary={"stage":"J5_PLUS_B_NO_SILENT_SOURCE_OR_REVIEW_LOSS",
  "frames_pass":sum(z["status"]=="PASS" for z in reports),
  "frames_waiting_J5":sum(z["status"]=="WAITING_J5" for z in reports),
  "frames_not_run":sum(z["status"]=="NOT_RUN" for z in reports),
  "J5_B_physical_dedup_unimplemented":True,"all_human_truth_unaffected":True,
  "frames":reports}
 writejson(OUT/"summary.json",summary)
 print("CROSSCHANNEL_SUMMARY",summary["frames_pass"],"PASS",
       summary["frames_waiting_J5"],"WAITING_J5",flush=True)
if __name__=="__main__":main()
