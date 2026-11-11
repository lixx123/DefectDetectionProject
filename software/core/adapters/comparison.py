"""Object, pixel, and source differences; no vague count-only acceptance."""
from pathlib import Path
import numpy as np
from .roi_mapper import read_png


def _mask(defect, directory):
    with np.load(Path(directory) / defect.geometry.mask_reference.path, allow_pickle=False) as data:
        return data["mask"] > 0, tuple(int(v) for v in data["global_RAW_bbox_xyxy_exclusive"])


def compare_results(reference, current, reference_dir, current_dir, *, length_tolerance=1e-6):
    before = {d.identity.defect_id: d for d in reference.defects}
    after = {d.identity.defect_id: d for d in current.defects}
    # Sequential IDs are run-local, not physical identities across pipelines.
    # First match exact source sets; then exact global masks can identify an
    # unchanged object whose source membership itself changed.
    remaining_before, remaining_after = set(before), set(after)
    pairs = []
    for aid in sorted(before):
        signature = set(before[aid].detection.candidate_ids)
        matches = [bid for bid in remaining_after if signature and signature == set(after[bid].detection.candidate_ids)]
        if len(matches) == 1:
            bid = matches[0]
            pairs.append((aid, bid))
            remaining_before.remove(aid)
            remaining_after.remove(bid)
    for aid in sorted(remaining_before.copy()):
        am, ab = _mask(before[aid], reference_dir)
        matches = []
        for bid in remaining_after:
            bm, bb = _mask(after[bid], current_dir)
            if ab == bb and np.array_equal(am, bm):
                matches.append(bid)
        if len(matches) == 1:
            bid = matches[0]
            pairs.append((aid, bid))
            remaining_before.remove(aid)
            remaining_after.remove(bid)
    report = {"matching_basis": "EXACT_SOURCE_SET_THEN_EXACT_GLOBAL_MASK",
        "added_objects": sorted(remaining_after), "disappeared_objects": sorted(remaining_before),
        "position_changes": [], "area_changes": [], "Feret_changes": [], "grade_changes": [],
        "source_membership_changes": [], "object_mask_changes": [], "id_changes": []}
    for key, current_id in sorted(pairs):
        a, b = before[key], after[current_id]
        if key != current_id:
            report["id_changes"].append({"before_id": key, "after_id": current_id,
                "source_uids": a.detection.candidate_ids, "not_a_physical_measurement_change": True})
        if a.geometry.bbox != b.geometry.bbox:
            report["position_changes"].append({"id": key, "before": vars(a.geometry.bbox), "after": vars(b.geometry.bbox)})
        if a.geometry.area_px != b.geometry.area_px:
            report["area_changes"].append({"id": key, "before": a.geometry.area_px, "after": b.geometry.area_px})
        if abs(a.geometry.length_px - b.geometry.length_px) > length_tolerance:
            report["Feret_changes"].append({"id": key, "before": a.geometry.length_px, "after": b.geometry.length_px})
        if a.classification.size_grade != b.classification.size_grade:
            report["grade_changes"].append({"id": key, "before": a.classification.size_grade.value, "after": b.classification.size_grade.value})
        if set(a.detection.candidate_ids) != set(b.detection.candidate_ids):
            report["source_membership_changes"].append({"id": key, "before": a.detection.candidate_ids, "after": b.detection.candidate_ids})
        am, ab = _mask(a, reference_dir)
        bm, bb = _mask(b, current_dir)
        if ab != bb or not np.array_equal(am, bm):
            report["object_mask_changes"].append(key)
    oldmask = read_png(Path(reference_dir) / reference.intermediate_results.final_mask.path)
    newmask = read_png(Path(current_dir) / current.intermediate_results.final_mask.path)
    report["final_binary_diff_pixels"] = int(np.count_nonzero(oldmask != newmask)) if oldmask.shape == newmask.shape else None
    oldsources = {r.candidate_id for r in reference.audit_log.candidates}
    newsources = {r.candidate_id for r in current.audit_log.candidates}
    report["missing_reference_candidate_uids"] = sorted(oldsources - newsources)
    report["additional_current_candidate_uids"] = sorted(newsources - oldsources)
    report["candidate_archive_semantics"] = "ROI may retain historical sources without recomputing them; extra boundary partial sources are explicit"
    changes = [report[k] for k in ("added_objects", "disappeared_objects", "position_changes", "area_changes",
        "Feret_changes", "grade_changes", "source_membership_changes", "object_mask_changes", "missing_reference_candidate_uids")]
    report["status"] = "PASS" if not any(changes) and report["final_binary_diff_pixels"] == 0 else "FAIL"
    return report
