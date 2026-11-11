"""Independent acceptance of Case03-J1 association outputs and source immutability."""
from pathlib import Path
import numpy as np,pandas as pd,cv2,json
ROOT=Path(__file__).resolve().parents[1]
new=ROOT/"outputs/case03j_fragment_association/run_20261010_W005_fragment_link_guarded_v2"
source=ROOT/"outputs/case03i_annotation/run_20261010_frame1_frame2_pixel_grade_v1"
group=pd.read_csv(new/"object_hypotheses.csv")
links=pd.read_csv(new/"association_link_audit.csv")
members=pd.read_csv(new/"source_region_to_object.csv")
windows=pd.read_csv(new/"window_before_after_counts.csv")
assert len(windows)==27 and len(group)==459 and len(members)==466
assert windows["separate_region_count"].sum()==466
assert windows["after_association_object_count"].sum()==459
assert int(windows.original_mask_pixels.sum())==int(windows.grouped_mask_pixels.sum())==16349
assert links["accepted"].sum()==7
assert int(group.area_union_original_pixels.sum())==16349
pngs=list(new.rglob("*.png"))
npzs=list((new/"exact_masks").glob("*.npz"))
assert len(pngs)==27 and len(npzs)==27
for p in pngs:
    img=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    assert img is not None and min(img.shape[:2])>=256,p
for p in npzs:
    with np.load(p,allow_pickle=False) as z:
        mask=z["original_mask"]>0
        old=z["source_region_labels"]
        obj=z["grouped_object_labels"]
        assert np.array_equal(mask,obj>0)
        assert np.array_equal(mask,old>0)
    with np.load(source/"region_masks"/p.name.replace("_groupmap.npz",".npz"),
                 allow_pickle=False) as q:
        assert np.array_equal(mask,q["exact_final_mask"]>0)
        assert np.array_equal(old,q["local_region_labels_int32"])
w=group[(group.frame=="26_1")&(group.window_id=="E2_W005")&(group.member_count>1)]
assert len(w)==1 and w.iloc[0].member_count==6
assert int(w.iloc[0].area_union_original_pixels)==4866
assert float(w.iloc[0].max_feret_centers_px)>180
print("CASE03J_PILOT_QA_PASS",json.dumps({
    "images_decoded":len(pngs),"mask_archives":len(npzs),
    "original_regions":466,"new_group_hypotheses":459,
    "accepted_links":int(links["accepted"].sum()),
    "W005_original_members_merged":int(w.iloc[0].member_count),
    "W005_total_area_px2":int(w.iloc[0].area_union_original_pixels),
    "W005_max_Feret_centers_px":float(w.iloc[0].max_feret_centers_px),
    "original_mask_pixel_count_unchanged":True
},ensure_ascii=False))
