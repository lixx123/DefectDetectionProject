"""Repository records, deliberately outside the domain wire schema."""
from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class ResultSummary:
    result_id: str
    task_id: str
    saved_at: str
    sample_id: str | None
    file_name: str
    source_sha256: str | None
    final_mode: str
    fallback_used: bool
    defect_count: int
    total_area_px: float | None
    algorithm_version: str | None
    config_name: str | None
    config_version: str | None


@dataclass
class VerificationReport:
    status: str = "FAIL"
    result_json_valid: bool = False
    validate_final: bool = False
    manifest_valid: bool = False
    missing_files: list = field(default_factory=list)
    hash_mismatches: list = field(default_factory=list)
    unsafe_paths: list = field(default_factory=list)
    unexpected_files: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    missing_logs: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self): return asdict(self)


@dataclass(frozen=True)
class SaveRecord:
    summary: ResultSummary
    result_dir: str
    index_status: str = "PASS"
    warnings: tuple = ()

    @property
    def result_id(self): return self.summary.result_id


@dataclass
class RebuildReport:
    indexed_results: list = field(default_factory=list)
    skipped_corrupt_results: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    status: str = "PASS"


@dataclass(frozen=True)
class ExportRecord:
    path: str
    sha256: str
    bytes: int
    crc_status: str = "PASS"
