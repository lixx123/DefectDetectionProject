"""Grouped defect measurements; absent measurements remain None, never zero-filled."""
from dataclasses import dataclass, field, replace
from .common import Record, BoundingBox, Point, ArtifactReference, nonnegative
from .calibration import CalibrationInfo
from .enums import SizeGrade, SeverityGrade
from .review import ReviewInfo


@dataclass(kw_only=True)
class DefectIdentity(Record):
    defect_id: str

    def __post_init__(self):
        if not self.defect_id.strip():
            raise ValueError("defect_id cannot be blank")


@dataclass(kw_only=True)
class DefectGeometry(Record):
    bbox: BoundingBox | None = None
    center: Point | None = None
    area_px: float | None = None
    area_um2: float | None = None
    length_px: float | None = None
    length_um: float | None = None
    width_px: float | None = None
    width_um: float | None = None
    equivalent_diameter_px: float | None = None
    equivalent_diameter_um: float | None = None
    contour_reference: ArtifactReference | None = None
    mask_reference: ArtifactReference | None = None
    area_method: str | None = None
    length_method: str | None = None

    def __post_init__(self):
        for name in ("area_px", "area_um2", "length_px", "length_um", "width_px", "width_um",
                     "equivalent_diameter_px", "equivalent_diameter_um"):
            nonnegative(getattr(self, name), name)

    def with_calibration(self, calibration: CalibrationInfo) -> "DefectGeometry":
        updated = replace(self, area_um2=calibration.area_um2(self.area_px),
                          length_um=calibration.linear_um(self.length_px),
                          width_um=calibration.linear_um(self.width_px),
                          equivalent_diameter_um=calibration.linear_um(self.equivalent_diameter_px))
        updated._unknown_fields = dict(self._unknown_fields)
        return updated


@dataclass(kw_only=True)
class Morphology(Record):
    aspect_ratio: float | None = None
    circularity: float | None = None
    elongation: float | None = None
    orientation_deg: float | None = None
    solidity: float | None = None
    eccentricity: float | None = None
    skeleton_length_px: float | None = None


@dataclass(kw_only=True)
class Photometry(Record):
    mean_gray_dn: float | None = None
    min_gray_dn: float | None = None
    max_gray_dn: float | None = None
    background_mean_dn: float | None = None
    background_std_dn: float | None = None
    gray_difference_dn: float | None = None
    gray_ratio: float | None = None
    local_contrast: float | None = None
    blackhat_response: float | None = None


@dataclass(kw_only=True)
class Classification(Record):
    defect_type: str | None = None
    defect_subtype: str | None = None
    size_grade: SizeGrade = SizeGrade.UNKNOWN
    severity_grade: SeverityGrade = SeverityGrade.UNKNOWN
    confidence: float | None = None
    classification_method: str | None = None

    def __post_init__(self):
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(kw_only=True)
class DefectLocation(Record):
    image_x: float | None = None
    image_y: float | None = None
    roi_id: str | None = None
    band_id: str | None = None
    physical_x: float | None = None
    physical_y: float | None = None
    physical_coordinate_unit: str = "um"
    sensor_x: float | None = None
    sensor_y: float | None = None


@dataclass(kw_only=True)
class DetectionInfo(Record):
    source_channels: list[str] = field(default_factory=list)
    candidate_ids: list[str] = field(default_factory=list)
    detection_stage: str | None = None
    merge_history: list[dict] = field(default_factory=list)
    algorithm_version: str | None = None


@dataclass(kw_only=True)
class Defect(Record):
    identity: DefectIdentity
    geometry: DefectGeometry = field(default_factory=DefectGeometry)
    morphology: Morphology = field(default_factory=Morphology)
    photometry: Photometry = field(default_factory=Photometry)
    classification: Classification = field(default_factory=Classification)
    location: DefectLocation = field(default_factory=DefectLocation)
    detection: DetectionInfo = field(default_factory=DetectionInfo)
    review: ReviewInfo = field(default_factory=ReviewInfo)
