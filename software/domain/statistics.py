"""Stored statistics, not recomputed from UI or silently on JSON load."""
from dataclasses import dataclass, field
from .common import Record, nonnegative


@dataclass(kw_only=True)
class InspectionStatistics(Record):
    total_defects: int = 0
    count_by_type: dict[str, int] = field(default_factory=dict)
    count_by_size_grade: dict[str, int] = field(default_factory=dict)
    count_by_severity_grade: dict[str, int] = field(default_factory=dict)
    count_by_band: dict[str, int] = field(default_factory=dict)
    count_by_roi: dict[str, int] = field(default_factory=dict)
    total_defect_area_px: float | None = None
    total_defect_area_um2: float | None = None
    scratch_total_length_px: float | None = None
    scratch_total_length_um: float | None = None
    review_statistics: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if type(self.total_defects) is not int or self.total_defects < 0:
            raise ValueError("total_defects must be a nonnegative integer")
        for name in ("count_by_type", "count_by_size_grade", "count_by_severity_grade",
                     "count_by_band", "count_by_roi", "review_statistics"):
            if any(type(v) is not int or v < 0 for v in getattr(self, name).values()):
                raise ValueError(f"{name} must contain nonnegative integer counts")
        for name in ("total_defect_area_px", "total_defect_area_um2", "scratch_total_length_px", "scratch_total_length_um"):
            nonnegative(getattr(self, name), name)
