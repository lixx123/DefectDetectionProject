from dataclasses import dataclass, field
from .common import Record, ArtifactReference
from .enums import IntermediateLevel


@dataclass(kw_only=True)
class IntermediateResults(Record):
    level: IntermediateLevel = IntermediateLevel.STANDARD
    original_preview: ArtifactReference | None = None
    work_mask: ArtifactReference | None = None
    nonwork_mask: ArtifactReference | None = None
    review_mask: ArtifactReference | None = None
    band_masks: dict[str, ArtifactReference] = field(default_factory=dict)
    blackhat_preview: ArtifactReference | None = None
    candidate_preview: ArtifactReference | None = None
    final_mask: ArtifactReference | None = None
    annotated_image: ArtifactReference | None = None
