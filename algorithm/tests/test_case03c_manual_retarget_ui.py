"""Regression tests: nine offline human ROI annotation pages and mask semantics."""
from __future__ import annotations
import base64
import json
import re
from pathlib import Path

import numpy as np
import cv2

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/case03c_manual_retarget/run_20261009_9roi_target_review_v2"
ORIGINAL=ROOT/"outputs/case03c_revision/run_20261009_reference_feature_review/patches"

def _rois():
    html=(OUT/"index.html").read_text(encoding="utf-8")
    block=re.search(r'<script id="review-data" type="application/json">(.*?)</script>',html,re.S)
    assert block is not None
    return json.loads(block.group(1))["rois"]


def test_review_ui_contains_nine_distinct_target_regions_and_images():
    rois=_rois()
    assert [r["number"] for r in rois]==[18,19,21,24,27,31,39,46,56]
    for row in rois:
        assert row["origin_xy"][0]>=0 and row["origin_xy"][1]>=0
        for kind in ("raw","overlay","response"):
            path=OUT/row[kind+"_image"]
            assert path.is_file(),path
            bgr=cv2.imdecode(np.frombuffer(path.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
            assert bgr.shape==(256,256,3),path


def test_annotation_mask_color_bit_exact_from_original_u16_patch():
    for roi in _rois():
        rid=roi["review_id"]
        with np.load(ORIGINAL/f"{rid}_reference_corrected.npz",allow_pickle=False) as patch:
            source_s=patch["S230"]
            source_h=patch["H170_230"]
            np.testing.assert_array_equal(np.asarray(patch["origin_xy"]),roi["origin_xy"])
            for key,src in (("S_mask_base64",source_s),("H_mask_base64",source_h)):
                decoded=np.frombuffer(base64.b64decode(roi[key]),dtype=np.uint8)
                assert decoded.size==8192
                restored=np.unpackbits(decoded,bitorder="little").reshape((256,256)).astype(bool)
                np.testing.assert_array_equal(restored,src)
        assert roi["roi_mask_S230_area_px"]==int(source_s.sum())
        assert roi["roi_mask_H170_area_px"]==int(source_h.sum())
        assert roi["old_red_selected_area_px"]>0


def test_ui_has_no_network_and_requires_exact_user_pixel_or_box():
    page=(OUT/"index.html").read_text(encoding="utf-8")
    assert "raw_global_x" in page
    assert "raw_global_y" in page
    assert "retargeted_full_H_candidate_id" in page
    assert '"original_red_candidate_id":' not in page
    assert "CSV" in page
    assert "XMLHttpRequest" not in page and "fetch(" not in page
    assert "https://" not in page and "http://" not in page
    assert "localStorage" not in page
