"""Merge fresh and archived ledgers without relabelling archives as fresh work."""
from pathlib import Path
from collections import Counter
from domain import AuditInfo, CandidateAuditRecord, DefectGeometry
from domain.common import BoundingBox
from core.errors import MappingError
from core.runtime.resources import portable_reference
from .tabular import read_rows, first, truth, sources
from .audit_reason_mapper import map_candidate_decision


def map_audit(engine_dir, ownership, resources, *, reference_root=None):
    engine_dir = Path(engine_dir)
    fresh_path = engine_dir / "ALL_SOURCE_DISPOSITIONS.csv"
    legacy_path = engine_dir / "ALL_ORIGINAL_J5_AND_B_SOURCE_DISPOSITIONS_NO_DROP.csv"
    fresh = read_rows(fresh_path if fresh_path.exists() else legacy_path)
    archive_path = engine_dir / "ALL_HISTORICAL_SOURCE_DISPOSITIONS_NO_DROP.csv"
    archive = read_rows(archive_path, required=False)
    if not archive:
        archive = read_rows(engine_dir / "HISTORICAL_ALL_SOURCE_LINEAGE_UNCHANGED.csv", required=False)
    # Old final exports kept geometry in a separate original source ledger.
    if not archive and fresh and fresh[0].get("original_source_ledger") and reference_root:
        ledger = Path(fresh[0]["original_source_ledger"]).resolve()
        if not ledger.is_relative_to(Path(reference_root).resolve()):
            raise MappingError("historical source ledger outside reference root")
        archive = read_rows(ledger)
    fresh_ids = [r["candidate_source_uid"] for r in fresh]
    archive_ids = [r["candidate_source_uid"] for r in archive]
    if len(set(fresh_ids)) != len(fresh_ids) or len(set(archive_ids)) != len(archive_ids):
        raise MappingError("duplicate original candidate source UID")
    rows = {r["candidate_source_uid"]: dict(r) for r in archive}
    for row in fresh:
        uid = row["candidate_source_uid"]
        combined = rows.setdefault(uid, {})
        combined.update({k: v for k, v in row.items() if v != ""})
    missing = set(ownership) - set(rows)
    if missing:
        raise MappingError(f"Defect -> Candidate reverse lineage missing {len(missing)} sources")
    membership_path = engine_dir / "final_group_membership.csv"
    if membership_path.is_file():
        membership = {r["source_uid"]: r["final_ID"] for r in read_rows(membership_path)}
        if membership != ownership:
            raise MappingError("final group membership differs from final NPZ sources")
    j5_membership_path = engine_dir / "upstream_J5/fresh/global_object_membership.csv"
    if j5_membership_path.is_file():
        groups = {r["global_defect_id"] for r in read_rows(j5_membership_path)}
        if any(r.get("source_local_id") not in groups for r in fresh if r.get("stage") == "J5"):
            raise MappingError("fresh J5 source missing J4 membership")
    recovery_events = []
    for row in read_rows(engine_dir / "RAW_recovery_gate_audit.csv", required=False):
        source_ids = sources(row.get("source_uids"))
        if not source_ids <= set(rows):
            raise MappingError("RAW recovery refers to missing original source candidates")
        recovery_events.append({"event": "RAW_RECOVERY", "candidate_ids": sorted(source_ids),
            "final_defect_ids": sorted({ownership[u] for u in source_ids if u in ownership}),
            "accepted": truth(row.get("accepted")), "reference_record": row})
    records = []
    fresh_set = set(fresh_ids)
    contributor_counts = Counter(ownership.values())
    known_final_ids = set(ownership.values())
    for uid, row in rows.items():
        target = ownership.get(uid)
        declared = first(row, "final_ID", "final_defect_ID", "current_final_ID")
        if declared and declared != target:
            raise MappingError("source ledger final membership disagrees with actual final NPZ")
        if row.get("original_source_preserved") and not truth(row["original_source_preserved"]):
            raise MappingError("engine reports removed original source pixels")
        archived_only = uid not in fresh_set
        reason = first(row, "decision_reason", "reason_for_visibility", "reason")
        decision = map_candidate_decision(row, target=target,
            contributor_count=contributor_counts.get(target, 0),
            historical_only=archived_only, known_final_ids=known_final_ids)
        geometry = None
        keys = ("source_bbox_x0", "source_bbox_y0", "source_bbox_x1_exclusive", "source_bbox_y1_exclusive")
        if all(row.get(k) != "" and row.get(k) is not None for k in keys):
            geometry = DefectGeometry(bbox=BoundingBox(*(int(float(row[k])) for k in keys)),
                area_px=float(row["source_area_px2"]) if row.get("source_area_px2") else None)
        records.append(CandidateAuditRecord(candidate_id=uid, source=first(row, "stage", default=uid.split(":")[0]),
            initial_geometry=geometry, current_stage="HISTORICAL_ARCHIVE_NOT_RESCANNED" if archived_only else "FINAL_SELECTION",
            disposition=decision.disposition, filter_reason=decision.filter_reason,
            filter_message=reason, final_defect_id=target,
            merged_into=decision.merged_into,
            extensions={"historical_only_not_recomputed": archived_only,
                        "execution_disposition": first(row, "execution_disposition"),
                        "reference_decision": reason, "not_a_human_noise_label": True,
                        **decision.extensions}))
    evidence = {}
    for name in (fresh_path.name if fresh_path.exists() else legacy_path.name,
                 "ALL_HISTORICAL_SOURCE_DISPOSITIONS_NO_DROP.csv", "RAW_recovery_gate_audit.csv",
                 "final_group_membership.csv", "association_edges.csv", "HISTORICAL_ALL_SOURCE_LINEAGE_UNCHANGED.csv",
                 "upstream_J5/fresh/global_object_membership.csv", "J5_current_to_historical_identity.csv"):
        path = engine_dir / name
        if path.is_file():
            evidence[name] = portable_reference(resources.reference(path))
    return AuditInfo(candidates=records, events=recovery_events, source_candidate_count=len(records), lineage_complete=True,
        extensions={"fresh_source_count": len(fresh), "historical_source_count": len(archive),
                    "union_source_count": len(records), "evidence": evidence})
