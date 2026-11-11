"""Frozen immutable review release of the complete historical Case03 pipeline.

Records ALL method stages, including experiments and not-yet-integrated stages,
without claiming unreviewed branch work was production approved. Distinguishes
mandatory step coverage, audit references and J5 full-frame processing.
No original source or historical output is changed.
"""
from pathlib import Path
from collections import Counter
from dataclasses import asdict
import sys,shutil,hashlib,json,datetime
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
BASE=cfg.OUTPUT_ROOT
OUT=BASE/"CASE03_FROZEN_RELEASE_20261019_v2"
I=BASE/"case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1"
II=BASE/"case03k8i_stage2_RAW_review_and_association/run_20261017_twoframes_priority_evidence_v1"
UI=BASE/"case03k8i_stage2_user_confirmed_reviews/run_20261017_F1_B02_B04_two_darkspots_v1"
F=BASE/"case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2"
K8A=BASE/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"
K8B=BASE/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
K8C=BASE/"case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2"
# Every historical method remains in the frozen workflow map, even when
# not promoted to production or not implemented for 18 unseen frames.
PIPELINE=[
 ("00_RAW_READ","src/io/raw_reader.py","ALL_20","big endian >u2, 12-bit valid DN, no preview geometry measurements"),
 ("01_RAW_QC","src/qc/image_statistics.py;src/qc/profile_analysis.py","ALL_20","shape/file bytes, intensity/hist/profile, exposure checks"),
 ("02_MULTISCALE_BLACKHAT","src/detection/blackhat.py;src/detection/multiscale.py","REPLAY_26_1_2","3,5,9,15,31 elliptical kernels, DN pixelwise max BEFORE band core mask"),
 ("03A_THRESHOLD_STUDIES","scripts/run_case03a_revision.py","RESEARCH_ARCHIVED","global fixed DN/local MAD comparison, research only not silently primary"),
 ("03B_HYSTERESIS_SEEDS","src/detection/case03t_adaptive_hysteresis.py","REPLAY_26_1_2","H170/230 connected threshold, source mask bitexact"),
 ("03E_E2_H_ANCHORED_EXTENSIONS","src/detection/case03e2_bounded_rescue.py;src/detection/case03e2_hseeded.py;src/detection/case03e2_multicandidate.py","J4_26_1_2","Gaussian smoothing/closing bounded to H-seeded structure; never free-seed blanket Gaussian morphology"),
 ("03F_LOCAL_RAW_CONTRAST_MAD","scripts/run_case03f_localcontrast_trial.py","J4_26_1_2","candidate/local RAW median annulus MAD significance, no blind noise deletion"),
 ("03G_REVERSIBLE_NOISE_GATE","src/detection/case03g_joint_gate.py","J4_26_1_2","support protection near H or Gaussian/Closing refinements"),
 ("03H_BACKGROUND_TEXTURE_DoG","src/detection/case03h_background_texture.py","J4_26_1_2","DoG, contrast, MAD, streak protections; suggest-hide only"),
 ("03I_SIZE_FERET","src/detection/case03i_size_grade.py","REPLAY_26_1_2","source area and longest Feret; 3.2um only detector image-plane equivalent"),
 ("03J_FRAGMENT_ASSOCIATION","src/detection/case03j_fragment_association.py;src/detection/case03j_continuous_contour.py","J4_26_1_2","raw-confirmed directional scratch continuity, avoid accidental bridge"),
 ("03J4_TILED_FULLSCAN","scripts/run_case03j4_fullscan.py","J4_26_1_2","full frame 1620 source tiles: original H seeds, refine, local candidate audits"),
 ("03J5_GLOBAL_STITCH","scripts/run_case03j5_global_merge.py;src/detection/case03j5_seam_match.py","J5_26_1_2","cross-tile 8-neighbor and constrained gap review; area source excludes inferred bridge pixels"),
 ("03K3_K5_K6_SCALE_SPOTS","src/detection/case03k3_spot_contour_pilot.py;src/detection/case03k5_adaptive_grouping.py","ARCHIVED_RESEARCH","61px large BH H-seeded/RAW outer/stability/groups in archive, do not replace J5"),
 ("03K8A_DYNAMIC_WORKBANDS","src/detection/case03k8a_band_locator.py","REPLAY_26_1_2","unknown 4/5 band count from frame, SHIELD/NONWORK/EDGE/WORK CORE; no hard-coded geometry"),
 ("03K8B_PER_BAND_THRESHOLDS","src/detection/case03k8b_perband_trial.py","REPLAY_26_1_2","fixed A H170/230, adaptive B robust z from strongest band, preserve both"),
 ("03K8C_NOISE_TRIAGE","src/detection/case03k8c_noise_review.py","REPLAY_26_1_2","local RAW contrast,MAD,DoG,2px micro suggestions, uncertain and edge review, no deletions"),
 ("03K8D_SEEDED_RAW_OUTER","src/detection/case03k8d_group_stability.py;src/detection/case03k3_spot_contour_pilot.py","PRIORITY_26_1_2","3/2/1.5MAD cautious stability and workband core, no unsupported expansion"),
 ("03K8E_PIXEL_EXACT_ASSOCIATION","src/detection/case03k8e_group_hypothesis.py","PRIORITY_26_1_2","pixel-level IoU/containment and true OR union; source labels retained"),
 ("03K8F_HUMAN_APPROVAL_LEDGER","scripts/run_case03k8f_approved_supplements_ledger.py","PRIORITY_26_1_2","only user confirmed group approval, preserve original J5 IDs"),
 ("03K8G_DISPLAY_1p5","src/detection/case03k8g_display_boxes.py","PRIORITY_26_1_2","1.5x display bounding rectangles and 1-display-pixel outline, A/L from source mask"),
 ("03K8H_LEGACY_BAND02_OVERLAY","scripts/run_case03k8h_f1_B02_review_reinstatement.py","MANUAL_ARCHIVE_NOT_AUTO","legacy hotfix for missing F1 B2 review groups; replaced by lossless K8I routing"),
 ("03K8I_FULL_SOURCE_PROVENANCE","src/detection/case03k8i_lineage_rules.py;tools/scripts/run_case03k8i_full_frame_lineage.py","J5_AND_B_26_1_2","all J5 + all B source IDs, explicit per-candidate visibility, pending/micro/fixed preserved"),
 ("03K8I2_EVIDENCE_RAW_AND_GROUPS","scripts/run_case03k8i_stage2_fullband_priority_contours.py","PRIORITY_26_1_2","136 new prioritized RAW outer 20,658 B source routing; archive all"),
 ("03K8I2_HUMAN_REVIEW_CONFIRMED","scripts/run_case03k8i_stage2_commit_user_confirmation.py","APPROVED_4_SPOTS_26_1_2","frame2 G006/G009 and frame1 B02,B04 unique exact-geometry review, other groups pending"),
 ("04_ROBUSTNESS_HOLDOUT","scripts/run_case03frozen_all20_robustness.py","20_RAW_K8A_B_C_PASS_J4_J5_18_NOT_RUN","all 20 raw files, dynamic work bands, perband candidates, counts and abnormalities"),
]
def hashfile(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  while 1:
   chunk=f.read(8*1024*1024)
   if not chunk:break
   h.update(chunk)
 return h.hexdigest()
def copy(source,dir,name=None):
 if not source.is_file():raise FileNotFoundError("RELEASE_SOURCE_MISSING "+str(source))
 target=dir/(name or source.name)
 target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():raise FileExistsError(target)
 shutil.copy2(source,target)
 if source.stat().st_size!=target.stat().st_size or hashfile(source)!=hashfile(target):
  raise AssertionError("file copy bit corruption")
 return {"release_path":str(target.relative_to(OUT)),"source_path":str(source),
         "bytes":target.stat().st_size,"sha256":hashfile(target)}
def main():
 if OUT.exists():raise FileExistsError("NO RELEASE OVERWRITE "+str(OUT))
 OUT.mkdir(parents=True)
 records=[]
 for f in (1,2):
  dest=OUT/f"26_{f}"
  dest.mkdir()
  base=I/f"frame26_{f}"
  src=II/f"frame26_{f}"
  required=[
   (base,"01_MAIN_J5_plus_confirmed_plus_unapproved_MEDLARGE_1to4.png", "01_FULLFRAME_MEDLARGE_PLUS_PENDING.png"),
   (base,"02_ALL_K8E_PENDING_AND_CONFLICT_GROUPS_1to4.png","02_K8E_ALL_GROUP_REVIEW.png"),
   (base,"03_ALL_SMALL_J5_AND_NOVEL_B_1to4.png","03_SMALL_AND_NOVEL.png"),
   (base,"04_K8C_MICRO_SUGGEST_HIDE_NOT_DELETED_1to4.png","04_ALL_MICRO_SUGGEST_HIDE_NOT_DELETED.png"),
   (base,"05_K8B_FIXED_H_OVERLAP_REFERENCE_1to8.png","05_FIXED_H_B_REFERENCE.png"),
   (base,"06_J5_OUTSIDE_WORK_REVIEW_REFERENCE_1to8.png","06_J5_NONWORK_SOURCE_REFERENCE.png"),
   (base,"07_ALL_K8B_B_SOURCE_PIXELS_reference_1to8.png","07_ALL_B_SOURCE_PIXELS.png"),
   (src,"01_STAGE2_NEW_RAW_GROUPS_REVIEW_plus_original_K8I_main.png","08_FULLFRAME_WITH_STAGE2_ALL_NEW_RAW_GROUPS.png"),
   (src,"02_NEW_RAW_GROUPS_ALL_review_1to4.png","09_STAGE2_ALL_RAW_GROUPS_REVIEW.png"),
   (src,"03_ONLY_NEW_STABLE_RAW_GROUPS_review_1to4.png","10_ONLY_STABLE_RAW_GROUPS_PENDING.png"),
   (src,"04_OLD_RAW_or_J5_bbox_OVERLAP_review_1to4.png","11_OLD_K8D_OR_J5_OVERLAP_REVIEW.png"),
   (base,"end_to_end_candidate_lineage.csv","SOURCE_ALL_J5_B_LINEAGE.csv"),
   (base,"K8E_review_group_register_all.csv","SOURCE_K8E_GROUPS.csv"),
   (base,"render_visibility_reconciliation.json","SOURCE_VISIBILITY_AUDIT.json"),
   (src,"ALL_B_STAGE2_processing_disposition.csv","STAGE2_ALL_B_DISPOSITION.csv"),
   (src,"new_evidence_RAW_trial_results.csv","STAGE2_RAW_TRIALS.csv"),
   (src,"new_exact_group_union_review.csv","STAGE2_RAW_EXACT_GROUPS.csv"),
   (src,"new_group_J5_bbox_and_old_K8D_collision_review.csv","STAGE2_RAW_OLD_COLLISION_AUDIT.csv"),
   (src,"ALL_FROZEN_AND_NEW_RAW_REVIEW_GROUPS_no_ID_merge.csv","ALL_FROZEN_AND_NEW_RAW_GROUPS.csv"),
   (K8A/f"frame26_{f}","work_band_overlay_on_RAW.png","12_BAND_GEOMETRY_WORK_SHIELD.png"),
   (K8B/f"frame26_{f}","perband_comparison_and_thresholds.csv","PARAMS_BAND_THRESHOLDS.csv"),
   (K8C/f"frame26_{f}","all_K8B_candidate_objects_complete_K8C_audit.csv","K8C_ALL_SOURCE_REVIEW.csv")]
  for folder,name,rename in required:records.append(copy(folder/name,dest,rename))
 if not (UI/"two_user_confirmed_darkspots_no_duplicate_area.csv").is_file():
  raise AssertionError("F1 human confirmation not found")
 for filename in ["two_user_confirmed_darkspots_no_duplicate_area.csv",
                  "five_B_source_components_to_two_user_confirmed_darkspots.csv",
                  "01_FRAME1_2_CONFIRMED_plus_frozen_J5_MEDLARGE.png",
                  "02_ONLY_B02_B04_two_confirmed_darkspots.png",
                  "03_Band04_verified_source_image_UNCHANGED.png",
                  "04_Band02_verified_source_image_UNCHANGED.png",
                  "independent_QA.json"]:
  records.append(copy(UI/filename,OUT/"26_1"/"USER_CONFIRMED"))
 for filename in ["workband_unified_candidate_review_register.csv",
                  "other_K8E_groups_pending_manual_review.csv"]:
  records.append(copy(F/"frame26_2"/filename,OUT/"26_2"/"PRIOR_2_USER_APPROVED"))
 # Existing frozen per-candidate data are references only: copy masks only for
 # user-confirmed objects, and link back to all historical source snapshots.
 for p in sorted((UI/"confirmed_mask_reviewonly").glob("*.npz")):
  records.append(copy(p,OUT/"26_1"/"USER_CONFIRMED"/"MASKS"))
 steps=[]
 for stage,sources,status,policy in PIPELINE:
  cited=[]
  for pathstr in sources.split(";"):
   pathstr=pathstr.replace("tools/scripts/","scripts/")
   pp=ROOT/pathstr
   cited.append({"file":pathstr,"exists":pp.exists(),
                 "sha256":hashfile(pp) if pp.is_file() else None})
  steps.append({"stage":stage,"source_files":cited,"execution_coverage":status,
                "policy_and_limit":policy,"guard":"DO_NOT_SILENTLY_OMIT"})
 assert all(all(x["exists"] for x in z["source_files"]) for z in steps
            if z["stage"]!="04_ROBUSTNESS_HOLDOUT"),"Missing freeze stage module"
 pd.DataFrame([{"stage":z["stage"],"execution_coverage":z["execution_coverage"],
                "policy_and_limit":z["policy_and_limit"],
                "source_files":';'.join(s["file"] for s in z["source_files"])}
                 for z in steps]).to_csv(OUT/"COMPLETE_PIPELINE_STAGE_REGISTRY.csv",
                                         encoding="utf-8-sig",index=False)
 src_confirm=pd.read_csv(UI/"two_user_confirmed_darkspots_no_duplicate_area.csv")
 assert len(src_confirm)==2
 state={"version":"CASE03_FROZEN_20261019_v2",
        "change_management":"Frozen J5/H fixed branch + K8A-I experimental branch; do not change algorithms or source IDs",
        "registered_stages":steps,"all_stages_included_even_research_only":True,
        "human_confirmed_review_count_F1":2,
        "human_confirmed_review_count_F2":2,
        "no_user_accepted_noise_groundtruth_beyond_last_review":True,
        "F1_8_green_proposal_nondefect_user_feedback_status":"USER_FEEDBACK_NEGATIVE_8_STABLE_DISPLAY_BOXES_ONLY; NOT_YET_MAPPED_TO_UNIQUE_SOURCE_GROUP_UIDs; KEEP_PENDING_MAPPING",
        "worklist_for_all20":"The J4/J5 G/H/global stitching work branch must be run on each new frame to call it equivalent full pipeline. Full 20-frame K8A/B/C/RAW experimental screening is not a substitute.",
        "immutable_exports":records}
 (OUT/"FROZEN_PIPELINE_AND_FILES_SHA256.json").write_text(
     json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
 print("FROZEN_RELEASE_COMPLETE",len(steps),"STAGES",len(records),
       "VERIFIED_FILE_COPIES",OUT,flush=True)
if __name__=="__main__":main()
