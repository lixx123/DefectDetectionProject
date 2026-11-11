"""Case03-J2 on-disk acceptance: one-piece verified with source provenance."""
from pathlib import Path
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
I=ROOT/"outputs/case03i_annotation/run_20261010_frame1_frame2_pixel_grade_v1"
T=ROOT/"outputs/case03j_continuous/run_20261010_27windows_one_piece_v2"
objs=pd.read_csv(T/"object_level_grades.csv")
windows=pd.read_csv(T/"window_continuity_check.csv")
edges=pd.read_csv(T/"all_link_edges_with_context.csv")
assert len(windows)==27 and len(objs)==457
assert int(windows.original_pixels.sum())==16349
assert int(windows.inferred_bridge_pixels.sum())==463
assert (windows.visually_disconnected_linked_objects==0).all()
assert (objs.original_area_px2>0).all()
assert objs.member_count.sum()==466
assert ((objs.display_support_pixels-objs.original_area_px2)==objs.inferred_bridge_pixels).all()
pngs=list((T/"figures").glob("*.png"))
masks=list((T/"masks").glob("*.npz"))
assert len(pngs)==27 and len(masks)==27
for p in pngs:
    im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),
                    cv2.IMREAD_COLOR)
    assert im is not None and im.shape[1]==4*256*3,p
touches=[]
for p in masks:
    with np.load(p) as z:
        source=z["source_exact_mask"]>0
        oldlabel=z["original_region_labels"]
        grouped=z["grouped_original_only_ids"]
        bridge=z["inferred_bridge_ids"]
        combined=z["one_piece_visual_ids"]
        assert np.array_equal(source,oldlabel>0)
        assert np.array_equal(source,grouped>0)
        assert np.array_equal(combined>0,source|(bridge>0))
        assert not np.any(source&(bridge>0))
        # No bridge should border a distinct independent object even
        # diagonally; otherwise one displayed contour might over-link.
        for j in np.unique(bridge):
            if j==0:continue
            near=cv2.dilate(np.uint8(bridge==j),np.ones((3,3),np.uint8))
            leakage=int(np.count_nonzero((near>0)&(grouped>0)&(grouped!=j)))
            if leakage:
                touches.append((p.name,int(j),leakage))
        oldp=I/"region_masks"/p.name.replace("_contour_provenance.npz","_graded_masks.npz")
        with np.load(oldp,allow_pickle=False) as src:
            assert np.array_equal(source,src["exact_final_mask"]>0)
            assert np.array_equal(oldlabel,src["local_region_labels_int32"])
w=objs[(objs.frame=="26_1")&(objs.window_id=="E2_W005")&(objs.member_count>1)]
assert len(w)==1
assert set(str(w.iloc[0]["members"]).split(";"))=={"7","12","14","15","16","17","19","20"}
assert w.iloc[0]["continuous_display_components"]==1
assert int(w.iloc[0]["original_area_px2"])==5068
assert int(w.iloc[0]["inferred_bridge_pixels"])==441
print("QA_CONTIGUITY",{
      "panels":len(pngs),"source_npz_verified":len(masks),
      "W005_components_grouped":8,
      "W005_extra_display_pixels":441,
      "other_object_adjacent_bridge_pixels":touches,
      "original_source_pixels_unchanged":True})
if touches:raise AssertionError("inferred bridge touches independently labeled object")
