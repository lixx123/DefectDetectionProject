"""Offline ten-ROI REAL raw-pixel ground-truth location UI regressions."""
from __future__ import annotations
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd


ROOT=Path(__file__).resolve().parents[1]
ANALYSIS=ROOT/"outputs/case03d_manual_review_analysis/run_20261010_092200"
PAGE=ANALYSIS/"ten_roi_true_target_click_annotation"


def test_target_location_ui_contains_precisely_the_10_flagged_rois():
    records=pd.read_csv(PAGE/"ten_roi_manifest.csv")
    issues=pd.read_csv(ANALYSIS/"ROI_annotation_scope_exceptions_10.csv")
    assert len(records)==len(issues)==10
    assert records["candidate_id"].is_unique
    assert set(records["candidate_id"])==set(issues["candidate_id"])
    assert records["human_note"].notna().all()
    for k in ("candidate_id","human_note"):
        lhs=records.set_index("candidate_id")
        rhs=issues.set_index("candidate_id")
        if k=="human_note":
            for cid in records["candidate_id"]:
                assert lhs.loc[cid,k]==rhs.loc[cid,"note"]


def test_ui_has_10_full_resolution_160px_raw_windows_and_matching_status():
    records=pd.read_csv(PAGE/"ten_roi_manifest.csv")
    assert len(list((PAGE/"assets").glob("*.png")))==20
    for row in records.itertuples(index=False):
        assert 0<=row.roi_x0<=11276-160
        assert 0<=row.roi_y0<=9200-160
        assert row.roi_x0<=row.bbox_x<row.roi_x0+160
        assert row.roi_y0<=row.bbox_y<row.roi_y0+160
        for rel in (row.raw_image,row.status_image):
            full=PAGE/rel
            assert full.is_file() and full.stat().st_size>2000
            image=cv2.imdecode(
                np.frombuffer(full.read_bytes(),dtype=np.uint8),
                cv2.IMREAD_COLOR)
            assert image is not None and image.shape==(160,160,3)


def test_click_annotation_controls_never_turn_parent_H_id_into_target_truth():
    html=(PAGE/"index.html").read_text(encoding="utf-8")
    assert html.count('id="reviewData"')==1
    for phrase in (
        "单击定位中心","双击两角框范围","多边形描轮廓",
        "RAW坐标","导出RAW定位CSV","导出JSON备份",
        "一个区域可以标多处","source_parent_H_candidate_id",
        "target_is_independent_of_parent_H_ID",
        "true_target_click",
    ):
        assert phrase in html,phrase
    # Historical labels appear in read-only navigation metadata, but this
    # UI does NOT provide defect-subtype classification controls.
    assert 'data-label="confirmed_dark_spot"' not in html
    assert 'data-label="confirmed_fine_line"' not in html
    assert 'src="https://' not in html
    assert 'fetch(' not in html
    assert "4*scale" not in html  # no double magnification in coordinate output


def test_existing_binary_detector_is_not_overwritten_by_ui_task():
    run=ROOT/"outputs/case03d_autodetect/run_20261009_autodetect_final"
    old=ROOT/"outputs/case03d/run_20261009_190000"
    assert (run/"detected_provisional.csv").is_file()
    assert (run/"candidate_decisions_full.csv").is_file()
    assert (old/"manual_label_revision_after_review045/strict_corrected_labels.csv").is_file()
    assert (PAGE/"README.md").is_file()
    assert (ROOT/"src/visualization/case03d_10roi_annotation_template.html").is_file()


def test_exact_roi_image_geometry_matches_original_16bit_big_endian_raw():
    from config import user_config as cfg
    records=pd.read_csv(PAGE/"ten_roi_manifest.csv")
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",dtype=">u2",mode="r",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    for row in records.iloc[[0,5]].itertuples(index=False):
        data=np.asarray(raw[row.roi_y0:row.roi_y0+160,
                            row.roi_x0:row.roi_x0+160],dtype=np.float32)
        lo,hi=np.percentile(data,[1,99.5])
        hi=max(lo+1,hi)
        expected=np.uint8(np.rint(np.clip((data-lo)/(hi-lo),0,1)*255))
        actual=cv2.imdecode(np.frombuffer((PAGE/row.raw_image).read_bytes(),
                             dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
        assert np.array_equal(expected,actual)
