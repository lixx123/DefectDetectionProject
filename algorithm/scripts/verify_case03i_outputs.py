"""Independent on-disk acceptance checks for Case03-I generated assets."""
from __future__ import annotations
from pathlib import Path
import cv2,numpy as np,pandas as pd,json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/case03i_annotation/run_20261010_frame1_frame2_pixel_grade_v1"
T=ROOT/"outputs/case03t_threshold_pilot/run_20261010_sample26_frame2_three_methods_v1"
rows=pd.read_csv(OUT/"all_candidate_size_grades.csv",encoding="utf-8-sig")
summary=pd.read_csv(OUT/"roi_grade_summary.csv",encoding="utf-8-sig")
assert len(rows)==466 and len(summary)==27
assert set(rows["size_grade"])=={"SMALL","MEDIUM","LARGE"}
assert summary["candidate_regions"].sum()==len(rows)
assert int(summary["refined_candidate_mask_pixels"].sum())==int(rows["area_px2"].sum())
assert rows.groupby("frame").size().to_dict()=={"26_1":349,"26_2":117}
assert not (rows["area_px2"]<=0).any()
assert rows["max_feret_centers_px"].min()>=1
assert not rows["grade_is_not_quality_acceptance"].eq(False).any()
pngfiles=list(OUT.rglob("*.png"))
assert len(pngfiles)==42, f"expected 42 PNGs, found {len(pngfiles)}"
for p in pngfiles:
    decoded=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    assert decoded is not None and decoded.shape[0]>0 and decoded.shape[1]>0,p
maps=list((OUT/"region_masks").glob("*.npz"))
assert len(maps)==27
for p in maps:
    with np.load(p,allow_pickle=False) as z:
        mask=z["exact_final_mask"]>0
        grade=z["grade_mask_uint8"]
        ids=z["local_region_labels_int32"]
        assert np.array_equal(mask,grade>0)
        assert np.array_equal(mask,ids>0)
        assert set(np.unique(grade)).issubset({0,1,2,3})
        if p.name.startswith("26_2_"):
            win=p.name.removeprefix("26_2_").removesuffix("_graded_masks.npz")
            with np.load(T/"masks"/(win+"_method_masks.npz"),allow_pickle=False) as old:
                assert np.array_equal(mask,old["fixed170_230_final"].astype(bool))
print("CASE03I_QA_PASS",
      json.dumps({"images_decoded":len(pngfiles),"mask_archives":len(maps),
                  "graded_regions":len(rows),"windows":len(summary),
                  "frame1":349,"frame2":117,
                  "frame2_source_masks_all_equal":True},ensure_ascii=False))
