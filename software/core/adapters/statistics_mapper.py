from collections import Counter
import math
from domain import InspectionStatistics


def aggregate(defects):
    def counts(getter):
        return dict(Counter(str(getter(d) or "UNKNOWN") for d in defects))
    def total(values):
        return None if any(v is None for v in values) else math.fsum(values)
    scratches = [d for d in defects if d.classification.defect_type == "SCRATCH"]
    # The reference engine currently supplies size grade, not a reliable type label.
    typed = all(d.classification.defect_type is not None for d in defects)
    return InspectionStatistics(total_defects=len(defects),
        count_by_type=counts(lambda d: d.classification.defect_type),
        count_by_size_grade=counts(lambda d: d.classification.size_grade.value),
        count_by_severity_grade=counts(lambda d: d.classification.severity_grade.value),
        count_by_band=counts(lambda d: d.location.band_id), count_by_roi=counts(lambda d: d.location.roi_id),
        total_defect_area_px=total([d.geometry.area_px for d in defects]),
        total_defect_area_um2=total([d.geometry.area_um2 for d in defects]),
        scratch_total_length_px=total([d.geometry.length_px for d in scratches]) if typed else None,
        scratch_total_length_um=total([d.geometry.length_um for d in scratches]) if typed else None,
        review_statistics=counts(lambda d: d.review.review_status.value))
