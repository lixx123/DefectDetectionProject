"""ROI geometry is produced by the engine, never recomputed by UI."""
from dataclasses import dataclass, field
from .common import Record, BoundingBox, ArtifactReference, nonnegative
from .enums import GeometryStatus, ReviewStatus


@dataclass(kw_only=True)
class RegionInfo(Record):
    region_id: str
    bbox: BoundingBox | None = None
    pixel_count: int | None = None
    mask_reference: ArtifactReference | None = None
    contour_reference: ArtifactReference | None = None

    def __post_init__(self):
        nonnegative(self.pixel_count, "pixel_count")


@dataclass(kw_only=True)
class BandInfo(Record):
    band_id: str
    name: str | None = None
    bbox: BoundingBox | None = None
    contour_reference: ArtifactReference | None = None
    mask_reference: ArtifactReference | None = None
    mean_gray_dn: float | None = None
    min_gray_dn: float | None = None
    max_gray_dn: float | None = None
    pixel_count: int | None = None
    valid: bool = False
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED

    def __post_init__(self):
        if not self.band_id.strip():
            raise ValueError("band_id cannot be blank")
        nonnegative(self.pixel_count, "pixel_count")


@dataclass(kw_only=True)
class ROIInfo(Record):
    status: GeometryStatus = GeometryStatus.NOT_EVALUATED
    work_region: RegionInfo | None = None
    nonwork_region: RegionInfo | None = None
    review_region: RegionInfo | None = None
    band_count: int = 0
    band_list: list[BandInfo] = field(default_factory=list)
    mask_references: dict[str, ArtifactReference] = field(default_factory=dict)
    geometry_source: str | None = None

    def __post_init__(self):
        if type(self.band_count) is not int or self.band_count != len(self.band_list):
            raise ValueError("band_count must equal len(band_list)")
        ids = [b.band_id for b in self.band_list]
        if len(ids) != len(set(ids)):
            raise ValueError("band IDs must be unique")
