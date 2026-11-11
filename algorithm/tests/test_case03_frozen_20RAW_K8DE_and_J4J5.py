"""Regression for frozen 20 RAW K8ABC + priority K8DE and explicit J4J5 pending.

Scope is precisely execution completeness, original pixel/ID traceability
and zero false claims of human-confirmed physical object counts.
"""
from pathlib import Path
import json
import pandas as pd
import numpy as np
import cv2
from config import user_config as C
ROOT=C.OUTPUT_ROOT
VAL=ROOT/"CASE03_FROZEN_20RAW_VALIDATION_20261019_v1"
DE=ROOT/"CASE03_FROZEN_K8DE_PRIORITY_ALL20_20261019_v1"
J4J5=ROOT/"CASE03_FROZEN_FULL_J4J5_20RAW_20261019_v1"

def test_20_K8DE_priority_pass_without_auto_physical_approval():
 s=json.loads((DE/"summary.json").read_text(encoding="utf-8"))
 qa=json.loads((DE/"independent_QA.json").read_text(encoding="utf-8"))
 assert s["frames_pass"]==qa["raw_inputs_pass"]==20
 assert s["frames_fail"]==s["frames_not_run"]==0
 assert qa["all_original_B_source_labels_audited"]==317673
 assert qa["all_trial_counts"]==4643
 assert qa["new_pixel_groups_sum"]==4546
 assert qa["new_physical_defects_approved"]==0
 assert not qa["all_micro_RAW_processed"]
 assert not qa["J5_B_crosschannel_production_dedup_finished"]

def test_18_new_K8DE_source_dispositions_cover_all_B_without_hidden_drop():
 for info in json.loads((DE/"summary.json").read_text(encoding="utf-8"))["frames"]:
  assert info["status"]=="PASS"
  assert info["source_B_pixels_modified"] is False
  assert info["new_user_confirmation_count"]==0
  if info["uid"] in ("26_1","26_2"):
   assert info["scope"]=="FROZEN_K8I2_REFERENCE_NO_RERUN"
   continue
  df=pd.read_csv(DE/info["uid"]/"ALL_ORIGINAL_B_DISPOSITION.csv",
                 encoding="utf-8-sig")
  assert len(df)==info["B_all_source_count"]
  assert df.uid.nunique()==len(df)
  assert df.source_B_preserved.all()
  assert not df.automatically_user_approved.any()
  assert len(df[df.processing_tier=="K8D_PRIORITY_RAW_PENDING"])==info["new_raw_trials"]

def test_26_algorithm_stages_have_20_unique_frame_dispositions():
 d=pd.read_csv(VAL/"CURRENT_26_ALGORITHM_STAGES_X_20_RAW_SCOPE_LEDGER.csv",
                encoding="utf-8-sig")
 assert len(d)==520 and d.stage.nunique()==26 and d.uid.nunique()==20
 assert not d.duplicated(["uid","stage"]).any()
 assert d.not_hidden_from_pipeline if "not_hidden_from_pipeline" in d.columns else d.no_silent_source_filtering.all()
 assert d.raw_provenance_unchanged.all()
 assert d.loc[d.stage=="03K8D_SEEDED_RAW_OUTER","actual_execution_status"].str.contains("MICRO_UNEXPANDED").all()
 assert d.loc[d.stage=="03J5_GLOBAL_STITCH","actual_execution_status"].isin(
        ["PASS_GLOBAL_J5_SOURCE_AREA_PRESERVED","NOT_RUN_J4_INCOMPLETE"]).all()

def test_frozen_J4J5_four_26_raw_frames_completed_area_kept():
 j=json.loads((J4J5/"summary.json").read_text(encoding="utf-8"))
 by={x["uid"]:x for x in j["all_frames"]}
 for f in ("26_1","26_2","26_3","26_4"):
  assert by[f]["J4_status"]=="J4_COMPLETE"
  assert by[f]["J4_done_tiles"]==1620
  assert by[f]["J5_status"]=="J5_COMPLETE"
  assert by[f]["J5_area_preserved"]
 assert by["26_3"]["J5_original_candidate_count"]==4741
 assert by["26_4"]["J5_original_candidate_count"]==5155
 assert (J4J5/"ALL20_J4J5_FULL_REPLAY_STAGE_LEDGER.csv").exists()

def test_frozen_original_SHA_and_all20_review_png_verified():
 s=json.loads((VAL/"FROZEN_ORIGINALS_POST20RAW_SHA256_QA.json").read_text(encoding="utf-8"))
 assert s["frozen_file_count"]==59
 assert s["all_frozen_files_same_bytes_and_hash"]
 p=VAL/"20_RAW_K8DE_PRIORITY_CONTOURS_5_SAMPLES_X_4_FRAMES.png"
 assert p.stat().st_size>100000
 img=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
 assert img is not None and img.shape[:2]==(2750,2720)
 assert (VAL/"TWENTY_RAW_K8DE_J4J5_COMPARISON.csv").exists()
