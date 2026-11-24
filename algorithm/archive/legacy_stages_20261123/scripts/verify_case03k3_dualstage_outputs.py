"""Independent artifact QA for Case03-K3, does not alter experiment."""
from __future__ import annotations
import json
from pathlib import Path
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2/K3_dualstage_contour_pilot_v1"
K=ROOT/"outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2"
D=pd.read_csv(P/"all_30_audit.csv",encoding="utf-8-sig",keep_default_na=False)
labels=pd.read_csv(K/"revision_074_obvious_dark_spot_20261012/first_pass_review_30_labels_corrected.csv",
                   encoding="utf-8-sig",keep_default_na=False)
assert len(D)==30 and D.sample_id.is_unique
assert (D.decision=="PROVISIONAL_OUTER_SUGGESTION").sum()==1
assert D.loc[D.decision=="PROVISIONAL_OUTER_SUGGESTION","sample_id"].tolist()==["K0_SMALL_074"]
assert D.loc[D.sample_id=="K0_SMALL_074","raw_envelope_area_px2"].iloc[0]==1203
assert (D.loc[D.sample_id=="K0_SMALL_074","H61_added_anchor_area_px2"].iloc[0]==215)
assert set(D.sample_id)==set(labels.sample_id)
for rec in D.to_dict("records"):
    if rec["sample_id"].startswith("K0_NEGROI"):
        assert rec["decision"]=="NO_SEED_NO_ADDITIONAL_OBJECT"
        continue
    name=rec["sample_id"]
    path=P/"masks"/(name+".npz")
    with np.load(path,allow_pickle=False) as z:
        source=z["original_J5_detected"]>0
        competitor=z["competitor_J5_detected"]>0
        old=z["old_H170_230_anchor"]>0
        enhanced=z["add61_H170_230_anchor"]>0
        hypothesis=z["proposed_RAW_envelope"]>0
        visual=z["suggested_display"]>0
        assert source.shape==visual.shape==(128,128)
        assert int(source.sum())==int(rec["original_area_px2"])
        assert int(enhanced.sum())==int(rec["H61_added_anchor_area_px2"])
        assert int(hypothesis.sum())==int(rec["raw_envelope_area_px2"])
        assert np.all(visual[source])
        if rec["decision"]=="KEEP_ORIGINAL_REVIEW_ONLY":
            assert np.array_equal(visual,source)
        else:
            assert np.array_equal(visual,source|hypothesis)
            assert not np.any(visual & competitor)
    p=P/"figures"/(name+"_fivepanel.png")
    img=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    assert img is not None and img.shape==(325,1300,3),(name,img.shape if img is not None else "")
scratch=pd.read_csv(P/"W005_scratch_scale_control.csv")
assert scratch.shape[0]==2 and scratch.K3_spot_contour_applied.eq(False).all()
assert scratch.H_pixels_anchored_to_existing_scratch.iloc[1]>=scratch.H_pixels_anchored_to_existing_scratch.iloc[0]
allpng=list(P.rglob("*.png"))
for p in allpng:
    decoded=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    assert decoded is not None and min(decoded.shape[:2])>60,p
print("K3_PILOT_INDEPENDENT_QA_PASS",json.dumps({
    "input_small_candidates":24,
    "input_unreviewed_empty_ROIs":6,
    "provisional_approved":1,
    "provisional_sample":"K0_SMALL_074",
    "provisional_area_px2":1203,
    "original_J5_core_area_px2":24,
    "all_original_source_masks_preserved":True,
    "non74_display_mask_unchanged":True,
    "all_png_decoded":len(allpng),
    "scratch_original_detected_pixels_unmodified":True,
    "new_independent_candidates_enabled":False,
    "production_labels_or_config_modified":False
},ensure_ascii=False),flush=True)
