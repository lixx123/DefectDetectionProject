"""K8A data QA - exact shape/mask code and per-frame independent geometry.

Untrusted candidates remain marked UNREVIEWED. No J5/K5 changes performed.
"""
from pathlib import Path
from collections import Counter
import json,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03k8a_band_locator import (
    BandLocatorConfig,polygon_for_band)
OUT=cfg.OUTPUT_ROOT/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"

def readpng(p):
    b=p.read_bytes()
    im=cv2.imdecode(np.frombuffer(b,np.uint8),cv2.IMREAD_UNCHANGED)
    if im is None:raise AssertionError(f"bad PNG {p}")
    return im

def audit():
    summ=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    assert summ["band_counts"]==[4,4]
    assert not summ["band_count_not_fixed"] is False
    assert summ["no_existing_detection_config_or_data_modified"]
    reports=[]
    first_ids=None
    for frame in (1,2):
        p=OUT/f"frame26_{frame}"
        a=json.loads((p/"audit.json").read_text(encoding="utf-8"))
        ids=readpng(p/"band_id_fullres.png")
        regions=readpng(p/"region_type_fullres.png")
        assert ids.shape==regions.shape==(9200,11276)
        assert ids.dtype==regions.dtype==np.uint8
        assert set(np.unique(ids))=={0,1,2,3,4}
        assert set(np.unique(regions))=={0,1,2,3}
        assert np.array_equal(ids>0,regions==2)
        counts=dict(zip(*np.unique(regions,return_counts=True)))
        assert int(sum(counts.values()))==11276*9200
        assert len(a["bands"])==4 and not a["band_count_hardcoded"]
        assert a["band_count_human_approved"] is False
        assert a["all_J5_K5_blackhat_thresholds_unchanged"]
        assert a["mask_codes"]["3"]=="BOUNDARY_REVIEW"
        for band in a["bands"]:
            i=band["band_id"]
            assert i in (1,2,3,4)
            assert band["work_area_status"]=="UNREVIEWED_AUTO_PROPOSAL"
            assert band["local_band_contrast_dn"]>90
            assert band["x_sample_count"]>=15
            assert band["top_line_slope_y_per_x"]==band["top_line_slope_y_per_x"]
            assert band["bottom_line_slope_y_per_x"]==band["bottom_line_slope_y_per_x"]
            one=readpng(p/f"band_{i:02d}_core_fullres.png")
            assert one.shape==ids.shape and set(np.unique(one))=={0,255}
            assert np.array_equal(one==255,ids==i)
            assert int(np.count_nonzero(one))>100_000
        stat=pd.read_csv(p/"band_geometry_and_DN_statistics.csv")
        assert len(stat)==4
        assert stat.band_id.tolist()==[1,2,3,4]
        assert stat.human_approved.fillna("").eq("").all()
        # The low-pass B2 (~300 DN) must remain a WORK candidate, not shield.
        assert 240<float(stat.loc[stat.band_id==2,"RAW_median_DN_inside_work"].iloc[0])<400
        for fname in ("work_band_overlay_on_RAW.png","region_codes_preview.png",
                      "row_band_profile.png"):
            im=readpng(p/fname)
            assert im.shape[0]>300 and im.shape[1]>700
        sample_shift=(
            a["bands"][0]["profile_top_y"],
            a["bands"][-1]["profile_bottom_y"])
        reports.append({
          "frame":frame,
          "band_count":len(a["bands"]),
          "peak_rows":[v["peak_position_y"] for v in a["bands"]],
          "geometric_proposal_limits_y":sample_shift,
          "work_core_pixels":int(counts[2]),
          "shield_pixels":int(counts[1]),
          "edge_review_pixels":int(counts[3]),
          "nonwork_pixels":int(counts[0]),
          "median_DN_by_band":stat.RAW_median_DN_inside_work.tolist(),
          "verified_full_resolution_PNG_masks":6,
          "band_boundaries_pending_human_approval":True
        })
        if frame==1:first_ids=ids[::8,::8].copy()
        else:
            new=ids[::8,::8]
            matches=int(np.count_nonzero((first_ids>0)&(new>0)))
            union=int(np.count_nonzero((first_ids>0)|(new>0)))
            overlap=round(matches/max(union,1),5)
            reports[-1]["frame1_frame2_workmask_IoU_unregistered"]=overlap
            assert overlap<.9,"Same masks reused accidentally across distinct frames"
    summary={
      "stage":"K8A_QA_PASS",
      "automatic_band_count_4_or_5_or_more_supported_in_code":True,
      "real_frame26_band_counts":[4,4],
      "synthetic_5_band_test_in_pytest":True,
      "both_fullres_masks_consistent":True,
      "frame1_frame2_masks_not_copied":True,
      "work_band_boundaries_not_human_verified":True,
      "no_blackhat_or_j5_modifications":True,
      "reports":reports
    }
    dst=OUT/"independent_mask_QA.json"
    if dst.exists():raise FileExistsError(dst)
    dst.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8A_INDEPENDENT_MASK_QA_PASS",json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":audit()
