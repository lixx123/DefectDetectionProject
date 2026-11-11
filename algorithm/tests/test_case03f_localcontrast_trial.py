"""Case03-F小面积噪声建议：验证保守判别和RAW邻域统计。"""
from __future__ import annotations
import numpy as np
import pytest

from src.detection.candidate_local_noise import (
    NoiseTrialConfig, classify_candidate, local_raw_statistics,
)

CONFIG = NoiseTrialConfig()


def synthetic_image(candidate_dn: int, background_dn: int = 2000):
    raw = np.full((64, 64), background_dn, dtype=np.uint16)
    raw[30, 30] = candidate_dn
    H = np.zeros((64, 64), dtype=bool)
    H[30, 30] = True
    candidate = H.copy()
    return raw, H, candidate


def test_small_low_raw_contrast_suggest_hide():
    raw,H,candidate = synthetic_image(1990)
    metric = local_raw_statistics(raw,H,candidate,(30,30,1,1),CONFIG)
    assert metric["reference_valid"]
    assert metric["raw_delta_dn"] == 10
    assert metric["relative_contrast"] == pytest.approx(0.005)
    status, _ = classify_candidate(1,1,1,metric,False,CONFIG)
    assert status == "suggest_hide"


def test_genuine_tiny_dark_spot_retained():
    raw,H,candidate = synthetic_image(1600)
    metric = local_raw_statistics(raw,H,candidate,(30,30,1,1),CONFIG)
    assert metric["reference_valid"]
    assert metric["relative_contrast"] == pytest.approx(.2)
    assert metric["significance_z"] > 3
    assert classify_candidate(1,1,1,metric,False,CONFIG)[0] == "keep"


def test_invalid_reference_never_auto_hidden():
    raw,H,candidate = synthetic_image(1990)
    # 窗口截断使局部背景不完整，不据此判噪声。
    candidate = np.zeros_like(H)
    candidate[0, 0] = True
    H = candidate.copy()
    metric = local_raw_statistics(raw,H,candidate,(0,0,1,1),CONFIG)
    assert metric["reference_valid"] is False
    assert classify_candidate(1,1,1,metric,False,CONFIG)[0] == "keep_review"


def test_cross_scratch_large_component_protected():
    weak = dict(reference_valid=True, relative_contrast=.001, significance_z=.01)
    assert classify_candidate(1936,160,18,weak,False,CONFIG)[0] == "keep"
    assert classify_candidate(3,3,1,weak,True,CONFIG)[0] == "keep_review"


def test_non_candidate_H_exclusion_and_ring_guard():
    raw,H,candidate = synthetic_image(1990)
    raw[30,38] = 0
    H[30,38] = True
    metric = local_raw_statistics(raw,H,candidate,(30,30,1,1),CONFIG)
    assert metric["background_median_dn"] == 2000
    assert metric["background_mad_dn"] == 0


def test_invalid_geometry_fails_closed():
    raw,H,candidate = synthetic_image(1990)
    with pytest.raises(ValueError):
        local_raw_statistics(raw,H,candidate,(100,100,1,1),CONFIG)
