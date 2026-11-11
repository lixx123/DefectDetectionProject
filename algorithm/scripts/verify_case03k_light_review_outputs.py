"""Read-only acceptance of split J5 displays and K0 review sampling.

Checks disjoint/exhaustive CSVs, sample IDs and full-source lineage,
bounds of native 128px crops, actual absence of detected bbox in every
"unpredicted ROI", unfilled manual labels, counts and decoded PNGs.
"""
from __future__ import annotations
import json
from pathlib import Path
import cv2,numpy as np,pandas as pd

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"outputs/case03j5_global/run_20261012_frame26_1_global_j5_v1"
SPLIT=BASE/"separate_size_views_v1"
K=ROOT/"outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2"
W=11276
H=9200
def load(path):
    img=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    assert img is not None and img.shape[0]>60 and img.shape[1]>60,str(path)
    return img


def run()->dict:
    src=pd.read_csv(BASE/"global_defects.csv",encoding="utf-8-sig")
    main=pd.read_csv(SPLIT/"medium_large_defects.csv",encoding="utf-8-sig")
    small=pd.read_csv(SPLIT/"small_defects_reference.csv",encoding="utf-8-sig")
    assert len(main)==720 and len(small)==14884
    assert set(main.global_defect_id).isdisjoint(set(small.global_defect_id))
    assert set(src.global_defect_id)==set(main.global_defect_id)|set(small.global_defect_id)
    assert main.grade.isin(["MEDIUM","LARGE"]).all()
    assert small.grade.eq("SMALL").all()
    for item in ["medium_large_main.png","small_reference.png"]:
        a=load(SPLIT/item)
        assert a.shape==(H//8+86,W//8+1,3) or a.shape==(
               len(range(0,H,8))+86,len(range(0,W,8)),3)
    a=load(SPLIT/"medium_large_main.png")
    b=load(SPLIT/"small_reference.png")
    assert a.shape==b.shape
    spec=json.loads((K/"summary.json").read_text(encoding="utf-8"))
    assert spec["no_human_labels_provided"] and spec["stage"]=="CASE03K0_SAMPLES_PREPARED_NOT_LABELED"
    sample=pd.read_csv(K/"manual_review_template.csv",encoding="utf-8-sig",
                       keep_default_na=False)
    assert len(sample)==120 and sample.sample_id.is_unique
    assert sample.manual_candidate_label.eq("").all()
    assert sample.manual_complete_roi_review.eq("").all()
    assert sample.manual_any_missed_defect_in_roi.eq("").all()
    assert sample.sample_kind.value_counts().to_dict()=={
        "SMALL_CANDIDATE":96,"NO_J5_CANDIDATE_ROI":24}
    candidate=sample[sample.sample_kind=="SMALL_CANDIDATE"]
    assert candidate.global_defect_id.nunique()==96
    assert candidate.global_defect_id.isin(small.global_defect_id).all()
    assert candidate.groupby("area_group").size().to_dict()=={
        "A_1px2":24,"B_2to3px2":24,"C_4to7px2":24,"D_8pluspx2":24}
    match=candidate.merge(src,on="global_defect_id",suffixes=("","_source"))
    assert np.array_equal(pd.to_numeric(match.source_area_px2).to_numpy(),match.source_area_px2_source.to_numpy())
    assert np.array_equal(pd.to_numeric(match.source_bbox_x_global).to_numpy(),
                          match.source_bbox_x_global_source)
    assert np.array_equal(pd.to_numeric(match.source_bbox_y_global).to_numpy(),
                          match.source_bbox_y_global_source)
    assert (pd.to_numeric(candidate.source_max_feret_px)>0).all()
    assert (candidate.target_blackhat_peak_DN.astype(float)>=0).all()
    for row in sample.itertuples(index=False):
        x0,y0,x1,y1=map(int,(row.x0,row.y0,row.x1,row.y1))
        assert 0<=x0<x1<=W and 0<=y0<y1<=H
        assert x1-x0==y1-y0==128
        if row.sample_kind=="SMALL_CANDIDATE":
            assert x0<=int(row.target_x_global)<x1
            assert y0<=int(row.target_y_global)<y1
        else:
            # Exact intersection check against ALL 15,604 J5 candidate
            # bbox locations; conservative sampling should return none.
            pred=src[
               (src.display_bbox_x_global<x1)&
               (src.display_bbox_xmax_inclusive>=x0)&
               (src.display_bbox_y_global<y1)&
               (src.display_bbox_ymax_inclusive>=y0)]
            assert len(pred)==0,f"predicted candidate in empty ROI {row.sample_id}"
        load(K/"cards"/(row.sample_id+".png"))
    contacts=list((K/"contact_sheets").glob("*.png"))
    assert len(contacts)==5
    for p in contacts:load(p)
    details={
        "J5_global_rows":len(src),
        "main_medium_large":len(main),"reference_small":len(small),
        "identical_preview_geometry":a.shape==b.shape,
        "CASE03K0_reviews":len(sample),
        "candidate_examples":len(candidate),
        "unpredicted_ROIs":24,
        "unpredicted_ROIs_have_zero_J5_bbox_intersections":True,
        "manual_annotation_is_blank":True,
        "all_review_pngs_verified":len(sample)+len(contacts),
        "physical_defect_metrics_not_claimed":True
    }
    print("J5_SPLIT_K0_QA_PASS",json.dumps(details,ensure_ascii=False),flush=True)
    return details


if __name__=="__main__":
    run()
