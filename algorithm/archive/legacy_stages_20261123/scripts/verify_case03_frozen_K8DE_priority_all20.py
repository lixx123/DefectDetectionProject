"""Independent strict 20-RAW K8D/E priority review verification.

Verify immutable all-source B IDs, exact original seed pixels,
three RAW envelopes and true per-group OR masks. Does not turn stable
outlines or candidate counts into confirmed physical defects.
"""
from pathlib import Path
from collections import Counter
import sys,json,math
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_case03_frozen_K8DE_priority_all20 import OUT,ROBUST,inputs
from scripts.run_case03k8i_stage2_fullband_priority_contours import ENABLED_CLASSES
def readpng(p):
 im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
 if im is None:raise IOError(p)
 return im
def exact_union(items,box):
 x0,y0,x1,y1=box
 result=np.zeros((y1-y0,x1-x0),bool)
 for mask,bbox in items:
  left=max(x0,bbox[0]);top=max(y0,bbox[1])
  right=min(x1,bbox[2]);bottom=min(y1,bbox[3])
  if left<right and top<bottom:
   result[top-y0:bottom-y0,left-x0:right-x0]|=mask[
       top-bbox[1]:bottom-bbox[1],left-bbox[0]:right-bbox[0]]
 return result
def frame(info):
 uid=info["uid"];folder=OUT/uid
 meta=json.loads((folder/"status.json").read_text(encoding="utf-8"))
 assert meta["status"]=="PASS"
 src=ROBUST/uid
 underlying=pd.read_csv(src/"ALL_B_SOURCE_CANDIDATE_LEDGER.csv",
                        low_memory=False,encoding="utf-8-sig")
 if uid in ("26_1","26_2"):
  assert meta["scope"]=="FROZEN_K8I2_REFERENCE_NO_RERUN"
  assert meta["B_all_source_count"]==len(underlying)
  assert Path(meta["source_archive"]).exists()
  return {"uid":uid,"original_B":len(underlying),
      "new_RAW_trials":meta["new_raw_trials"],
      "candidate_review_groups":meta["review_group_count"],
      "source_mask_immutability":"ORIGINAL_K8I2_ALREADY_INDEPENDENTLY_AUDITED"}
 assert meta["B_all_source_count"]==len(underlying)
 tab=pd.read_csv(folder/"ALL_ORIGINAL_B_DISPOSITION.csv",encoding="utf-8-sig")
 trails=pd.read_csv(folder/"K8D_PRIORITY_RAW_3_2_1p5MAD_TRIALS.csv",
                    encoding="utf-8-sig")
 gr=pd.read_csv(folder/"K8E_EXACT_OR_GROUPS_PENDING.csv",encoding="utf-8-sig")
 assert len(tab)==len(underlying)
 assert tab.uid.nunique()==len(tab)
 assert tab.source_B_preserved.all() and not tab.automatically_user_approved.any()
 assert len(trails)==sum(x in ENABLED_CLASSES for x in tab.K8C_category)
 assert len(gr)==meta["review_group_count"]
 m=tab.merge(underlying,left_on=["band_id","B_source_label"],right_on=[
          "band_id","band_component_label"],how="outer",indicator=True,
          validate="one_to_one")
 assert m._merge.eq("both").all()
 assert (m.source_area_px2==m.candidate_area_px2).all()
 assert (m.uid==m.candidate_source_uid).all()
 assert (m.K8C_category==m.classification).all()
 allMasks={}
 for band in sorted(tab.band_id.unique()):
  b=readpng(src/f"band{band:02d}/B_adaptive_SOURCE_UNALTERED.png")
  n,lab,stats,_=cv2.connectedComponentsWithStats(np.uint8(b>0),8)
  for row in trails[trails.band_id==band].itertuples(index=False):
   lid=int(row.B_source_label)
   assert int(stats[lid,cv2.CC_STAT_AREA])==int(row.source_area_px2)
   if row.status=="GEOMETRY_REVIEW_SOURCE_ONLY":
    assert not isinstance(row.mask_npz,str) or row.mask_npz==""
    continue
   path=Path(row.mask_npz)
   with np.load(path,allow_pickle=False) as z:
    seed=z["original_B_source"].astype(bool)
    ids=z["original_B_labels"].astype(np.int32)
    outer=z["outer"].astype(bool)
    k3=z["k3"].astype(bool);k2=z["k2"].astype(bool)
    k15=z["k1p5"].astype(bool)
    work=z["workcore"].astype(bool)
    box=tuple(map(int,z["raw_roi_global_xyxy"]))
   assert seed.shape==ids.shape==outer.shape==(128,128)
   assert np.array_equal(seed,ids==lid)
   assert int(seed.sum())==int(row.source_area_px2)
   assert np.all(outer[seed])
   assert int(k3.sum())==row.k3_area_px2
   assert int(k2.sum())==row.k2_area_px2
   assert int(k15.sum())==row.k1p5_area_px2
   assert int(outer.sum())==row.outer_area_px2
   assert not np.any(outer&~work) if row.status.startswith("STABLE_") else True
   if row.status=="SOURCE_ONLY_UNRELIABLE_3MAD":
    assert np.array_equal(seed,outer)
   allMasks[(int(band),lid)]=(outer,box)
 for group in gr.itertuples(index=False):
  k=(int(group.band_id),
       tuple(sorted(map(int,str(group.source_B_labels).split(";")))))
  members=[allMasks[(k[0],x)] for x in k[1]]
  with np.load(group.mask_npz,allow_pickle=False) as z:
   mask=z["exact_review_union"].astype(bool)
   box=tuple(map(int,z["RAW_global_bbox"]))
   orig=set(map(int,z["raw_outer_source_B_labels"]))
  assert orig==set(k[1])
  rebuilt=exact_union(members,box)
  assert np.array_equal(mask,rebuilt)
  assert int(mask.sum())==group.exact_union_area_px2
  assert sum(int(x[0].sum()) for x in members)==group.sum_source_outer_areas_px2
  assert (group.sum_source_outer_areas_px2-int(mask.sum())
          ==group.duplicate_pixels_removed)
  assert not group.user_confirmed and group.production_defect_count_not_approved
 pic=readpng(folder/"K8DE_ALL_PRIORITY_REVIEW_1to8.png")
 assert pic.ndim==3 and pic.shape[0]==C.RAW_HEIGHT//8
 return {"uid":uid,"original_B":len(underlying),
     "new_RAW_trials":len(trails),"new_mask_count":len(allMasks),
     "candidate_review_groups":len(gr),
     "source_mask_immutability":"ALL_PIXEL_AND_OR_UNION_QA_PASS"}

