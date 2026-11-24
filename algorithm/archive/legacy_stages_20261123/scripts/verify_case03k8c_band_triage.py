"""Case03-K8-C independent source-preservation and reversible-score QA.

Rebuilds aggregate masks from saved PNG. All B pixels must be in EXACTLY
one review/strong/hide-suggestion archive; no source J5 pixels deleted.
No manual annotation is used to score; only frame2 12 spot confirmations
are retrospectively joined, with all nonhidden.
"""
from pathlib import Path
from collections import Counter
import sys,json
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
R=cfg.OUTPUT_ROOT/"case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2"
B=cfg.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"

def load(path):
    im=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if im is None:raise AssertionError("invalid PNG "+str(path))
    return im

def verify():
    summ=json.loads((R/"summary.json").read_text(encoding="utf-8"))
    assert summ["stage"]=="CASE03K8C_REVERSIBLE_PROPOSAL_TRIAGE"
    assert summ["source_J5_K5_not_edited"]
    assert summ["manual_dark_spot_reference_separate_from_scoring"]
    results=[]
    for frame in (1,2):
        folder=R/f"frame26_{frame}"
        stats=pd.read_csv(folder/"K8C_per_band_review_summary.csv",
                          encoding="utf-8-sig")
        objects=pd.read_csv(folder/"all_K8B_candidate_objects_complete_K8C_audit.csv",
                            encoding="utf-8-sig")
        outmeta=json.loads((folder/"summary.json").read_text(encoding="utf-8"))
        dashboard=json.loads((folder/"K8C_J5_work_and_supplement_dashboard.json").read_text(
                        encoding="utf-8"))
        assert outmeta["source_RAW"]==f"26 ({frame}).raw"
        assert outmeta["no_candidate_source_mask_pixels_ever_deleted"]
        assert outmeta["human_labels_not_used_in_candidate_gate"]
        assert stats.band_id.tolist()==[1,2,3,4]
        assert int(stats.K8B_B_candidate_objects.sum())==len(objects)
        assert int(objects.candidate_area_px2.sum())==int(stats.source_B_pixel_count.sum())
        assert objects.candidate_group_uid.is_unique
        assert objects.no_actual_candidate_pixels_deleted.all()
        assert objects.no_official_J5_area_or_ID_modified.all()
        assert objects.candidate_area_px2.min()>=1
        assert objects.is_independent_of_fixed_H.eq(
            objects.source_A_fixed_overlap_px.eq(0)).all()
        masks_checked=0
        image_checked=0
        for row in stats.itertuples(index=False):
            band=folder/f"band{int(row.band_id):02d}"
            original=B/f"frame26_{frame}"/f"band_{int(row.band_id):02d}_B_hysteresis_mask_cropped.png"
            fixed=B/f"frame26_{frame}"/f"band_{int(row.band_id):02d}_A_hysteresis_mask_cropped.png"
            b=load(original)>0;a=load(fixed)>0
            p=load(band/"K8C_promising_raw_supported_mask.png")>0
            r=load(band/"K8C_uncertain_or_fixedH_review_mask.png")>0
            m=load(band/"K8C_micro_suggest_hide_mask.png")>0
            assert p.shape==r.shape==m.shape==b.shape==a.shape
            assert not np.any((p&r)|(r&m)|(p&m))
            assert np.array_equal(p|r|m,b)
            assert np.all(r[a])
            assert int(p.sum())==row.promising_candidate_pixels
            assert int(r.sum())==row.review_candidate_pixels
            assert int(m.sum())==row.micro_hide_suggestion_pixels
            assert int(p.sum()+r.sum()+m.sum())==row.source_B_pixel_count
            group=objects[objects.band_id==row.band_id]
            assert len(group)==row.K8B_B_candidate_objects
            assert len(group[group.classification=="PROMISING_DARK_REVIEW"])==row.strong_dark_review_candidates
            assert len(group[group.classification=="MICRO_HIDE_SUGGESTION"])==row.micro_hide_suggestion_candidates
            assert len(group[group.classification=="EXISTING_FIXED_H"])==row.fixed_A_overlap_candidates
            assert (group.loc[group.classification=="MICRO_HIDE_SUGGESTION","candidate_area_px2"]<=2).all()
            assert (group.loc[group.classification=="PROMISING_DARK_REVIEW","candidate_area_px2"]>=8).all()
            assert (group.loc[group.classification=="EXISTING_FIXED_H","source_A_fixed_overlap_px"]>0).all()
            masks_checked+=3
            for image in band.glob("*.png"):
                if "mask" in image.name:continue
                x=cv2.imdecode(np.frombuffer(image.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
                assert x is not None and x.shape[0]>90 and x.shape[1]>500,image
                image_checked+=1
        assert dashboard["original_J5_work_center_objects"]==(683 if frame==1 else 398)
        assert dashboard["K8C_promising_supplemental_review_proposals"]==13
        assert dashboard["K8C_proposals_do_not_count_as_verified_true_defects"]
        for image in folder.glob("0?_*.png"):
            x=cv2.imdecode(np.frombuffer(image.read_bytes(),np.uint8),1)
            assert x is not None and x.shape[1]>1000
            image_checked+=1
        if frame==1:
            assert not (folder/"band02_user_reviewed_12_POSTHOC_only.csv").exists(),(
                "The user did not annotate first-frame top12")
        else:
            confirmed=pd.read_csv(folder/"band02_user_reviewed_12_POSTHOC_only.csv",
                    encoding="utf-8-sig")
            assert len(confirmed)==12
            assert confirmed.review_is_development_set_not_blind_validation.all()
            assert confirmed.classification.ne("MICRO_HIDE_SUGGESTION").all()
            assert all(confirmed.user_assessment_from_previous_turn==
                       "VISIBLE_DARK_SPOT_CANDIDATE")
        results.append({
          "frame":frame,
          "K8B_total_candidate_objects":len(objects),
          "A_fixed_source_components":int(stats.original_A_candidates.sum()),
          "new_B_unshared_component_count":int(stats.novel_B_unshared_with_A.sum()),
          "K8C_promising_review_count":int(stats.strong_dark_review_candidates.sum()),
          "micro_display_hide_suggestions":int(stats.micro_hide_suggestion_candidates.sum()),
          "all_3_binmask_pixels_conserved":True,
          "original_J5_work_center_total_unchanged":dashboard["original_J5_work_center_objects"],
          "full_band_binary_masks_checked":masks_checked,
          "PNG_preview_outputs_decoded":image_checked,
          "all_user_confirmed_12_frame2_nonhidden":(frame==2)
        })
    report={
       "stage":"CASE03_K8C_FULL_QA_PASS",
       "frames":[1,2],
       "user_confirmation_applies_only_to_second_frame_B2_top12":True,
       "no_masks_really_deleted":True,
       "no_full_new_J5_GH_pipeline_run":True,
       "no_true_precision_recall_claims":True,
       "comparison_valid_only_as_reversible_K8B_candidates":True,
       "results":results
    }
    fn=R/"independent_QA.json"
    if fn.exists():raise FileExistsError(fn)
    fn.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8C_INDEPENDENT_QA_PASS",json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":verify()
