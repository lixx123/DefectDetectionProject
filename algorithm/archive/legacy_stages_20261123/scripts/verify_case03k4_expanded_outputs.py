"""Read-only QA for K4 expanded 60 controls and K4S 240 discovery; prioritize review.

Checks mask/area provenance, validation without human ground truth, and
all newly created images. Outputs a blank manual priority sheet once.
"""
from pathlib import Path
import numpy as np,cv2,json,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
J4=ROOT/"outputs/case03j4_fullframe/run_20261012_frame26_1_full_j4_v1"
J5=ROOT/"outputs/case03j5_global/run_20261012_frame26_1_global_j5_v1"
K4=ROOT/"outputs/case03k_expanded_validation/run_20261012_new_J5_objects_K3_frozen_v1"
K4S=ROOT/"outputs/case03k_expanded_validation/run_20261012_240_green_scale_sensitivity_v1"

def qa():
    src=pd.read_csv(J5/"global_defects.csv")
    byid=src.set_index("global_defect_id")
    rows=pd.read_csv(K4/"manual_review_template.csv",keep_default_na=False)
    audit=pd.read_csv(K4/"all_60_audit.csv",keep_default_na=False)
    assert len(rows)==len(audit)==60 and rows.sample_id.is_unique
    assert rows.review_is_true_defect.eq("").all()
    assert set(rows.sample_id)==set(audit.sample_id)
    assert (rows.sample_group=="MEDIUM").sum()==12
    assert (rows.sample_group=="LARGE").sum()==12
    assert rows.sample_group.str.startswith("UNREVIEWED_SMALL").sum()==24
    assert (rows.sample_group=="NO_PREDICTION_CONTROL").sum()==12
    assert (audit.suggestion=="PROVISIONAL_OUTER_SUGGESTION").sum()==0
    for s in rows.to_dict("records"):
        sid=s["sample_id"]
        p=K4/"figures"/(sid+"_5panel.png")
        im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),1)
        assert im is not None and im.shape==(313,1300,3),(sid,im.shape if im is not None else None)
        if s["global_defect_id"]:
            assert s["global_defect_id"] in byid.index
            mask=K4/"masks"/(sid+".npz")
            with np.load(mask,allow_pickle=False) as z:
                source=z["original_source"].astype(bool)
                inferred=z["provisional_raw_outer"].astype(bool)
                display=z["suggested_display"].astype(bool)
                assert source.shape==inferred.shape==display.shape==(128,128)
                assert int(source.sum())==int(s["source_area_px2"])
                assert np.array_equal(source,display)
                assert int(source.sum())==int(byid.loc[s["global_defect_id"],"source_area_px2"])
    marks=sorted(K4.glob("contact_*.png"))
    assert len(marks)==5
    for p in marks:
        assert cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),1) is not None
    s=pd.read_csv(K4S/"fixed_unlabeled_selection.csv")
    x=pd.read_csv(K4S/"240_scale_trial_audit.csv")
    assert len(s)==len(x)==240 and s.global_defect_id.is_unique
    assert set(s.global_defect_id)==set(x.global_defect_id)
    assert s.stratum.value_counts().to_dict()=={"A1":24,"B2to3":24,"C4to7":72,"D8plus":120}
    assert x.shape_size_precheck_pass.sum()==22
    assert x.accepted_provisional.sum()==1
    assert x.loc[x.accepted_provisional,"sample_id"].tolist()==["K4S_079"]
    t=x.loc[x.accepted_provisional].iloc[0]
    assert int(t.source_area_px2)==7 and int(t.H61_anchor_area)==127 and int(t.RAW_envelope_trial_area)==179
    k4_known=set(rows.loc[rows.global_defect_id.ne(""),"global_defect_id"])
    assert not set(x.global_defect_id)&k4_known
    review_images=sorted((K4S/"review_figures").glob("*_5panel.png"))
    assert len(review_images)==18
    for p in review_images+sorted(K4S.glob("top_unlabeled_*.png")):
        im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),1)
        assert im is not None and min(im.shape[:2])>50,p
    # The review 18 are the only entries that have a review image.
    sample_ids={p.stem.replace("_unlabeled_5panel","") for p in review_images}
    ids=x[x.sample_id.isin(sample_ids)].copy()
    assert len(ids)==18 and ids.shape_size_precheck_pass.all()
    manual=ids[["sample_id","global_defect_id","source_area_px2","H61_anchor_area",
                "RAW_envelope_trial_area","accepted_provisional",
                "decision","veto","x0","y0","x1","y1"]].copy()
    manual["manual_true_dark_spot"]=""
    manual["manual_is_undersized"]=""
    manual["manual_outer_contour_quality"]=""
    manual["manual_overmerged_neighbor"]=""
    manual["manual_comments"]=""
    out=K4S/"priority_18_manual_review_blank.csv"
    if out.exists():raise FileExistsError(out)
    manual.to_csv(out,index=False,encoding="utf-8-sig")
    d={
      "stage":"K4_K4S_DATA_QA_PASS",
      "new_J5_candidate_tests":48,
      "new_no_J5_prediction_ROIs":12,
      "new_source_proposals":0,
      "fully_guaranteed_source_pixels_retained":True,
      "first60_PNG_verified":60+len(marks),
      "green_scale_screened":240,
      "scale_eligible":22,
      "provisional_outer_suggestions":1,
      "suggested_sample":"K4S_079",
      "review_images_for_human":18,
      "review_csv":str(out),
      "new_human_labels":0,
      "frozen_J5_unchanged":True,
      "validated_independent_second_frame":False,
      "confirmed_physical_outer_contours":0
    }
    print("K4_ALL_QA_PASS",json.dumps(d,ensure_ascii=False),flush=True)
    return d
if __name__=="__main__":qa()
