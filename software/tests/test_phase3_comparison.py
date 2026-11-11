from copy import deepcopy
from pathlib import Path
import numpy as np
from core.adapters.comparison import compare_results
from domain.common import ArtifactReference
from examples.phase2_roundtrip import example_result
from core.adapters.roi_mapper import write_png


def test_object_comparison_lists_area_length_position_and_source_changes(tmp_path):
    before = example_result()
    before.intermediate_results.final_mask = ArtifactReference(path="full.png")
    before.defects[0].geometry.mask_reference = ArtifactReference(path="defect.npz")
    before.defects[0].detection.candidate_ids = ["C001"]
    write_png(tmp_path / "full.png", np.ones((2, 2), np.uint8))
    np.savez_compressed(tmp_path / "defect.npz", mask=np.ones((2, 2)), global_RAW_bbox_xyxy_exclusive=np.array([0, 0, 2, 2]))
    current = deepcopy(before)
    current.defects[0].geometry.area_px += 1
    current.defects[0].geometry.length_px += 1
    current.defects[0].detection.candidate_ids = ["C999"]
    report = compare_results(before, current, tmp_path, tmp_path)
    assert report["status"] == "FAIL"
    assert report["area_changes"] and report["Feret_changes"] and report["source_membership_changes"]
    assert report["final_binary_diff_pixels"] == 0


def test_sequential_id_permutation_is_reported_without_faking_physical_change(tmp_path):
    before = example_result()
    before.intermediate_results.final_mask = ArtifactReference(path="full.png")
    before.defects[0].geometry.mask_reference = ArtifactReference(path="defect.npz")
    before.defects[0].detection.candidate_ids = ["C001"]
    write_png(tmp_path / "full.png", np.ones((2, 2), np.uint8))
    np.savez_compressed(tmp_path / "defect.npz", mask=np.ones((2, 2)), global_RAW_bbox_xyxy_exclusive=np.array([0, 0, 2, 2]))
    after = deepcopy(before)
    after.defects[0].identity.defect_id = "NEW_LOCAL_ID"
    report = compare_results(before, after, tmp_path, tmp_path)
    assert report["status"] == "PASS"
    assert report["id_changes"][0]["after_id"] == "NEW_LOCAL_ID"
    assert not report["added_objects"] and not report["source_membership_changes"]
