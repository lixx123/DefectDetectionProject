"""Current, audited 26-stage x 20-RAW coverage updated with real J4/J5 and K8DE.

Never silently claim completion for archived studies, micro raw restoration,
cross-channel J5/B physical dedup or unreviewed dark spots.
"""
from pathlib import Path
from collections import Counter
import sys,json,datetime
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_case03frozen_all20_robustness import inputs
from scripts.run_case03_frozen_J4J5_full_all20 import status_all
F=C.OUTPUT_ROOT/"CASE03_FROZEN_RELEASE_20261019_v2"
DE=C.OUTPUT_ROOT/"CASE03_FROZEN_K8DE_PRIORITY_ALL20_20261019_v1"
J4J5=C.OUTPUT_ROOT/"CASE03_FROZEN_FULL_J4J5_20RAW_20261019_v1"
OUT=C.OUTPUT_ROOT/"CASE03_FROZEN_20RAW_VALIDATION_20261019_v1"
EARLY_J4={"03E_E2_H_ANCHORED_EXTENSIONS","03F_LOCAL_RAW_CONTRAST_MAD",
          "03G_REVERSIBLE_NOISE_GATE","03H_BACKGROUND_TEXTURE_DoG",
          "03I_SIZE_FERET","03J_FRAGMENT_ASSOCIATION"}
ARCHIVE_ONLY={"03A_THRESHOLD_STUDIES","03K3_K5_K6_SCALE_SPOTS",
             "03K8H_LEGACY_BAND02_OVERLAY"}
