"""K8H independent cross-stage provenance and image consistency QA."""
from pathlib import Path
import json,sys,math,hashlib
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8g_display_boxes import expand_bbox_xyxy,overlap_area
OUT=C.OUTPUT_ROOT/"case03k8h_f1_band02_review_overlay/run_20261015_f1_b2_K8D_unreviewed_restore_v1"
D=C.OUTPUT_ROOT/"case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3"
E=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
G=C.OUTPUT_ROOT/"case03k8g_display_zoom_labels/run_20261015_26_1_2_boxes_1p5x_1px_size_v2"
F=C.OUTPUT_ROOT/"case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2"

def img(path):
    arr=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if arr is None:raise AssertionError(f"not PNG {path}")
    return arr

def run():
    cand=pd.read_csv(OUT/"B02_four_original_K8D_source_candidates.csv")
    zone=pd.read_csv(OUT/"B02_two_review_zone_1p5_DISPLAY_geometry.csv")
    src=pd.read_csv(D/"frame26_1/all_K8D_original_vs_outer_review.csv")
    assert len(cand)==4 and set(cand.candidate_B_label)=={614,1273,1562,1902}
    assert set(cand.review_zone)=={"A","B"}
    assert cand.user_confirmed_this_firstframe.eq(False).all()
    assert cand.can_use_as_final_defect_area.eq(False).all()
    assert cand.old_source_masks_modified.eq(False).all()
    assert len(zone)==4 and set(zone.stride)=={4,8}
    assert zone.manual_confirmation_pending.all()
    assert zone.visual_only_not_J5_official_defect.all()
    old_J5=pd.read_csv(F/"frame26_1/workband_unified_candidate_review_register.csv")
    assert len(old_J5)==683
    assert old_J5.source.eq("FROZEN_J5_WORK").all()
    assert not old_J5.visual_defect_confirmed_by_user.any()
    assert not any(
        p.name.startswith("K8E_F1_B2") for p in F.glob("frame26_1/*outer_mask*.png"))
    for x in cand.itertuples(index=False):
        source=src[(src.band_id==2)&(src.candidate_label==x.candidate_B_label)]
        assert len(source)==1
        source=source.iloc[0]
        assert int(source.source_area_px2)==int(x.original_B_H_pixel_area_px2)
        assert int(source.K8D_review_outer_px2)==int(x.K8D_trial_RAW_outer_pixel_area_px2)
        assert np.isclose(source.K8D_length_detector_um_PROVISIONAL,
                          x.trial_RAW_outer_length_IMAGE_um)
        assert source.status==x.K8D_status
        with np.load(D/"frame26_1"/"band02"/(
                f"F1_B2_C{x.candidate_B_label:05d}_K8D_all_masks.npz"),
                allow_pickle=False) as m:
            orig=m["original_B_source"].astype(bool)
            new=m["K8D_full_outer"].astype(bool)
            assert orig.sum()==x.original_B_H_pixel_area_px2
            assert new.sum()==x.K8D_trial_RAW_outer_pixel_area_px2
            assert np.all(new[orig])
    for label,expected in [(614,2262),(1273,1646),(1562,1781),(1902,398)]:
        assert int(cand[cand.candidate_B_label==label].K8D_trial_RAW_outer_pixel_area_px2.iloc[0])==expected
    for key in ("A","B"):
        q=zone[zone.review_zone==key]
        assert len(q)==2
        bb=[json.loads(x) for x in q.enlarged_display_RAW_xyxy]
        assert np.allclose(bb[0],bb[1])
        labs=json.loads(q.iloc[0].source_K8D_candidate_labels)
        assert set(labs)==({614,1273,1562} if key=="A" else {1902})
        source_boxes=[]
        for label in labs:
            part=cand[cand.candidate_B_label==label].iloc[0]
            source_boxes.append(json.loads(part.raw_trial_bbox_global_xyxy))
        raw_bbox=(min(x[0] for x in source_boxes),min(x[1] for x in source_boxes),
                  max(x[2] for x in source_boxes),max(x[3] for x in source_boxes))
        correct=expand_bbox_xyxy(raw_bbox,(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
        assert np.allclose(correct,bb[0])
    for scale,name in [(8,"01_F1_B02_review_reinstated_plus_J5_1to8.png"),
                       (4,"02_F1_B02_review_reinstated_plus_J5_1to4.png")]:
        new=img(OUT/name)
        old_name=("01_MED_LARGE_boxes_1p5x_1px_with_area_length_overview_1to8.png" if scale==8 else
                  "02_MED_LARGE_boxes_1p5x_1px_with_area_length_detail_1to4.png")
        old=img(G/"frame26_1"/old_name)
        assert new.shape==old.shape==(
            math.ceil(C.RAW_HEIGHT/scale)+94,math.ceil(C.RAW_WIDTH/scale),3)
        positions=zone[zone.stride==scale]
        # All changes must be within the K8H rectangles/label plaques OR
        # in the modified header. The old G J5 marks are not redrawn.
        permitted=np.zeros(new.shape[:2],bool)
        permitted[:94,:]=True
        for row in positions.itertuples(index=False):
            b=list(map(int,json.loads(row.rendered_frame_display_rectangle_inclusive)))
            x0,y0,x1,y1=b
            permitted[94+y0:94+y1+1,x0:x1+1]=True
            l=list(map(int,json.loads(row.label_position_display_xyxy_exclusive)))
            x0,y0,x1,y1=l
            permitted[94+y0:94+y1,x0:x1]=True
        diff=np.any(new!=old,axis=2)
        assert not np.any(diff&~permitted),(
            "Unexpected changed source pixels outside new K8H review overlay")
        assert diff.sum()>0
    atlas=img(OUT/"03_B02_two_REVIEW_ZONES_RAW_vs_trial_contours.png")
    assert atlas.shape[1]==1200 and atlas.shape[0]==924
    for i in (614,1273,1562,1902):
        assert img(OUT/f"K8D_B02_C{i}_K8E_review_reference.png").ndim==3
    summ=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    assert summ["K8D_raw_trial_candidates_reintroduced"]==4
    assert summ["review_zones"]==2
    assert summ["no_J5_K8B_K8C_K8D_K8E_K8F_K8G_original_results_modified"]
    report={"stage":"K8H_REAL_RAW_CORRESPONDENCE_AND_DISPLAY_ONLY_QA_PASS",
            "frame":"26 (1)","band_id":2,
            "source_K8D_candidates":[614,1273,1562,1902],
            "two_display_review_zones_not_two_approved_defects":True,
            "K8D_outer_mask_px_area_match_original_archive":True,
            "new_ROI_from_real_RAW_coordinates_exact":True,
            "K8G_original_body_pixels_untouched_outside_review_overlays":True,
            "K8F_original_firstframe_683_candidates_unmodified":True,
            "physical_area_grade_changes":False,
            "all_unreviewed_candidates_keep_pending":True}
    p=OUT/"independent_QA.json"
    if p.exists():raise FileExistsError(p)
    p.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8H_REAL_RAW_CORRESPONDENCE_AND_DISPLAY_ONLY_QA_PASS",
          json.dumps(report,ensure_ascii=False),flush=True)
if __name__=="__main__":run()
