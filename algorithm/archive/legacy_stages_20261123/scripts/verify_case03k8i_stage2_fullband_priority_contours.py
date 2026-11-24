"""Independent stage-2 exact mask, class coverage and association QA.

Never accepts prior E groups automatically, and every K8B source must have
exactly one disposition. Group union is reconstructed from original RAW
candidate local pixel masks using global coordinates.
"""
from pathlib import Path
import sys,json,hashlib,math
from collections import Counter
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8e_group_hypothesis import make_groups,union_global
from scripts.run_case03k8i_stage2_fullband_priority_contours import (
    OUT,K8I,K8B,K8D,K8E,PRIOR,ENABLED_CLASSES,read_prior_mask)
def image(p):
    v=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if v is None:raise AssertionError("Image cannot decode "+str(p))
    return v

def qa_frame(f):
    base=OUT/f"frame26_{f}"
    lineage=pd.read_csv(K8I/f"frame26_{f}"/"end_to_end_candidate_lineage.csv",
                         encoding="utf-8-sig",low_memory=False,dtype={"source_local_id":"string"})
    b=lineage[lineage.stage=="K8B"].copy()
    dec=pd.read_csv(base/"ALL_B_STAGE2_processing_disposition.csv",
                   encoding="utf-8-sig")
    new=pd.read_csv(base/"new_evidence_RAW_trial_results.csv",
                   encoding="utf-8-sig")
    groups=pd.read_csv(base/"new_exact_group_union_review.csv",encoding="utf-8-sig")
    assert len(dec)==len(b)==(16766 if f==1 else 3892)
    assert not dec.duplicated(["band_id","B_label"]).any()
    assert dec.candidate_source_preserved.eq(True).all()
    assert not dec.human_confirmed_by_this_run.any()
    assert not dec.production_count_changed.any()
    source={(int(z.band_id),int(z.source_local_id)):z for z in b.itertuples()}
    assert set(zip(dec.band_id.astype(int),dec.B_label.astype(int)))==set(source)
    for row in dec.itertuples(index=False):
        key=(int(row.band_id),int(row.B_label))
        src=source[key]
        assert row.source_UID==src.candidate_source_uid
        assert row.source_area_px2==src.source_area_px2
        assert row.K8C_classification==src.K8C_noise_review_classification
        if row.stage2_tier=="NEW_RAW_EVIDENCE_REVIEW":
            assert row.K8C_classification in ENABLED_CLASSES
        if row.K8C_classification=="MICRO_HIDE_SUGGESTION":
            assert row.stage2_tier=="MICRO_SUGGEST_HIDE_SOURCE_RETAINED_NO_NEW_RAW"
    assert len(new)==int(dec.stage2_tier.eq("NEW_RAW_EVIDENCE_REVIEW").sum())==(
        131 if f==1 else 5)
    assert len(groups)==(129 if f==1 else 5)
    assert len(new)==len(set(zip(new.band_id,new.B_label)))
    assert new.source_mask_exact.all() and new.candidate_source_preserved.all()
    bmeta=json.loads((K8B/f"frame26_{f}"/"summary.json").read_text(encoding="utf-8"))
    roi_y={int(x["band_id"]):int(x["ROI_global_xyxy"][1]) for x in bmeta["ROI_crops"]}
    items=[]
    for band in sorted(new.band_id.unique()):
        source_mask=image(K8B/f"frame26_{f}"/f"band_{band:02d}_B_hysteresis_mask_cropped.png")
        n,labels,stats,centers=cv2.connectedComponentsWithStats(np.uint8(source_mask>0),8)
        for row in new[new.band_id==band].itertuples(index=False):
            label=int(row.B_label)
            file=base/f"band{band:02d}"/f"F{f}_B{band}_C{label:05d}_full_RAW_trial.npz"
            assert file.exists() and row.new_NPZ==str(file)
            with np.load(file,allow_pickle=False) as z:
                seed=z["original_B_source"].astype(bool)
                raw3=z["raw_k3"].astype(bool)
                raw2=z["raw_k2"].astype(bool)
                raw15=z["raw_k1p5"].astype(bool)
                outer=z["new_full_RAW_review_outer"].astype(bool)
                core=z["K8A_band_CORE"].astype(bool)
                lb=z["original_B_label_grid"].astype(np.int32)
                x0,y0,x1,y1=map(int,z["RAW_roi_global_xyxy"])
            assert seed.shape==outer.shape==(128,128)
            ybase=roi_y[band]
            overlay=np.zeros((128,128),np.int32)
            amin=max(ybase,y0);amax=min(ybase+labels.shape[0],y1)
            if amin<amax:
                overlay[amin-y0:amax-y0,:]=labels[amin-ybase:amax-ybase,x0:x1]
            assert np.array_equal(overlay,lb)
            assert np.array_equal(seed,lb==label)
            assert int(seed.sum())==int(stats[label,cv2.CC_STAT_AREA])==row.source_area_px2
            assert int(raw3.sum())==row.k3_area_px2
            assert int(raw2.sum())==row.k2_area_px2
            assert int(raw15.sum())==row.k1p5_area_px2
            assert int(outer.sum())==row.K8D_trial_outer_area_px2
            assert np.array_equal(seed|outer,outer)
            if row.stage2_review_status.startswith("STABLE_"):
                assert not np.any(outer&~core)
            if row.stage2_review_status=="SOURCE_ONLY_UNRELIABLE_3MAD":
                assert np.array_equal(outer,seed)
            # QA does not promote stable to production; unresolved stays
            # full review even if outer violates band core.
            items.append({"band_id":int(band),"label":label,
                          "box":(x0,y0,x1,y1),"mask":outer,
                          "status":row.stage2_review_status,
                          "partial_competitors":(
                              [int(z) for z in str(row.partial_other_B_competitors).split(";")
                               if z and z!="nan"]),
                          "embedded_evidence":[]})
    # Since same-group membership can depend on embedded evidence but
    # connectivity of source outer masks cannot, regenerate exact groups.
    groups2=make_groups(items)
    assert len(groups2)==len(groups)
    groupkeys={}
    for row in groups.itertuples(index=False):
        key=(int(row.band_id),
             tuple(sorted(map(int,str(row.new_source_B_labels).split(";")))))
        assert key not in groupkeys
        groupkeys[key]=row
    assert len(groupkeys)==len(groups2)
    for group in groups2:
        key=(group["band_id"],tuple(sorted(group["selected_candidate_labels"])))
        assert key in groupkeys
        saved=groupkeys[key]
        assert group["exact_group_union_px2"]==saved.new_exact_union_area_px2
        assert group["original_K8D_masks_sum_px2"]==saved.new_RAW_source_areas_sum_px2
        assert group["deduplicated_pixels"]==saved.new_internal_duplicate_pixels_removed
        with np.load(saved.npz_file,allow_pickle=False) as z:
            assert np.array_equal(z["exact_review_union"].astype(bool),group["mask"])
            assert tuple(map(int,z["RAW_global_bbox"]))==group["box"]
            assert set(map(int,z["raw_outer_source_B_labels"]))==set(key[1])
        assert not saved.is_user_confirmed
        assert saved.no_old_K8E_group_ID_merged and saved.original_sources_unchanged
    existing=pd.read_csv(K8E/f"frame26_{f}"/"K8E_unique_group_union_measurements.csv")
    assert set(existing.group_id)==set(pd.read_csv(
           K8I/f"frame26_{f}"/"K8E_review_group_register_all.csv").group_id)
    for gid,expected in ({"K8E_F2_B2_G006":348,"K8E_F2_B2_G009":370}.items() if f==2 else []):
        assert int(existing.set_index("group_id").loc[gid,"unique_outer_union_px2"])==expected
        with np.load(K8E/f"frame26_2"/"group_detail"/(
            gid+"_EXACT_GROUP_MASK.npz"),allow_pickle=False) as z:
            assert int(z["review_outer"].sum())==expected
    overlay=image(base/"01_STAGE2_NEW_RAW_GROUPS_REVIEW_plus_original_K8I_main.png")
    assert overlay.shape==(2388,2819,3)
    summary=json.loads((base/"summary.json").read_text(encoding="utf-8"))
    assert summary["new_exact_RAW_trials"]==len(new)
    assert summary["source_B_total"]==len(dec)
    assert summary["source_objects_omitted"]==0
    assert summary["approved_groups_changed"]==0
    assert summary["user_approval_automatically_assigned"]==0
    assert summary["new_group_review_count"]==len(groups)
    report={"frame":f,"total_B_dispositions":len(dec),"new_K8D_source_trials":len(new),
        "exact_group_review_masks":len(groups),
        "new_group_overlap_with_old_K8D_count":int(
           groups.old_K8D_B_mask_overlap_json.ne("[]").sum()),
        "source_masks_pixel_exact":True,"all_new_group_or_masks_pixel_exact":True,
        "old_approved_E_objects_unchanged":True,
        "new_auto_confirmed_physical_defects":0,
        "status_counts":dict(Counter(new.stage2_review_status))}
    print("STAGE2_FRAME_INDEPENDENT_PIXEL_QA_PASS",json.dumps(report,ensure_ascii=False),flush=True)
    return report

def main():
    r=[qa_frame(f) for f in (1,2)]
    output={"stage":"CASE03_K8I_STAGE2_INDEPENDENT_SOURCE_AND_PIXEL_QA_PASS",
            "frames":r,
            "all_20658_K8B_source_B_labels_have_stage2_disposition":True,
            "source_J5_B_K8D_E_I1_not_modified":True,
            "no_unapproved_object_merge_or_production_approval":True}
    path=OUT/"independent_QA.json"
    if path.exists():raise FileExistsError(path)
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print("CASE03_K8I_STAGE2_INDEPENDENT_SOURCE_AND_PIXEL_QA_PASS",flush=True)
if __name__=="__main__":main()
