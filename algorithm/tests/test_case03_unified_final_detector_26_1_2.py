"""Case03 unified final from real 26_1 26_2 J4/J5/K8 source files."""
from pathlib import Path
import json
import pandas as pd,numpy as np,cv2
from config import user_config as C
ROOT=C.OUTPUT_ROOT/"CASE03_UNIFIED_FINAL_DETECTOR_26_1_26_2_20261019_v2"
def source(frame):
 d=ROOT/f"26_{frame}"
 return (pd.read_csv(d/"FINAL_DEFECTS_AND_MEASUREMENTS.csv"),
         pd.read_csv(d/"ALL_ORIGINAL_J5_AND_B_SOURCE_DISPOSITIONS_NO_DROP.csv",
                     low_memory=False))
def test_both_twoframe_final_detected_objects_and_user_approved():
 for f,n in ((1,39),(2,35)):
  df,_=source(f)
  assert len(df)==n
  assert df.final_ID.is_unique
  assert df.human_confirmed_darkspot.sum()==2
  assert set(df.origin_stage).issubset({
    "J5_SIZE_MEDLARGE","B_K8E_GROUP","B_NOVEL_MEDLARGE_SOURCE_ONLY",
    "B_K8I2_USER_CONFIRMED_OR","J5_DIRECTIONAL_SMALL_SCRATCH",
    "UNIFIED_SAME_OBJECT_OR"})

def test_four_approved_original_contours_exact_area():
 for f,expected in ((1,{297,398}),(2,{348,370})):
  df,_=source(f)
  ok=df[df.human_confirmed_darkspot]
  assert set(ok.final_area_detector_px2)==expected
  for a in ok.itertuples(index=False):
   with np.load(a.raw_mask_npz,allow_pickle=False) as z:
    assert int(z["mask"].sum())==a.final_area_detector_px2

def test_no_source_or_mask_data_dropped():
 for f,n in ((1,32370),(2,8332)):
  df,old=source(f)
  assert len(old)==n
  assert not old.candidate_source_uid.duplicated().any()
  assert old.original_source_mask_preserved.all()
  assert not old.human_verified_as_noise.any()
  assert old.final_defect_ID.dropna().isin(df.final_ID).all()
  assert old.final_disposition.notna().all()

def test_J5_all_mediumlarge_and_small_scratch_protected():
 for f,count in ((1,25),(2,26)):
  df,old=source(f)
  a=old[(old.stage=="J5")&
        (old.original_visibility_layer=="J5_WORK_MEDLARGE")]
  assert len(a)==count
  assert a.final_defect_ID.notna().all()
  if f==1:
   assert len(df[df.origin_stage=="J5_DIRECTIONAL_SMALL_SCRATCH"])==1

def test_micro_suggested_noise_not_shown_as_final_defect():
 for f,n in ((1,11524),(2,3168)):
  _,old=source(f)
  micro=old[old.K8C_class=="MICRO_HIDE_SUGGESTION"]
  assert len(micro)==n
  assert micro.final_defect_ID.isna().all()
  assert micro.final_disposition.eq(
       "ALGORITHM_NOISE_SUGGEST_EXCLUDED_SOURCE_RETAINED").all()

def test_true_fullresolution_binary_exact_pixel_area():
 for f in (1,2):
  df,_=source(f)
  path=ROOT/f"26_{f}"/"01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK_11276x9200.png"
  assert path.is_file()
  im=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_GRAYSCALE)
  assert im is not None and im.shape==(C.RAW_HEIGHT,C.RAW_WIDTH)
  assert set(np.unique(im))=={0,255}
  assert int(np.count_nonzero(im))==int(df.final_area_detector_px2.sum())

def test_seven_user_rejected_green_objects_never_into_final_pixels():
 qa=json.loads((ROOT/"26_1/independent_QA.json").read_text(encoding="utf8"))
 assert qa["seven_green_false_proposals_no_pixel_conflict"]
 p=ROOT/"26_1/USER_NEGATIVE_GREEN_VS_FINAL_SPATIAL_CONFLICT_AUDIT.csv"
 assert p.is_file()
 assert len(pd.read_csv(p))==0
 summary=json.loads((ROOT/"26_1/summary.json").read_text(encoding="utf8"))
 assert len(summary["all_green_false_review_group_ids"])==7
 assert "K8I2_F1_B04_G0096" not in summary["all_green_false_review_group_ids"]

def test_no_pending_proposals_in_final_annotation_layer():
 for f in (1,2):
  p=ROOT/f"26_{f}"
  q=json.loads((p/"summary.json").read_text(encoding="utf8"))
  assert q["no_pending_or_noise_overlay_on_final_main"]
  m=cv2.imdecode(np.frombuffer(
      (p/"00_FINAL_DEFECTS_ONLY_fullframe_1to4.png").read_bytes(),np.uint8),
      cv2.IMREAD_COLOR)
  assert m is not None and m.shape[:2]==(C.RAW_HEIGHT//4+90,(C.RAW_WIDTH+3)//4)
  assert (p/"FINAL_LOCAL_RAW_CONTOUR_PROOFS").is_dir()
  assert len(list((p/"FINAL_LOCAL_RAW_CONTOUR_PROOFS").glob("*.png")))==(
      39 if f==1 else 35)
