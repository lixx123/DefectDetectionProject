"""Frozen release full-stage inventory and 20-RAW robustness tests."""
from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np,cv2
from config import user_config as C
RELEASE=C.OUTPUT_ROOT/"CASE03_FROZEN_RELEASE_20261019_v2"
ROBUST=C.OUTPUT_ROOT/"CASE03_FROZEN_ROBUSTNESS_20RAW_20261019_v3"

def test_pipeline_26_steps_all_explicit_and_code_exists():
 m=json.loads((RELEASE/"FROZEN_PIPELINE_AND_FILES_SHA256.json").read_text(encoding="utf-8"))
 stages=m["registered_stages"]
 assert len(stages)==26
 assert len({s["stage"] for s in stages})==26
 assert all(s["guard"]=="DO_NOT_SILENTLY_OMIT" for s in stages)
 for s in stages:
  assert s["source_files"] and all(
      f["exists"] and f["sha256"] and (C.PROJECT_ROOT/f["file"]).is_file()
      for f in s["source_files"])
 labels={x["stage"] for x in stages}
 assert all(x in labels for x in [
   "00_RAW_READ","02_MULTISCALE_BLACKHAT","03E_E2_H_ANCHORED_EXTENSIONS",
   "03G_REVERSIBLE_NOISE_GATE","03H_BACKGROUND_TEXTURE_DoG",
   "03J4_TILED_FULLSCAN","03J5_GLOBAL_STITCH",
   "03K8A_DYNAMIC_WORKBANDS","03K8B_PER_BAND_THRESHOLDS",
   "03K8C_NOISE_TRIAGE","03K8D_SEEDED_RAW_OUTER",
   "03K8E_PIXEL_EXACT_ASSOCIATION","03K8F_HUMAN_APPROVAL_LEDGER",
   "03K8I_FULL_SOURCE_PROVENANCE","04_ROBUSTNESS_HOLDOUT"])
 assert any("J4" in x["stage"] and x["execution_coverage"]=="J4_26_1_2"
            for x in stages)
 assert m["worklist_for_all20"].startswith("The J4/J5")

def test_55_frozen_image_csv_json_copies_not_corrupted():
 m=json.loads((RELEASE/"FROZEN_PIPELINE_AND_FILES_SHA256.json").read_text(encoding="utf-8"))
 assert len(m["immutable_exports"])==55
 for o in m["immutable_exports"]:
  p=RELEASE/o["release_path"]
  assert p.is_file()
  assert p.stat().st_size==o["bytes"]
  h=hashlib.sha256()
  with p.open("rb") as f:
   for chunk in iter(lambda:f.read(4*1024*1024),b""):h.update(chunk)
  assert h.hexdigest()==o["sha256"]

def test_original26_1_and26_2_visible_every_layer_and_human_confirmed():
 m=json.loads((RELEASE/"LATEST_APPROVAL_AWARE_MAIN_PNG_MANIFEST.json").read_text(encoding="utf-8"))
 assert len(m["frames"])==2
 for v in m["frames"]:
  frame=v["frame"];p=RELEASE/f"26_{frame}"
  assert (p/"00_LATEST_APPROVAL_AWARE_FULLFRAME_ALL_PENDING_PRESERVED.png").is_file()
  assert v["approved_darkspots_added"]==2
  assert {o["area"] for o in v["approved"]}==({398,297} if frame==1 else {348,370})
  assert v["not_hide_other_candidates"]
  assert (p/"SOURCE_ALL_J5_B_LINEAGE.csv").is_file()
  assert (p/"04_ALL_MICRO_SUGGEST_HIDE_NOT_DELETED.png").is_file()
  assert (p/"09_STAGE2_ALL_RAW_GROUPS_REVIEW.png").is_file()
 assert (RELEASE/"26_1/USER_CONFIRMED/two_user_confirmed_darkspots_no_duplicate_area.csv").exists()
 assert (RELEASE/"26_2/PRIOR_2_USER_APPROVED/workband_unified_candidate_review_register.csv").exists()

def test_20_allK8ABC_pass_exactly_unreviewed_other18():
 q=json.loads((ROBUST/"independent_QA.json").read_text(encoding="utf-8"))
 assert q["pass_count"]==20 and q["fail_count"]==0
 assert q["bands_count_all_frames"]=={"4":20}
 assert q["B_source_objects_all20_total"]==317673
 assert q["K8C_micro_suggest_hide_source_total_not_deleted"]==211349
 assert q["K8C_strong_raw_support_pending_total"]==287
 assert not q["complete_J4_J5_K8D_K8E_All20"]
 df=pd.read_csv(ROBUST/"INDEPENDENT_20_FRAME_PIXEL_SOURCE_AUDIT.csv")
 assert len(df)==20 and len(set(zip(df.sample_id,df.frame_id)))==20
 assert df.K8A_B_C_source_integrity.eq("PASS").all()
 assert df[df.sample_id==26].set_index("frame_id").loc[1,"B_candidate_source_objects"]==16766
 assert df[df.sample_id==26].set_index("frame_id").loc[2,"B_candidate_source_objects"]==3892
 assert df[df.sample_id!=26].J4_J5_fullprocess.eq("NOT_RUN").all()

def test_all_contact_sheet_pngs_exist_and_four_20raw_images():
 d=RELEASE/"ROBUSTNESS_20RAW_K8A_B_C"
 for name in (
  "20_RAW_RAW_WORKBAND_CONTACT_SHEET_5samples_x_4frames.png",
  "20_RAW_ALL_B_CONTACT_SHEET_5samples_x_4frames.png",
  "20_RAW_K8C_PROMISING_PENDING_CONTACT_SHEET_5samples_x_4frames.png",
  "20_RAW_K8C_MICRO_SUGGEST_HIDE_CONTACT_SHEET_5samples_x_4frames.png"):
  p=d/name
  assert p.is_file() and p.stat().st_size>30000
  img=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
  assert img is not None and img.shape[0]>=2500 and img.shape[1]>=2600

def test_no_silent_omission_26_stages_times_20_frames_and_correct_order():
    path=RELEASE/"PIPELINE_26_STAGES_X_20RAW_EXECUTION_COVERAGE_v2.csv"
    table=pd.read_csv(path,encoding="utf-8-sig")
    assert len(table)==520
    assert table.raw_uid.nunique()==20
    assert table.stage.nunique()==26
    assert not table.duplicated(["raw_uid","stage"]).any()
    for uid,t in table.groupby("raw_uid",sort=False):
        assert t.stage_order.tolist()==list(range(1,27))
        assert t.not_hidden_from_pipeline.all()
        for r in t.itertuples():
            if not (uid in ("26_1","26_2")) and r.stage in (
                  "03J4_TILED_FULLSCAN","03J5_GLOBAL_STITCH"):
                assert r.status=="NOT_RUN_FULL_J4_J5_PER_FRAME"
    m=json.loads((RELEASE/"PIPELINE_20RAW_NO_SILENT_STAGE_OMISSION_AUDIT_v2.json").read_text(encoding="utf-8"))
    assert m["stages_recorded"]==26 and m["raw_frames_recorded"]==20
    assert m["source_stages_omitted"]==0 and m["audit_stage_frame_rows"]==520
    assert m["still_pending_stage_frame_rows"]==252
    assert not m["all20_complete_J4_J5_K8D_E"]
