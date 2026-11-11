"""Execution evidence only: no algorithm, scheduler, or fallback runner here."""
from dataclasses import dataclass, field
from typing import ClassVar
from .common import Record, nonnegative
from .enums import PipelineMode, FallbackReason, QAStatus, ExecutionStatus, GeometryStatus


@dataclass(kw_only=True)
class QACheck(Record):
    name: str
    status: QAStatus = QAStatus.NOT_RUN
    message: str | None = None
    stage: str | None = None
    mandatory: bool = True


@dataclass(kw_only=True)
class QualityControl(Record):
    """Result QC evidence. Execution QA uses the same check value type, not this scope."""
    status: QAStatus = QAStatus.NOT_RUN
    checks: list[QACheck] = field(default_factory=list)

    def __post_init__(self):
        if self.status == QAStatus.PASS and any(c.mandatory and c.status != QAStatus.PASS for c in self.checks):
            raise ValueError("mandatory QA checks must all pass")


@dataclass(kw_only=True)
class DetectionPlanInfo(Record):
    roi_geometry_status: GeometryStatus = GeometryStatus.NOT_EVALUATED
    band_geometry_status: GeometryStatus = GeometryStatus.NOT_EVALUATED
    planned_tiles: int | None = None
    full_tiles: int | None = None
    skipped_tiles: int | None = None
    legal_source_pixels: int | None = None

    def __post_init__(self):
        for name in ("planned_tiles", "full_tiles", "skipped_tiles", "legal_source_pixels"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a nonnegative integer or None")
        if self.planned_tiles is not None and self.full_tiles is not None and self.planned_tiles > self.full_tiles:
            raise ValueError("planned_tiles cannot exceed full_tiles")
        if all(v is not None for v in (self.planned_tiles, self.full_tiles, self.skipped_tiles)):
            if self.planned_tiles + self.skipped_tiles != self.full_tiles:
                raise ValueError("planned_tiles + skipped_tiles must equal full_tiles")


@dataclass(kw_only=True)
class ExecutionAttempt(Record):
    mode: PipelineMode
    status: ExecutionStatus = ExecutionStatus.NOT_STARTED
    plan: DetectionPlanInfo = field(default_factory=DetectionPlanInfo)
    qa_status: QAStatus = QAStatus.NOT_RUN
    qa_checks: list[QACheck] = field(default_factory=list)
    reason: FallbackReason | None = None
    message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    execution_time_seconds: float | None = None

    def __post_init__(self):
        if self.mode == PipelineMode.AUTO:
            raise ValueError("attempt mode must be concrete")
        nonnegative(self.execution_time_seconds, "execution_time_seconds")
        QualityControl(status=self.qa_status, checks=self.qa_checks)


@dataclass(kw_only=True)
class ExecutionInfo(Record):
    # Removed pre-freeze draft fields must not reappear as unknown additive fields.
    _retired_wire_fields: ClassVar[frozenset[str]] = frozenset({
        "roi_geometry_status", "band_geometry_status", "planned_tiles",
        "full_tiles", "skipped_tiles", "legal_source_pixels",
    })
    requested_mode: PipelineMode = PipelineMode.AUTO
    attempted_mode: PipelineMode | None = None
    final_mode: PipelineMode | None = None
    status: ExecutionStatus = ExecutionStatus.NOT_STARTED
    fallback_used: bool = False
    fallback_reason: FallbackReason | None = None
    fallback_message: str | None = None
    qa_status: QAStatus = QAStatus.NOT_RUN
    qa_checks: list[QACheck] = field(default_factory=list)
    attempts: list[ExecutionAttempt] = field(default_factory=list)

    def __post_init__(self):
        QualityControl(status=self.qa_status, checks=self.qa_checks)
        self.validate_policy()

    @property
    def final_attempt(self) -> ExecutionAttempt | None:
        """Last successful QA-PASS attempt, only if it matches the adopted mode."""
        if self.final_mode is None:
            return None
        for attempt in reversed(self.attempts):
            if attempt.status == ExecutionStatus.SUCCEEDED and attempt.qa_status == QAStatus.PASS:
                return attempt if attempt.mode == self.final_mode else None
        return None

    @property
    def final_plan(self) -> DetectionPlanInfo | None:
        attempt = self.final_attempt
        return None if attempt is None else attempt.plan

    def validate_policy(self):
        if not isinstance(self.requested_mode, PipelineMode):
            raise ValueError("requested_mode must be a PipelineMode")
        if self.attempted_mode is not None and not isinstance(self.attempted_mode, PipelineMode):
            raise ValueError("attempted_mode must be a PipelineMode")
        if self.final_mode is not None and not isinstance(self.final_mode, PipelineMode):
            raise ValueError("final_mode must be a PipelineMode")
        if self.attempted_mode == PipelineMode.AUTO or self.final_mode == PipelineMode.AUTO:
            raise ValueError("AUTO is a request, never an actual attempt/final mode")
        if self.final_mode is not None and self.status != ExecutionStatus.SUCCEEDED:
            raise ValueError("only a successful execution may have an adopted final_mode")
        if self.status == ExecutionStatus.SUCCEEDED and (self.final_mode is None or self.qa_status != QAStatus.PASS):
            raise ValueError("successful execution needs an adopted mode and passing QA")
        if self.status == ExecutionStatus.SUCCEEDED and self.attempted_mode is None:
            raise ValueError("successful execution must record the initial attempted_mode")
        if self.fallback_used:
            if (self.requested_mode != PipelineMode.AUTO or self.attempted_mode != PipelineMode.ROI_BH
                    or not isinstance(self.fallback_reason, FallbackReason)):
                raise ValueError("fallback requires AUTO, initial ROI_BH, and a typed reason")
            if self.final_mode not in (None, PipelineMode.FULL):
                raise ValueError("AUTO falls directly back to FULL")
        elif self.fallback_reason is not None:
            raise ValueError("fallback_reason requires fallback_used")
        if self.requested_mode == PipelineMode.AUTO:
            if self.attempted_mode not in (None, PipelineMode.ROI_BH):
                raise ValueError("AUTO starts with ROI_BH")
            if self.final_mode not in (None, PipelineMode.ROI_BH, PipelineMode.FULL):
                raise ValueError("ROI_J4 and LEGACY_REPLAY are debug/replay only")
            if self.final_mode == PipelineMode.FULL and not self.fallback_used:
                raise ValueError("AUTO adopting FULL must record fallback")
            modes = [a.mode for a in self.attempts]
            if modes and modes not in ([PipelineMode.ROI_BH], [PipelineMode.ROI_BH, PipelineMode.FULL]):
                raise ValueError("AUTO attempt history must be ROI_BH then optionally FULL")
            if len(modes) == 2 and not self.fallback_used:
                raise ValueError("a FULL attempt must record fallback")
        elif self.fallback_used:
            raise ValueError("explicit debug requests do not run AUTO fallback")
        elif self.final_mode is not None and self.final_mode != self.requested_mode:
            raise ValueError("debug/replay final mode must equal requested mode")
        if self.requested_mode != PipelineMode.AUTO:
            if self.attempted_mode not in (None, self.requested_mode):
                raise ValueError("explicit mode must record the requested initial attempt")
            if any(a.mode != self.requested_mode for a in self.attempts):
                raise ValueError("explicit modes cannot silently execute a different mode")
        if self.attempts:
            if self.attempted_mode != self.attempts[0].mode:
                raise ValueError("attempted_mode identifies the initial attempt")
            last = self.attempts[-1]
            if self.final_mode is not None and (last.mode != self.final_mode
                    or last.status != ExecutionStatus.SUCCEEDED or last.qa_status != QAStatus.PASS):
                raise ValueError("adopted mode requires a successful passing final attempt")
