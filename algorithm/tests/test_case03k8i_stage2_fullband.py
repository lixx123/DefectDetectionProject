"""K8I Stage2 actual two-frame saved pipeline and non-deletion tests.

The only permitted output of new RAW proposals is review. No changes to
source J5/B, historical approved K8E groups, or production defect IDs.
"""
from pathlib import Path
import json
import numpy as np,pandas as pd,cv2
from config import user_config as C
ROOT=C.OUTPUT_ROOT/"case03k8i_stage2_RAW_review_and_association/run_20261017_twoframes_priority_evidence_v1"

def data(f):
 p=ROOT/f"frame26_{f}"
 return (pd.read_csv(p/"ALL_B_STAGE2_processing_disposition.csv"),
         pd.read_csv(p/"new_evidence_RAW_trial_results.csv"),
         pd.read_csv(p/"new_exact_group_union_review.csv"))

def test_every_source_has_explicit_disposition():
 for f,expected in ((1,16766),(2,3892)):
  all_rows,_,_=data(f)
  assert len(all_rows)==expected
  assert not all_rows.duplicated(["band_id","B_label"]).any()
  assert all_rows.candidate_source_preserved.all()
  assert not all_rows.production_count_changed.any()

def test_new_priority_is_frozen_three_K8C_review_classes_only():
 allowed={"PROMISING_DARK_REVIEW","UNCERTAIN_REVIEW","BOUNDARY_REVIEW"}
 for f,n in ((1,131),(2,5)):
  rows,new,_=data(f)
  selected=rows[rows.stage2_tier=="NEW_RAW_EVIDENCE_REVIEW"]
  assert len(selected)==len(new)==n
  assert set(selected.K8C_classification).issubset(allowed)
  assert new.source_mask_exact.all()

def test_micro_and_fixed_sources_are_not_automatically_hidden_or_deleted():
 for f in (1,2):
  rows,_,_=data(f)
  for c,typ in [
   ("MICRO_HIDE_SUGGESTION","MICRO_SUGGEST_HIDE_SOURCE_RETAINED_NO_NEW_RAW"),
   ("MICRO_REVIEW","MICRO_REVIEW_SOURCE_RETAINED_NO_NEW_RAW"),
   ("EXISTING_FIXED_H","FIXED_H_SOURCE_REFERENCE_NO_NEW_RAW")]:
   matches=rows[rows.K8C_classification==c]
   # Some already processed K8D members can exist in micro class:
   leftovers=matches[~matches.stage2_tier.str.startswith("REUSE_")]
   assert leftovers.stage2_tier.eq(typ).all()
   assert leftovers.candidate_source_preserved.all()

def test_stable_vs_no_strict_anchor_never_automatically_approve():
 for f in (1,2):
  _,trials,_=data(f)
  assert not trials.human_confirmed_by_this_run.any()
  strict=trials[trials.stage2_review_status=="SOURCE_ONLY_UNRELIABLE_3MAD"]
  assert strict.K8D_trial_outer_area_px2.eq(strict.source_area_px2).all()
  assert strict.k3_area_px2.eq(0).any()

def test_exact_triple_overlap_keeps_each_source_label():
 _,trial,group=data(1)
 z=group[group.new_source_B_labels=="2424;2444;2504"]
 assert len(z)==1
 obj=z.iloc[0]
 assert int(obj.new_exact_union_area_px2)==297
 assert int(obj.new_RAW_source_areas_sum_px2)==870
 assert int(obj.new_internal_duplicate_pixels_removed)==573
 assert obj.approval_status=="PENDING_MANUAL_REVIEW"
 with np.load(obj.npz_file,allow_pickle=False) as m:
  assert int(m["exact_review_union"].sum())==297
  assert set(m["raw_outer_source_B_labels"])=={2424,2444,2504}
 assert not obj.is_user_confirmed

def test_new_overlaps_existing_are_ambiguous_not_id_merged():
 _,_,g=data(1)
 coll=g[g.old_K8D_B_mask_overlap_json!="[]"]
 assert len(coll)==3
 assert coll.approval_status.eq("PENDING_OLD_OUTER_OVERLAP_REVIEW").all()
 assert g.no_old_K8E_group_ID_merged.all()
 assert g.original_sources_unchanged.all()

def test_frozen_two_approved_objects_still_original_area():
 frozen=pd.read_csv(ROOT/"frame26_2"/
       "ALL_FROZEN_AND_NEW_RAW_REVIEW_GROUPS_no_ID_merge.csv")
 appr=frozen[frozen.user_approved_darkspot_and_group]
 assert set(appr.review_group_id)=={"K8E_F2_B2_G006","K8E_F2_B2_G009"}
 assert set(appr.outer_review_px2)=={348,370}
 assert not frozen.source_modified.any()
 assert not frozen[frozen.source_stage=="NEW_K8I_STAGE2_REVIEW"].user_approved_darkspot_and_group.any()

def test_review_layer_pngs_and_separate_full_frame_audits_exist():
 for f,expected in ((1,129),(2,5)):
  p=ROOT/f"frame26_{f}"
  old=pd.read_csv(p/"ALL_FROZEN_AND_NEW_RAW_REVIEW_GROUPS_no_ID_merge.csv")
  assert len(old)==expected+(13 if f==1 else 18)
  for filename in [
    "01_STAGE2_NEW_RAW_GROUPS_REVIEW_plus_original_K8I_main.png",
    "02_NEW_RAW_GROUPS_ALL_review_1to4.png",
    "03_ONLY_NEW_STABLE_RAW_GROUPS_review_1to4.png",
    "04_OLD_RAW_or_J5_bbox_OVERLAP_review_1to4.png"]:
   buf=(p/filename).read_bytes()
   img=cv2.imdecode(np.frombuffer(buf,np.uint8),cv2.IMREAD_COLOR)
   assert img is not None and img.shape[1]==2819
  s=json.loads((p/"summary.json").read_text(encoding="utf-8"))
  assert s["source_objects_omitted"]==0
  assert s["approved_groups_changed"]==0

def test_B2_1787_vs_frozen_K8D_1902_is_exact_same_RAW_outer_but_not_automerged():
 from src.detection.case03k8e_group_hypothesis import global_intersection
 newfile=ROOT/"frame26_1"/"band02"/"F1_B2_C01787_full_RAW_trial.npz"
 oldfile=C.OUTPUT_ROOT/"case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3/frame26_1/band02/F1_B2_C01902_K8D_all_masks.npz"
 with np.load(newfile,allow_pickle=False) as z:
  a={"box":tuple(map(int,z["RAW_roi_global_xyxy"])),
     "mask":z["new_full_RAW_review_outer"].astype(bool)}
 with np.load(oldfile,allow_pickle=False) as z:
  b={"box":tuple(map(int,z["raw_global_roi_xyxy"])),
     "mask":z["K8D_full_outer"].astype(bool)}
 geo=global_intersection(a,b)
 assert geo["intersection_px2"]==398
 assert geo["union_px2"]==398
 assert geo["iou"]==1.0
 group=pd.read_csv(ROOT/"frame26_1"/"new_exact_group_union_review.csv")
 new=group[(group.band_id==2)&(group.new_source_B_labels.astype(str)=="1787")]
 assert len(new)==1
 assert new.iloc[0].approval_status=="PENDING_OLD_OUTER_OVERLAP_REVIEW"
 assert not new.iloc[0].is_user_confirmed
