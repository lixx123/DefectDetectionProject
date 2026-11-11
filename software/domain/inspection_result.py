"""Schema 1.0 result contract. No engine or GUI dependencies."""
from dataclasses import dataclass, field
import math
from pathlib import Path
from uuid import uuid4
from .common import Record
from .algorithm import AlgorithmInfo
from .calibration import CalibrationInfo
from .execution import ExecutionInfo, QualityControl
from .roi import ROIInfo
from .defect import Defect
from .statistics import InspectionStatistics
from .audit import AuditInfo
from .task import ImageInfo
from .intermediate import IntermediateResults
from .migrations import CURRENT_SCHEMA_VERSION, DEFAULT_MIGRATIONS
from .enums import PipelineMode, QAStatus, ExecutionStatus, GeometryStatus, FallbackReason


class FinalValidationError(ValueError):
    """Result is a valid draft, but is not ready for official save/publication."""


@dataclass(kw_only=True)
class InspectionResult(Record):
    task_id: str
    result_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: str = CURRENT_SCHEMA_VERSION
    input_info: ImageInfo = field(default_factory=ImageInfo)
    algorithm_info: AlgorithmInfo = field(default_factory=AlgorithmInfo)
    calibration_info: CalibrationInfo = field(default_factory=CalibrationInfo)
    execution_info: ExecutionInfo = field(default_factory=ExecutionInfo)
    roi_info: ROIInfo = field(default_factory=ROIInfo)
    defects: list[Defect] = field(default_factory=list)
    statistics: InspectionStatistics = field(default_factory=InspectionStatistics)
    intermediate_results: IntermediateResults = field(default_factory=IntermediateResults)
    quality_control: QualityControl = field(default_factory=QualityControl)
    audit_log: AuditInfo = field(default_factory=AuditInfo)

    def __post_init__(self):
        if self.schema_version != CURRENT_SCHEMA_VERSION:
            raise ValueError("migrate unsupported schema before constructing InspectionResult")
        if not self.task_id.strip() or not self.result_id.strip():
            raise ValueError("task_id and result_id are required")
        ids = [d.identity.defect_id for d in self.defects]
        if len(ids) != len(set(ids)):
            raise ValueError("defect IDs must be unique within a result")
        candidates = self.audit_log.candidates
        keys = [(r.source, r.candidate_id) for r in candidates]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate source/candidate audit record")
        if self.audit_log.lineage_complete:
            if self.audit_log.source_candidate_count != len(candidates):
                raise ValueError("complete lineage requires one record per original source candidate")
            for row in candidates:
                if row.final_defect_id is not None and row.final_defect_id not in ids:
                    raise ValueError("audit final_defect_id is not in result defects")

    def validate_final(self) -> None:
        """Pure, non-mutating final gate; file existence QA belongs to the application.

        Execution QA decides which attempt can be adopted. Result QC attests
        output completeness. This gate independently checks model consistency.
        It never runs an algorithm, marks QC PASS, or fills missing measurements.
        """
        def require(condition: bool, message: str):
            if not condition:
                raise FinalValidationError(message)

        # Re-run nested type/constructor invariants after any in-place edits.
        try:
            self.to_dict()
        except (ValueError, TypeError) as exc:
            raise FinalValidationError(f"model consistency: {exc}") from exc

        require(self.statistics.total_defects == len(self.defects),
                "statistics.total_defects must equal len(defects)")
        ids = [d.identity.defect_id for d in self.defects]
        require(len(ids) == len(set(ids)), "defect IDs must be unique")

        execution = self.execution_info
        require(execution.status == ExecutionStatus.SUCCEEDED,
                "official final result requires a SUCCEEDED execution")
        require(execution.final_mode is not None and execution.qa_status == QAStatus.PASS,
                "adopted execution mode and Execution QA PASS are required")
        final = execution.final_attempt
        require(final is not None, "a successful QA-PASS final attempt is required")
        require(final is execution.attempts[-1], "adopted final attempt must be the last attempt")
        require(final.mode == execution.final_mode and final.status == ExecutionStatus.SUCCEEDED
                and final.qa_status == QAStatus.PASS, "final attempt must match adopted mode and pass")

        if execution.requested_mode == PipelineMode.AUTO:
            modes = [a.mode for a in execution.attempts]
            if execution.final_mode == PipelineMode.ROI_BH:
                require(not execution.fallback_used and modes == [PipelineMode.ROI_BH],
                        "AUTO ROI_BH success requires exactly one ROI_BH attempt and no fallback")
                require(final.plan.roi_geometry_status == GeometryStatus.VALID
                        and final.plan.band_geometry_status == GeometryStatus.VALID,
                        "AUTO ROI_BH final plan requires VALID ROI and Band geometry")
            elif execution.final_mode == PipelineMode.FULL:
                require(execution.fallback_used and execution.fallback_reason is not None,
                        "AUTO FULL requires an explicit fallback reason")
                require(modes == [PipelineMode.ROI_BH, PipelineMode.FULL],
                        "AUTO fallback order must be exactly ROI_BH, FULL")
                first = execution.attempts[0]
                require(not (first.status == ExecutionStatus.SUCCEEDED and first.qa_status == QAStatus.PASS),
                        "a successful QA-PASS ROI_BH attempt must not trigger fallback")
                require(first.reason == execution.fallback_reason,
                        "first attempt reason must equal fallback_reason")

        if execution.fallback_reason == FallbackReason.BAND_GEOMETRY_INVALID:
            first = execution.attempts[0]
            require(first.mode == PipelineMode.ROI_BH
                    and first.plan.band_geometry_status in (GeometryStatus.INVALID, GeometryStatus.FAILED),
                    "BAND_GEOMETRY_INVALID requires INVALID or FAILED first Band geometry")
            require(self.roi_info.status in (GeometryStatus.INVALID, GeometryStatus.FAILED),
                    "failed Band geometry must remain INVALID/FAILED in ROIInfo for audit")
            require(not self.roi_info.band_list or any(not band.valid for band in self.roi_info.band_list),
                    "preserved failed Band geometry must identify invalid Bands")

        if execution.final_mode == PipelineMode.ROI_BH:
            require(self.roi_info.status == GeometryStatus.VALID,
                    "adopting ROI_BH requires VALID ROIInfo")
            require(bool(self.roi_info.band_list), "adopting ROI_BH requires production Bands")
            require(all(band.valid for band in self.roi_info.band_list),
                    "all production Bands must be valid when adopting ROI_BH")

        require(self.audit_log.lineage_complete, "official final result requires complete source lineage")
        require(self.audit_log.source_candidate_count == len(self.audit_log.candidates),
                "source count must equal candidate audit records")
        require(all(row.final_defect_id is None or row.final_defect_id in ids
                    for row in self.audit_log.candidates), "audit final_defect_id must exist")

        # Defects are disjoint physical objects; totals are sums, never bbox areas.
        # Tolerances apply to stored numeric sums, not algorithm segmentation QA.
        for area_field, total_field in (("area_px", "total_defect_area_px"),
                                        ("area_um2", "total_defect_area_um2")):
            areas = [getattr(d.geometry, area_field) for d in self.defects]
            total = getattr(self.statistics, total_field)
            if total is not None and all(value is not None for value in areas):
                require(math.isclose(total, math.fsum(areas), rel_tol=1e-9, abs_tol=1e-6),
                        f"statistics.{total_field} must equal the sum of defects.{area_field}")

        require(self.quality_control.status == QAStatus.PASS,
                "Result QC PASS is required independently of Execution QA")
        # No return value, mutations, automatic sums, or resource IO on success.

    def to_dict(self):
        from .serialization import to_dict
        return to_dict(self)

    @classmethod
    def from_dict(cls, payload, *, migrations=DEFAULT_MIGRATIONS):
        from .serialization import from_dict
        return from_dict(cls, migrations.migrate(payload))

    def to_json(self) -> str:
        from .serialization import dumps
        return dumps(self)

    @classmethod
    def from_json(cls, text: str, *, migrations=DEFAULT_MIGRATIONS):
        from .serialization import parse_json
        return cls.from_dict(parse_json(text), migrations=migrations)

    def save_json(self, path: str | Path, *, overwrite: bool = False):
        """Small codec convenience API, not a repository. Do not overwrite history by default."""
        text = self.to_json()
        with Path(path).open("w" if overwrite else "x", encoding="utf-8", newline="\n") as stream:
            stream.write(text + "\n")

    @classmethod
    def load_json(cls, path: str | Path, *, migrations=DEFAULT_MIGRATIONS):
        return cls.from_json(Path(path).read_text(encoding="utf-8-sig"), migrations=migrations)
