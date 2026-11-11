from dataclasses import dataclass, field
from .common import Record, ArtifactReference
from .enums import ExecutionStatus


@dataclass(kw_only=True)
class ImageInfo(Record):
    file_name: str | None = None
    image_reference: ArtifactReference | None = None
    sha256: str | None = None
    width_px: int | None = None
    height_px: int | None = None
    container_bits: int | None = None
    effective_bits: int | None = None
    byte_order: str | None = None
    input_format: str | None = None
    sample_id: str | None = None


@dataclass(kw_only=True)
class InspectionTask(Record):
    task_id: str
    created_at: str | None = None
    status: ExecutionStatus = ExecutionStatus.NOT_STARTED
    inputs: list[ImageInfo] = field(default_factory=list)
    result_ids: list[str] = field(default_factory=list)
