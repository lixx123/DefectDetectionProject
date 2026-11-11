from dataclasses import dataclass, field
from .common import Record
from .defect import DefectGeometry
from .enums import CandidateDisposition, FilterReason


@dataclass(kw_only=True)
class CandidateAuditRecord(Record):
    candidate_id: str
    source: str
    initial_geometry: DefectGeometry | None = None
    current_stage: str | None = None
    disposition: CandidateDisposition = CandidateDisposition.PENDING
    filter_reason: FilterReason | None = None
    filter_message: str | None = None
    merged_into: str | None = None
    final_defect_id: str | None = None

    def __post_init__(self):
        if not self.candidate_id.strip() or not self.source.strip():
            raise ValueError("candidate_id and source are required")
        if self.disposition == CandidateDisposition.FILTERED and self.filter_reason is None:
            raise ValueError("filtered candidate must have a reason")
        if self.disposition == CandidateDisposition.MERGED and not self.merged_into:
            raise ValueError("merged candidate must have a target")


@dataclass(kw_only=True)
class AuditInfo(Record):
    candidates: list[CandidateAuditRecord] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    source_candidate_count: int | None = None
    lineage_complete: bool = False
