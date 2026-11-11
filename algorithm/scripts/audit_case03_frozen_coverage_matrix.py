"""No-omission coverage matrix for all 26 stages across 20 RAW frames.

Explicitly separates standalone experiments from required production stages.
26_1/26_2 have archived J4/J5 full runs. Other frames have K8A/B/C
validation only; NEVER represent as 26-stage complete.
"""
from pathlib import Path
import json,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
RELEASE=C.OUTPUT_ROOT/"CASE03_FROZEN_RELEASE_20261019_v2"
ROBUST=C.OUTPUT_ROOT/"CASE03_FROZEN_ROBUSTNESS_20RAW_20261019_v3"
base=json.loads((RELEASE/"FROZEN_PIPELINE_AND_FILES_SHA256.json").read_text(encoding="utf-8"))
STAGES=base["registered_stages"]
ALL20={"00_RAW_READ","01_RAW_QC","03K8A_DYNAMIC_WORKBANDS",
       "03K8B_PER_BAND_THRESHOLDS","03K8C_NOISE_TRIAGE","04_ROBUSTNESS_HOLDOUT"}
TRIAL_ONLY={"03A_THRESHOLD_STUDIES","03K3_K5_K6_SCALE_SPOTS","03K8H_LEGACY_BAND02_OVERLAY"}
def main():
 raw=pd.read_csv(ROBUST/"INDEPENDENT_20_FRAME_PIXEL_SOURCE_AUDIT.csv")
 assert len(raw)==20
 table=[]
 for z in raw.itertuples(index=False):
  historic=(int(z.sample_id)==26 and int(z.frame_id) in (1,2))
  for order,stage in enumerate(STAGES,1):
   sid=stage["stage"]
   if sid in ALL20:
    state="PASS_ALL20_K8ABC_SCOPE"
   elif sid=="02_MULTISCALE_BLACKHAT":
    state="PASS_BANDRAW_UNMASKED_5KERNEL; HISTORICAL_FULL_J4" if historic else "PASS_BANDRAW_UNMASKED_5KERNEL_ONLY"
   elif sid=="03B_HYSTERESIS_SEEDS":
    state="PASS_FULL_J4_H_PLUS_BAND_A" if historic else "PASS_WORKBAND_A_H_ONLY_J4_PENDING"
   elif sid in TRIAL_ONLY:
    state="ARCHIVED_RESEARCH_NOT_AUTOMATIC"
   elif sid in ("03K8D_SEEDED_RAW_OUTER","03K8E_PIXEL_EXACT_ASSOCIATION",
                "03K8F_HUMAN_APPROVAL_LEDGER","03K8I2_EVIDENCE_RAW_AND_GROUPS"):
    state="PASS_PRIOR_SELECTED_OBJECTS_ONLY" if historic else "NOT_RUN_REQUIRED_FOR_COMPLETE_FULL_PIPELINE"
   elif sid=="03K8I2_HUMAN_REVIEW_CONFIRMED":
    state="TWO_PRIOR_USER_CONFIRMED_BAND_OBJECTS" if historic else "NO_USER_GROUNDTRUTH_AVAILABLE"
   elif sid in ("03K8I_FULL_SOURCE_PROVENANCE","03K8G_DISPLAY_1p5"):
    state="PASS_FULL_J5_AND_B_LAYERS" if historic else "NOT_RUN_FULL_J5_B_LINEAGE_AND_DISPLAY_PENDING"
   elif sid in ("03J4_TILED_FULLSCAN","03J5_GLOBAL_STITCH"):
    state="PASS_FROZEN_J4_J5_1620_TILES" if historic else "NOT_RUN_FULL_J4_J5_PER_FRAME"
   else:
    state="HISTORIC_26_FRAME1_2_METHOD_ONLY" if historic else "NOT_RUN_REQUIRED_FOR_COMPLETE_FULL_PIPELINE"
   table.append({"sample_id":int(z.sample_id),"frame_id":int(z.frame_id),
       "raw_uid":f"{int(z.sample_id)}_{int(z.frame_id)}",
       "stage_order":order,
       "stage":sid,"status":state,
       "stage_algorithm_policy":stage["policy_and_limit"],
       "not_hidden_from_pipeline":True,
       "not_a_claim_of_groundtruth_accuracy":True})
 expected=len(STAGES)*len(raw)
 assert len(table)==expected==520
 d=pd.DataFrame(table)
 assert not d.duplicated(["raw_uid","stage"]).any()
 output=RELEASE/"PIPELINE_26_STAGES_X_20RAW_EXECUTION_COVERAGE_v2.csv"
 if output.exists():raise FileExistsError(output)
 d.to_csv(output,index=False,encoding="utf-8-sig")
 pending=d[(d.status.str.startswith("NOT_RUN"))]
 assert len(pending)>0
 status={
  "stages_recorded":26,
  "raw_frames_recorded":20,
  "audit_stage_frame_rows":len(d),
  "source_stages_omitted":0,
  "all20_complete_J4_J5_K8D_E":False,
  "all20_K8A_B_C_reproduced":True,
  "historical_26_1_26_2_full_J4_J5_only":True,
  "still_pending_stage_frame_rows":len(pending),
  "not_run_coverage_by_stage":pending.groupby("stage").size().to_dict(),
  "all_remaining_modules_explicit_and_have_frozen_source_files":True,
  "no_automatic_promotion_of_candidate_to_defect_truth":True}
 (RELEASE/"PIPELINE_20RAW_NO_SILENT_STAGE_OMISSION_AUDIT_v2.json").write_text(
    json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")
 print("CASE03_PIPELINE_NO_STAGE_SILENTLY_OMITTED",json.dumps(
     {"stages":26,"raws":20,"rows":len(d),
      "pending_stage_frame_entries":len(pending)},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