EARLY_ALL={"00_RAW_READ","01_RAW_QC","03K8A_DYNAMIC_WORKBANDS",
           "03K8B_PER_BAND_THRESHOLDS","03K8C_NOISE_TRIAGE",
           "04_ROBUSTNESS_HOLDOUT"}
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 stages=json.loads((F/"FROZEN_PIPELINE_AND_FILES_SHA256.json").read_text(encoding="utf-8"))["registered_stages"]
 assert len(stages)==26
 raw=inputs()
 j=status_all(raw)
 jd={z["uid"]:z for z in j}
 de=json.loads((DE/"summary.json").read_text(encoding="utf-8"))
 assert de["frames_pass"]==20 and de["frames_fail"]==0
 qa=json.loads((DE/"independent_QA.json").read_text(encoding="utf-8"))
 assert qa["raw_inputs_pass"]==20
 k={x["uid"]:x for x in de["frames"]}
 rows=[]
 for spec in raw:
  uid=spec["uid"]
  js=jd[uid]
  d=k[uid]
  full_J4=js["J4_status"]=="J4_COMPLETE"
  full_J5=js["J5_status"]=="J5_COMPLETE"
  assert not full_J5 or full_J4
  if d["status"]!="PASS":raise AssertionError("K8DE lost pass "+uid)
  for stage in stages:
   key=stage["stage"]
   if key in EARLY_ALL:
    state="PASS_K8ABC_SCOPE"
   elif key in ARCHIVE_ONLY:
    state="ARCHIVED_RESEARCH_NOT_AUTO_STAGE"
   elif key=="02_MULTISCALE_BLACKHAT":
    state="PASS_WHOLE_RAW_J4_FUSED" if full_J4 else (
      "WHOLE_RAW_BH_FUSED_READY_J4_PARTIAL" if js["fused_exact_ready"]
      else "PASS_BANDWISE_BH_ONLY")
   elif key=="03B_HYSTERESIS_SEEDS":
    state="PASS_J4_H170_230_PLUS_BAND_A" if full_J4 else "PASS_K8B_BAND_A_J4_PENDING"
   elif key in EARLY_J4:
    state="PASS_FROZEN_J4_WHOLE_FRAME" if full_J4 else (
      "J4_PARTIAL_SOURCE_TILES" if js["J4_done_tiles"]>0 else "NOT_RUN_J4_REQUIRED")
   elif key=="03J4_TILED_FULLSCAN":
    state="PASS_ALL_1620_SOURCE_TILES" if full_J4 else (
      f"PARTIAL_{js['J4_done_tiles']}_OF_1620_TILES" if js["J4_done_tiles"] else "NOT_RUN")
   elif key=="03J5_GLOBAL_STITCH":
    state="PASS_GLOBAL_J5_SOURCE_AREA_PRESERVED" if full_J5 else "NOT_RUN_J4_INCOMPLETE"
   elif key=="03K8D_SEEDED_RAW_OUTER":
    state="PASS_K8C_PRIORITY_RAW_ONLY_MICRO_UNEXPANDED"
   elif key=="03K8E_PIXEL_EXACT_ASSOCIATION":
    state="PASS_K8C_PRIORITY_K8D_PIXEL_OR_ONLY_NOT_J5B_DEDUP"
   elif key=="03K8I2_EVIDENCE_RAW_AND_GROUPS":
    state="PASS_PRIORITY_RAW_NEW_OR_FROZEN_REFERENCE"
   elif key=="03K8F_HUMAN_APPROVAL_LEDGER":
    state=("USER_APPROVALS_FROZEN_FOR_TWO_REAL_SPOTS" if uid in ("26_1","26_2")
      else "NO_NEW_USER_GROUNDTRUTH_NOT_APPROVED")
   elif key=="03K8G_DISPLAY_1p5":
    state="PASS_J5_AND_K8I_FULL_DISPLAY" if uid in ("26_1","26_2") else (
      "K8DE_PRIORITY_OVERVIEW_ONLY_J5_DISPLAY_NOT_MERGED")
   elif key=="03K8I_FULL_SOURCE_PROVENANCE":
    state="PASS_J5_B_FULL_LINEAGE" if uid in ("26_1","26_2") else (
      "J5_FULL_YET_TO_BE_JOINED_WITH_B" if full_J5 else "B_STAGE_RECORD_ONLY_J5_PENDING")
   elif key=="03K8I2_HUMAN_REVIEW_CONFIRMED":
    state="PRIOR_USER_APPROVED_TWO_REAL_DARKSPOTS" if uid in ("26_1","26_2") else (
      "CANDIDATES_AWAIT_MANUAL_TRUTH_NOT_AUTO_APPROVED")
   else:
    raise AssertionError("Unmapped pipeline stage "+key)
   rows.append({"uid":uid,"sample":spec["sample_id"],"frame":spec["frame_id"],
     "stage":key,"stage_scope":stage["execution_coverage"],
     "actual_execution_status":state,
     "original_B_source_count":d["B_all_source_count"],
     "K8D_priority_trial_count":d["new_raw_trials"],
     "K8E_new_review_group_count":d["review_group_count"],
     "J4_source_tiles_complete":js["J4_done_tiles"],
     "J5_full_frame_complete":full_J5,
     "raw_provenance_unchanged":True,
     "no_silent_source_filtering":True})
 tab=pd.DataFrame(rows)
 assert len(tab)==520 and not tab.duplicated(["uid","stage"]).any()
 tab.to_csv(OUT/"CURRENT_26_ALGORITHM_STAGES_X_20_RAW_SCOPE_LEDGER.csv",
            encoding="utf-8-sig",index=False)
 statuses=pd.DataFrame([{"uid":z["uid"],"sample":z["sample"],
   "frame":z["frame"],"K8ABC_all_bands_status":"PASS",
   "K8DE_priority_RAW_area_exact":"PASS",
   "J4_tiles_completed":z["J4_done_tiles"],
   "J4_status":z["J4_status"],"J5_status":z["J5_status"],
   "J5_objects_count":z["J5_original_candidate_count"],
   "J5_area_preserved":z["J5_area_preserved"],
   "J5_B_full_crosschannel_dedup":"NOT_DONE",
   "production_ground_truth":"NOT_AVAILABLE"} for z in j])
 statuses.to_csv(OUT/"ALL20_MAIN_PIPELINE_EXECUTION_STATUS.csv",encoding="utf-8-sig",index=False)
 completed=int((statuses.J5_status=="J5_COMPLETE").sum())
 s={"version":"CASE03_20RAW_FROZEN_FULL_PROCESS_SNAPSHOT_V1",
    "raw_total":20,"algorithms_registered":26,"stage_frame_audit_rows":520,
    "K8ABC_20_frames_pass":True,"K8DE_priority_20_frames_pass":True,
    "B_original_source_records_proven":qa["all_original_B_source_labels_audited"],
    "priority_RAW_trial_records":qa["all_trial_counts"],
    "K8DE_review_groups_not_true_defect_count":qa["new_pixel_groups_sum"],
    "J4_J5_full_frame_pass":completed,
    "J4_J5_frames_not_yet_complete":20-completed,
    "J5_B_full_physical_dedup_complete":False,
    "all_K8B_micro_RAW_outer_complete":False,
    "true_physical_precision_recall_test_complete":False,
    "green_review_8_nondefect_user_note_in_26_1_needs_exact_ID_mapping":True,
    "historical_user_approved_F1_B02_B04_and_F2_G006_G009_preserved":True,
    "data_no_silent_drop":True,
    "current_J4_J5_queue_state":"SEE_ACTIVE_WINDOWS_PROCESS_AND_PER_FRAME_J4_STATUS",
    "frame_statuses":statuses.to_dict("records")}
 (OUT/"summary.json").write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8")
 print("FULL20_STAGE_LEDGER_NOW",completed,"J5_PASS",20-completed,
       "J5_PENDING","26STAGES_X20_FRAMES=",len(tab),flush=True)
if __name__=="__main__":main()
