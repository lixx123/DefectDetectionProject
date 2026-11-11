"""联合筛噪门控不得依赖人工标注、不能改变H原像素或独立产生G/M候选。"""
import cv2
import numpy as np
import pytest
from src.detection.case03g_joint_gate import (
    JointGateConfig, decide_gate, build_joint_maps,
)


def fixture():
    H=np.zeros((64,64),dtype=np.uint8)
    H[20:24,20:24]=1   # area16 reliable H shape
    H[25,25]=1         # nearby 1px near large H (8-connectivity separation?)
    H[52,52]=1         # isolated 1px noise candidate
    H[40,40]=1         # isolated 1px refined evidence
    n,l,stats,_=cv2.connectedComponentsWithStats(H,8)
    refined=l.copy()
    return n,l,stats,refined


def test_protect_nearby_and_gaussian():
    n,l,stats,F=fixture()
    assert n==5
    states=["keep", "suggest_hide", "suggest_hide", "suggest_hide"]
    sources=[("H170_230",),("H170_230",),
             ("H170_230","gaussian22"),("H170_230",)]
    gate,reason=decide_gate(l,stats,states,sources,JointGateConfig())
    assert gate[0]=="keep"
    assert gate[1]=="protected_review"
    assert gate[2]=="protected_review"
    assert gate[3]=="hide_suggestion"
    masks=build_joint_maps(l,F,gate)
    assert int(masks["h_hidden_suggestion"].sum())==1
    assert np.array_equal(masks["h_original"],
                          masks["h_hidden_suggestion"]|masks["h_kept_display"])


def test_refinement_extra_pixels_respect_gate():
    n,l,stats,F=fixture()
    F[18,20]=1
    states=["keep", "suggest_hide", "suggest_hide", "suggest_hide"]
    sources=[("H170_230",),("H170_230",),("H170_230","closing61"),
             ("H170_230",)]
    gate,_=decide_gate(l,stats,states,sources,JointGateConfig())
    masks=build_joint_maps(l,F,gate)
    assert masks["fused_joint_display"][18,20]
    assert not masks["fused_joint_display"][52,52]
    assert masks["h_original"][52,52] # source remains intact


def test_invalid_H_id_mapping_rejected():
    n,l,stats,F=fixture()
    F[52,52]=0
    with pytest.raises(AssertionError,match="ownership"):
        build_joint_maps(l,F,["keep"]*(n-1))


def test_bad_state_and_cardinality_fail():
    n,l,stats,F=fixture()
    with pytest.raises(ValueError,match="state"):
        decide_gate(l,stats,["delete"]*(n-1),
                    [("H170_230",)]*(n-1),JointGateConfig())
    with pytest.raises(ValueError,match="catalogue"):
        decide_gate(l,stats,["keep"],
                    [("H170_230",)],JointGateConfig())


def test_manual_data_unavailable_to_gate():
    import inspect
    sig=inspect.signature(decide_gate)
    for key in sig.parameters:
        assert "manual" not in key and "label_truth" not in key
