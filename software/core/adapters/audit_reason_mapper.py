"""Deterministic reference audit semantics; membership outranks display layers."""
from dataclasses import dataclass
import re

from domain.enums import CandidateDisposition as D, FilterReason as F


def _text(row):
    return "_".join(re.sub(r"[^A-Z0-9]+", "_", str(row.get(key, "")).upper())
                    for key in ("decision_reason", "reason_for_visibility", "reason",
                                "primary_visibility_layer", "classification", "execution_disposition"))


def _has(text, *patterns):
    return any(re.search(r"(?:^|_)" + re.escape(pattern) + r"(?:_|$)", text) for pattern in patterns)


def _manual_rejected(row):
    # Algorithm classification/reason alone is never evidence of human rejection.
    return str(row.get("human_rejected", "")).lower() in ("true", "1", "yes") or (
        str(row.get("review_source", "")).upper() in ("HUMAN", "USER") and
        str(row.get("review_status", "")).upper() in ("FALSE_POSITIVE", "REJECTED", "USER_REJECTED"))


def reason_category(row):
    text = _text(row)
    if _manual_rejected(row):
        return "USER_REJECTED"
    if _has(text, "MERGED", "DUPLICATE", "ASSOCIATED_INTO_OTHER_DEFECT"):
        return "MERGED_OR_DUPLICATE"
    if _has(text, "OUTSIDE_WORK", "NONWORK", "OUTSIDE_ROI"):
        return "OUTSIDE_WORK_REGION"
    if _has(text, "RAW_GATE_REJECT", "RAW_CONTRAST_FAIL", "STABILITY_FAIL", "SAFETY_REJECT", "SAFETY_GATE_REJECTED"):
        return "SAFETY_GATE_REJECTED"
    # Explicit rejection only: SMALL, MICRO and area values are not filter decisions.
    if _has(text, "AREA_TOO_SMALL", "SIZE_FILTER", "MIN_AREA", "GEOMETRY_REJECT", "SIZE_OR_GEOMETRY_FILTER"):
        return "SIZE_OR_GEOMETRY_FILTER"
    if not _has(text, "NOT_PROVEN_NOISE", "NO_DELETE", "NOISE_REVIEW") and _has(
            text, "BACKGROUND", "NOISE", "LOCAL_NOISE", "LOW_LOCAL_CONTRAST", "NOISE_REJECT"):
        return "BACKGROUND_NOISE"
    if _has(text, "LOW_EVIDENCE", "INSUFFICIENT_EVIDENCE", "UNCERTAIN_BUT_REJECTED", "WEAK_RESPONSE", "EVIDENCE_NOT_SUFFICIENT"):
        return "LOW_EVIDENCE"
    return "OTHER"


def map_filter_reason(row):
    """Use frozen schema 1.0; known unsupported subcategories remain in extensions."""
    category = reason_category(row)
    return F(category) if category in F._value2member_map_ else F.OTHER


@dataclass(frozen=True)
class AuditDecision:
    disposition: D
    filter_reason: F | None
    merged_into: str | None
    extensions: dict


def map_candidate_decision(row, *, target=None, contributor_count=0,
                           historical_only=False, known_final_ids=()):
    """Only final membership or an explicit valid target can declare a merge."""
    text = _text(row)
    category = reason_category(row)
    original = {key: row.get(key, "") for key in (
        "decision_reason", "reason_for_visibility", "reason", "stage",
        "primary_visibility_layer", "classification", "execution_disposition",
        "human_rejected", "review_source", "review_status", "merged_into")}
    extensions = {"reference_reason_category": category, "reference_fields": original}
    # Preserve the established historical-only semantics and human conclusions.
    if historical_only:
        disposition, reason, merged = (D.RETAINED if target else D.REVIEW), None, (
            target if target and contributor_count > 1 else None)
        basis = "HISTORICAL_ONLY_NOT_RECOMPUTED"
    elif target:
        disposition = D.MERGED if contributor_count > 1 else D.RETAINED
        reason, merged, basis = None, (target if disposition == D.MERGED else None), "FINAL_MEMBERSHIP"
    elif _manual_rejected(row):
        disposition, reason, merged, basis = D.FILTERED, F.USER_REJECTED, None, "EXPLICIT_HUMAN_REJECTION"
    elif category == "MERGED_OR_DUPLICATE":
        destination = row.get("merged_into")
        if destination and destination in known_final_ids:
            disposition, reason, merged, basis = D.MERGED, None, destination, "EXPLICIT_VALID_MERGE_TARGET"
        else:
            disposition, reason, merged, basis = D.REVIEW, None, None, "MERGE_TARGET_UNRESOLVED"
    elif _has(text, "REVIEW", "PENDING", "PROVISIONAL", "NO_DELETE", "NOT_PROVEN_NOISE", "UNASSESSED", "UNRELIABLE"):
        disposition, reason, merged, basis = D.REVIEW, None, None, "EXPLICIT_REVIEW_OR_UNDELETED"
    elif category not in ("OTHER", "MERGED_OR_DUPLICATE"):
        disposition, reason, merged, basis = D.FILTERED, map_filter_reason(row), None, "EXPLICIT_ALGORITHM_REASON"
    elif _has(text, "FILTERED", "REJECTED", "REJECT", "REMOVED"):
        disposition, reason, merged, basis = D.FILTERED, F.OTHER, None, "EXPLICIT_UNCLASSIFIED_REJECTION"
    else:
        disposition, reason, merged, basis = D.REVIEW, None, None, "NO_PROVEN_FILTER_DECISION"
    extensions["disposition_basis"] = basis
    return AuditDecision(disposition, reason, merged, extensions)
