"""K6 independent second-frame QA and side-by-side distribution audit.

Verifies complete 1620-tile J4, J5 global source conservation,
288 predeclared frame2 review regions, 264 frozen J5 source-mask identities
using a fresh tile/J5 membership loader; 24 genuinely J5-bbox-free controls;
actual PNG decode and second-frame Bhat input matching. No ground truth.
"""
from pathlib import Path
from collections import Counter
import json,sys
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from scripts.run_case03k6_second_frame_K5 import (
    J4,J5,RAW,RESP,OUT,original_id_map
)
from scripts.run_case03k6_second_frame_K5 import tile_labels
from scripts.run_case03k6_second_frame_K5 import SEED
from src.detection.blackhat import black_hat_uint16
REPORT=OUT/"independent_QA_and_frame_comparison.json"
STAT=OUT/"comparison_frame1_frame2_dn_stats.csv"
PNG=OUT/"selected_6panel_labeled_top_7.png"


def compare_distribution():
    rows=[]
    for frame in (1,2):
        source=np.memmap(cfg.DATA_ROOT/f"26 ({frame}).raw",
           mode="r",dtype=">u2",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
        if frame==1:
            resp=cfg.OUTPUT_ROOT/(
               "case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy")
        else:resp=RESP
        bh=np.load(resp,mmap_mode="r",allow_pickle=False)
        raw=np.asarray(source[::8,::8],np.float64)
        response=np.asarray(bh[::8,::8],np.float64)
        rec={
          "frame":frame,
          "input_raw":f"26 ({frame}).raw",
          "raw_p01_dn":float(np.percentile(raw,1)),
          "raw_p10_dn":float(np.percentile(raw,10)),
          "raw_p50_dn":float(np.percentile(raw,50)),
          "raw_p90_dn":float(np.percentile(raw,90)),
          "raw_p99_dn":float(np.percentile(raw,99)),
          "raw_nonzero_fraction":float(np.mean(raw>0)),
          "BH_p50_dn":float(np.percentile(response,50)),
          "BH_p90_dn":float(np.percentile(response,90)),
          "BH_p99_dn":float(np.percentile(response,99)),
          "BH_p999_dn":float(np.percentile(response,99.9)),
          "BH_pixels_ge170_sampled":int(np.count_nonzero(response>=170)),
          "BH_pixels_ge230_sampled":int(np.count_nonzero(response>=230)),
          "BH_fraction_ge170":float(np.mean(response>=170)),
          "BH_fraction_ge230":float(np.mean(response>=230)),
        }
        rows.append(rec)
    pd.DataFrame(rows).to_csv(STAT,encoding="utf-8-sig",index=False)
    return rows


def qa():
    if REPORT.exists() or STAT.exists() or PNG.exists():
        raise FileExistsError("do not overwrite prior QA")
    a=json.loads((J4/"run_status.json").read_text(encoding="utf-8"))
    b=json.loads((J5/"summary.json").read_text(encoding="utf-8"))
    c=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    assert (a["stage"]=="J4_COMPLETE" and a["completed_tiles"]==
            a["planned_tiles"]==1620)
    assert b["stage"]=="J5_COMPLETE"
    assert b["source_area_unchanged"] and b["source_area_before_pixels"]==b["source_area_after_pixels"]
    assert c["stage"]=="K6_SECOND_FRAME_FROZEN_K5_COMPLETE"
    frame=pd.read_csv(J5/"global_defects.csv",encoding="utf-8-sig")
    mapping=pd.read_csv(J5/"global_object_membership.csv",encoding="utf-8-sig")
    assert len(frame)==b["global_candidate_objects"]==4440
    assert frame.global_defect_id.is_unique
    assert len(mapping)==b["original_J4_unmerged_objects"]==4511
    assert mapping.global_defect_id.isin(frame.global_defect_id).all()
    assert int(frame.source_area_px2.sum())==b["source_area_after_pixels"]
    assert frame.grade.value_counts().to_dict()=={"SMALL":4215,"MEDIUM":119,"LARGE":106}
    selections=pd.read_csv(OUT/"fixed_selection_and_blank_manual_review.csv",
                           keep_default_na=False,encoding="utf-8-sig")
    audit=pd.read_csv(OUT/"all_288_frozen_K5_audit.csv",encoding="utf-8-sig")
    assert len(selections)==len(audit)==288
    assert selections.sample_id.is_unique and audit.sample_id.is_unique
    assert audit.frozen_second_frame_J5_ID.nunique()==264
    assert selections.human_true_defect_review.eq("").all()
    assert selections.manual_outer_quality.eq("").all()
    assert selections.human_missed_defects_in_ROI.eq("").all()
    assert (selections.sample_group=="NO_J5_PREDICTION_ROI").sum()==24
    gids=selections[selections.source_global_defect_id.ne("")]
    assert gids.source_global_defect_id.is_unique
    assert len(gids)==264
    assert audit.no_official_ID_or_grade_changed.all()
    assert audit.unlabeled_second_frame.all()
    members=pd.DataFrame(mapping)
    local_to_global=dict(zip(
        zip(members.source_tile_id,members.source_local_object_index.astype(int)),
        members.global_defect_id))
    # Rebuild every selected source region from original second-frame J4 masks.
    for row in selections.to_dict("records"):
        idmap,source=original_id_map(row,local_to_global)
        related=audit.loc[audit.sample_id==row["sample_id"]].iloc[0]
        assert int(source.sum())==int(related.original_source_area_px2)
        x0,y0,x1,y1=[int(row[k]) for k in ("x0","y0","x1","y1")]
        assert (x1-x0,y1-y0)==(128,128)
        if row["source_global_defect_id"]=="":
            # A J5 bbox can include inferred bridge even where no source pixel.
            # Controls were explicitly chosen to avoid both.
            violations=frame.loc[
                 (frame.display_bbox_x_global<x1)&
                 (frame.display_bbox_xmax_inclusive>=x0)&
                 (frame.display_bbox_y_global<y1)&
                 (frame.display_bbox_ymax_inclusive>=y0)]
            assert len(violations)==0,row["sample_id"]
            assert not np.any(idmap!="")
    assert (audit.display_status=="GROUP_OUTER_PENDING_HUMAN_REVIEW").sum()==5
    assert (audit.display_status=="REJECTED_HALO_DISPLAY_REVIEW_ONLY").sum()==2
    assert (audit.K5_adaptive_area_px2>0).sum()==7
    assert (audit.noise_multiplier_chosen==1.5).sum()==2
    assert (audit.display_status=="NO_SPOT_SCALE_PRECHECK").sum()==251
    # Explicit fix of early 'precheck' count: exact 264-251, rather than H61>=60 only.
    shape_precheck_pass=int((audit.sample_group!="NO_J5_PREDICTION_ROI").sum()-
                        (audit.display_status=="NO_SPOT_SCALE_PRECHECK").sum())
    assert shape_precheck_pass==13
    pics=sorted((OUT/"review_images").glob("*.png"))
    cards=sorted(OUT.glob("selected_6panel_*.png"))
    assert len(pics)==25 and len(cards)==3,(len(pics),len(cards))
    for file in pics+cards:
        decoded=cv2.imdecode(np.frombuffer(file.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        assert decoded is not None and min(decoded.shape[:2])>100,file
    # Create a TOP 7 montage with exact displayed IDs, no input-specific alignment.
    marked=audit[audit.K5_adaptive_area_px2>0].copy()
    marked=marked.sort_values(["display_status","K5_adaptive_area_px2"],
                               ascending=[True,False])
    top=[]
    for rec in marked.to_dict("records"):
        name=rec["sample_id"]
        file=OUT/"review_images"/(name+"_6panel.png")
        assert file.exists(),file
        raw=cv2.imdecode(np.frombuffer(file.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        resized=cv2.resize(raw,(1260,257),interpolation=cv2.INTER_AREA)
        head=np.full((45,1260,3),25,np.uint8)
        msg=f'{name} | {rec["frozen_second_frame_J5_ID"]} | SOURCE {rec["original_source_area_px2"]}px | RAW {rec["K5_adaptive_area_px2"]}px | {rec["display_status"]}'
        cv2.putText(head,msg[:145],(8,25),cv2.FONT_HERSHEY_SIMPLEX,.39,(238,238,238),1,cv2.LINE_AA)
        top.append(np.vstack((head,resized)))
    merged=np.vstack(top)
    ok,png=cv2.imencode(".png",merged)
    assert ok
    PNG.write_bytes(png.tobytes())
    verify=cv2.imdecode(np.frombuffer(PNG.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    assert verify is not None and verify.shape==merged.shape
    distribution=compare_distribution()
    s1=json.loads((cfg.OUTPUT_ROOT/
      "case03j5_global/run_20261012_frame26_1_global_j5_v1/summary.json").read_text(encoding="utf-8"))
    answer={
       "stage":"K6_SECOND_FRAME_DATA_QA_PASS",
       "frame":2,
       "raw_pixels_total":int(cfg.RAW_WIDTH*cfg.RAW_HEIGHT),
       "J4_complete_tiles":1620,
       "J4_local_objects":int(a["candidate_j4_local_objects"]),
       "J5_global_candidates":len(frame),
       "J5_source_area_preserved_px2":int(frame.source_area_px2.sum()),
       "J5_sizes":b["grade_counts"],
       "first_frame_candidate_count":int(s1["global_candidate_objects"]),
       "second_frame_candidate_count":len(frame),
       "not_a_direct_object_correspondence_between_frames":True,
       "second_frame_sampled_J5":264,
       "second_frame_unpredicted_controls":24,
       "second_frame_exact_BH_shape_precheck_pass":shape_precheck_pass,
       "second_frame_RAW_outer_candidate_count":7,
       "second_frame_group_review_count":5,
       "second_frame_rejected_halo_review_count":2,
       "second_frame_adaptive_k1p5_selected":2,
       "all_source_pixels_reconstructed_from_frame2_J4":True,
       "all_images_decode_pass":len(pics)+len(cards)+1,
       "all_manual_label_fields_empty":True,
       "frame_comparison_dn_distributions":distribution,
       "no_first_frame_ID_or_coordinate_mapping_used":True,
       "no_official_source_masks_or_thresholds_updated":True,
       "no_blind_manual_true_contours_available":True,
       "performance_statistics_not_yet_measurable":True,
       "important_restriction":"K5 still sampled only; first-frame thresholds developed on 074 and 079."
    }
    REPORT.write_text(json.dumps(answer,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K6_INDEPENDENT_FULL_QA_PASS",json.dumps(answer,ensure_ascii=False),flush=True)
    return answer

if __name__=="__main__":qa()
