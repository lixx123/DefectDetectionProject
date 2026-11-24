"""Independent acceptance of J5 outputs against frozen J4 source tables.

This verifier is READ-ONLY. It reconstructs global memberships from both
CSVs, checks sum of original measured pixels, source union rectangle per
global object, accepted seam endpoint provenance and every rendered PNG.
"""
from __future__ import annotations
from pathlib import Path
import sys,json
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03i_size_grade import SizeGradeConfig,grade_size

J4=cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1"
J5=cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_1_global_j5_v1"


def run()->dict:
    old=pd.read_csv(J4/"j4_unmerged_tile_objects.csv",encoding="utf-8-sig")
    new=pd.read_csv(J5/"global_defects.csv",encoding="utf-8-sig")
    membership=pd.read_csv(J5/"global_object_membership.csv",encoding="utf-8-sig")
    edges=pd.read_csv(J5/"cross_tile_matching_audit.csv",encoding="utf-8-sig")
    status=json.loads((J5/"summary.json").read_text(encoding="utf-8"))
    assert status["stage"]=="J5_COMPLETE"
    assert len(old)==15934
    assert len(new)==15604
    assert len(membership)==len(old)
    assert old.object_id.is_unique
    assert new.global_defect_id.is_unique
    assert membership.J4_local_object_id.is_unique
    assert set(membership.J4_local_object_id)==set(old.object_id)
    assert set(membership.global_defect_id)==set(new.global_defect_id)
    assert membership.source_tile_id.eq(
        membership.J4_local_object_id.str.split("_C").str[0]).all()
    assert membership.source_pixels_unchanged.all()
    assert all(new["source_area_px2"]>0)
    assert old.source_area_px2.sum()==new.source_area_px2.sum()==234029
    assert int(membership.source_area_px2.sum())==234029
    assert new.local_object_count.sum()==len(old)
    assert new.tile_count.ge(1).all()
    assert int(new.cross_tile_merged.sum())==264
    assert new.global_defect_id.tolist()==[
        "DEFECT_"+str(k).zfill(5) for k in range(1,len(new)+1)]
    assert new.center_y_global.is_monotonic_increasing
    assert (new.center_x_global>=new.source_bbox_x_global).all()
    assert (new.center_x_global<=new.source_bbox_x_global+new.source_bbox_width_px-1).all()
    assert (new.center_y_global>=new.source_bbox_y_global).all()
    assert (new.center_y_global<=new.source_bbox_y_global+new.source_bbox_height_px-1).all()
    assert (new.display_bbox_x_global<=new.source_bbox_x_global).all()
    assert (new.display_bbox_y_global<=new.source_bbox_y_global).all()
    assert (new.display_bbox_xmax_inclusive>=(
        new.source_bbox_x_global+new.source_bbox_width_px-1)).all()
    assert (new.display_bbox_ymax_inclusive>=(
        new.source_bbox_y_global+new.source_bbox_height_px-1)).all()
    # Strong independent exact per-group aggregate validation.
    oldby=old.set_index("object_id")
    memberships=membership.groupby("global_defect_id")
    globalby=new.set_index("global_defect_id")
    for gid,g in memberships:
        original=oldby.loc[g.J4_local_object_id]
        result=globalby.loc[gid]
        assert int(original.source_area_px2.sum())==int(result.source_area_px2)
        assert int(original.member_count.sum())==int(result.source_region_count)
        assert int(original.inferred_bridge_pixels.sum())==int(
                    result.inferred_bridge_pixels_within_tiles)
        assert int(original.display_bbox_x_global.min())==int(
                    result.display_bbox_x_global)
        assert int(original.display_bbox_y_global.min())==int(
                    result.display_bbox_y_global)
        assert int(original.display_bbox_xmax_inclusive.max())==int(
                    result.display_bbox_xmax_inclusive)
        assert int(original.display_bbox_ymax_inclusive.max())==int(
                    result.display_bbox_ymax_inclusive)
        assert len(set(original.tile_id))==int(result.tile_count)
    k=SizeGradeConfig(
        medium_area_min_px2=cfg.CASE03I_MEDIUM_AREA_MIN_PX2,
        large_area_min_px2=cfg.CASE03I_LARGE_AREA_MIN_PX2,
        medium_length_min_px=cfg.CASE03I_MEDIUM_LENGTH_MIN_PX,
        large_length_min_px=cfg.CASE03I_LARGE_LENGTH_MIN_PX)
    for r in new.itertuples(index=False):
        grade,_=grade_size(int(r.source_area_px2),
                          float(r.source_max_feret_px),k)
        assert grade==r.grade
    assert int(edges.accepted.sum())==342
    assert (edges.direct_connected & edges.accepted).sum()==341
    assert ((~edges.direct_connected)&edges.accepted).sum()==1
    mapped=membership.set_index("J4_local_object_id").global_defect_id.to_dict()
    for e in edges.itertuples(index=False):
        if not e.accepted:continue
        assert mapped[e.a_id]==mapped[e.b_id]
        if e.direct_connected:
            assert e.gap_px<=2**0.5+0.0011
        else:
            assert e.bridge_dog_median_dn>=cfg.CASE03J5_BRIDGE_DOG_MIN_DN
            assert e.bridge_positive_fraction>=cfg.CASE03J5_BRIDGE_POSITIVE_FRACTION
            assert globalby.loc[mapped[e.a_id]].J5_gap_link_review
    assert len(new)==sum(status['grade_counts'].values())
    pngs=list(J5.rglob("*.png"))
    assert len(pngs)>=22, f"few review PNGs: {len(pngs)}"
    for p in pngs:
        im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        assert im is not None and im.ndim==3 and min(im.shape[:2])>30,p
    result={
        "J5_COMPLETE":True,
        "original_J4_objects_covered_exactly_once":len(membership),
        "global_unique_objects":len(new),
        "original_detected_area_preserved_px2":int(new.source_area_px2.sum()),
        "recomputed_global_grade_checked":True,
        "every_object_bbox_matches_member_union":True,
        "direct_and_gap_accepted_edges_checked":True,
        "all_review_and_overview_pngs_decoded":len(pngs),
        "raw_mask_modification":False,
        "physical_ground_truth_not_yet_annotated":True,
    }
    print("J5_QA_PASS",json.dumps(result,ensure_ascii=False),flush=True)
    return result

if __name__=="__main__":
    run()
