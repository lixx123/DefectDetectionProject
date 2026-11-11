"""K8I lossless candidate lineage and visibility policy. Never infer truth.

Every B candidate and every frozen J5 candidate must have an evidence layer.
Suggested hide means REVIEW layer, not deletion. K8E group association is
display provenance, not cross-channel source identity/production acceptance.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import math

LAYERS={
 "J5_WORK_MEDLARGE":"01_main_1to4",
 "J5_WORK_SMALL":"03_small_source_1to4",
 "J5_OUTSIDE_WORK":"06_J5_outside_work_reference_1to8",
 "B_FIXED_H_REFERENCE":"05_fixed_H_B_candidates_reference_1to8",
 "B_NOVEL_MICRO":"04_micro_hide_suggestions_NOT_deleted_1to4",
 "B_NOVEL_SMALL":"03_small_source_1to4",
 "B_NOVEL_MEDLARGE":"01_main_1to4",
 "B_K8E_GROUP_PENDING":"02_all_K8E_group_review_1to4",
 "B_K8E_GROUP_CONFIRMED":"01_main_1to4",
 "B_K8E_MULTIGROUP_CONFLICT":"02_all_K8E_group_review_1to4",
}
ROUTING_CODES=set(LAYERS)

def parse_ids(value):
    """B labels in pandas CSV may be strings, ints or numeric floats."""
    if value is None:return ()
    if isinstance(value,float) and math.isnan(value):return ()
    text=str(value).strip()
    if not text or text.lower() in ("nan","none"):return ()
    return tuple(sorted({int(float(piece)) for piece in text.split(";")
                         if piece.strip() and piece.strip().lower()!="nan"}))

def b_layer(classification,novel,grade,groups,approved_ids):
    """Return one guaranteed visible category, not a judgement of truth."""
    group_names=tuple(sorted(set(groups)))
    if group_names:
        if len(group_names)>1:return "B_K8E_MULTIGROUP_CONFLICT"
        if group_names[0] in approved_ids:return "B_K8E_GROUP_CONFIRMED"
        return "B_K8E_GROUP_PENDING"
    if not novel or classification=="EXISTING_FIXED_H":return "B_FIXED_H_REFERENCE"
    if classification=="MICRO_HIDE_SUGGESTION":return "B_NOVEL_MICRO"
    if grade in ("MEDIUM","LARGE"):return "B_NOVEL_MEDLARGE"
    return "B_NOVEL_SMALL"

def j5_layer(region_code,grade):
    if int(region_code)!=2:return "J5_OUTSIDE_WORK"
    return "J5_WORK_SMALL" if grade=="SMALL" else "J5_WORK_MEDLARGE"

def source_key(stage,frame,band,label):
    if stage=="J5":return f"J5:F{int(frame)}:{str(label)}"
    if stage=="K8B":return f"B:F{int(frame)}:B{int(band):02d}:C{int(label):07d}"
    raise ValueError("unknown detection stage")

def validate_lineage(rows):
    if not rows:raise AssertionError("no candidates")
    seen=set()
    for obj in rows:
        uid=obj["candidate_source_uid"]
        if uid in seen:raise AssertionError(f"duplicate {uid}")
        seen.add(uid)
        key=obj["primary_visibility_layer"]
        if key not in ROUTING_CODES:raise AssertionError(f"unrouted candidate {uid}")
        if obj["size_grade"] not in ("SMALL","MEDIUM","LARGE"):
            raise AssertionError(f"invalid grade {uid}")
        if obj["source_area_px2"]<1:raise AssertionError(f"missing source area {uid}")
        if not obj["original_source_pixels_preserved"]:
            raise AssertionError(f"source pixels modified {uid}")
        if obj["is_user_confirmed"] and obj["stage"]=="J5":
            raise AssertionError("Frozen J5 has no user confirmed truth in this trial")
    return {"total_source_candidates":len(rows),"unique_source_ids":len(seen),
            "unrouted_source_candidates":0,"source_pixels_modified":0}

def audit_layer_counts(rows):
    d={k:0 for k in ROUTING_CODES}
    for x in rows:d[x["primary_visibility_layer"]]+=1
    if sum(d.values())!=len(rows):raise AssertionError("loss from routing")
    return dict(sorted(d.items()))