def main():
 reports=[frame(i) for i in inputs()]
 assert len(reports)==20
 s={"stage":"CASE03_20RAW_K8DE_PRIORITY_EXACT_SOURCE_QA_PASS",
   "raw_inputs_pass":len(reports),
   "all_original_B_source_labels_audited":sum(x["original_B"] for x in reports),
   "all_trial_counts":sum(x["new_RAW_trials"] for x in reports),
   "new_pixel_groups_sum":sum(x["candidate_review_groups"] for x in reports),
   "new_physical_defects_approved":0,
   "old_human_approvals_unmodified":True,
   "all_micro_RAW_processed":False,
   "J5_B_crosschannel_production_dedup_finished":False,
   "frames":reports}
 p=OUT/"independent_QA.json"
 if p.exists():raise FileExistsError(p)
 p.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8")
 pd.DataFrame(reports).to_csv(OUT/"INDEPENDENT_ALL20_K8DE_PIXEL_QA.csv",
                              index=False,encoding="utf-8-sig")
 print("CASE03_20RAW_K8DE_PRIORITY_EXACT_SOURCE_QA_PASS",
    "B",s["all_original_B_source_labels_audited"],
    "RAW",s["all_trial_counts"],
    "GROUP",s["new_pixel_groups_sum"],flush=True)
if __name__=="__main__":main()
