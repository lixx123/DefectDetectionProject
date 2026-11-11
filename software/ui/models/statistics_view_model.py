"""Read-only final-object aggregates checked against stored result statistics."""
from collections import Counter
import math


def complete_sum(values):
    return None if any(v is None for v in values) else math.fsum(values)


def complete_max(values):
    return None if not values or any(v is None for v in values) else max(values)


class StatisticsViewModel:
    def __init__(self, result):
        self.result = result
        self.defects = tuple(result.defects)
        self.errors, self.warnings = [], []
        stored = result.statistics
        if stored.total_defects != len(self.defects):
            self.errors.append('总数与最终 Defect[] 不一致')
        for field, attribute in (('total_defect_area_px', 'area_px'), ('total_defect_area_um2', 'area_um2')):
            expected = complete_sum([getattr(d.geometry, attribute) for d in self.defects])
            actual = getattr(stored, field)
            if actual is not None and (expected is None or not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6)):
                self.errors.append(field + ' 与最终测量不一致')
        getters = {
            'count_by_type': lambda d: d.classification.defect_type,
            'count_by_size_grade': lambda d: d.classification.size_grade,
            'count_by_severity_grade': lambda d: d.classification.severity_grade,
            'count_by_band': lambda d: d.location.band_id,
            'count_by_roi': lambda d: d.location.roi_id}
        for field, getter in getters.items():
            expected = Counter(str(getter(d) or 'UNKNOWN') for d in self.defects)
            actual = getattr(stored, field)
            if actual and {k:v for k,v in actual.items() if v} != dict(expected):
                self.errors.append(field + ' 与最终对象不一致')
            elif not actual and expected:
                self.warnings.append(field + ' 未提供；分组由最终对象聚合')

    @property
    def consistent(self):
        return not self.errors

    def summary(self):
        s, c = self.result.statistics, self.result.calibration_info
        roi = self.result.roi_info
        work = roi.work_region.pixel_count if roi.work_region and str(roi.status) == 'VALID' else None
        area = s.total_defect_area_px
        return dict(total_defects=s.total_defects, total_area_px=area,
            total_area_um2=s.total_defect_area_um2 if c.valid else None,
            work_area_px=work, defect_area_ratio=area/work if area is not None and work and work > 0 else None,
            max_area_px=complete_max([d.geometry.area_px for d in self.defects]),
            max_feret_px=complete_max([d.geometry.length_px for d in self.defects]))

    def _groups(self, getter, keys=(), label=lambda k:k):
        groups = {str(k):[] for k in keys}
        for defect in self.defects:
            groups.setdefault(str(getter(defect) or 'UNKNOWN'), []).append(defect)
        rows = []
        for key, defects in groups.items():
            rows.append(dict(key=key, label=label(key), count=len(defects),
                percentage=100*len(defects)/len(self.defects) if self.defects else 0,
                area_px=complete_sum([d.geometry.area_px for d in defects]),
                area_um2=complete_sum([d.geometry.area_um2 for d in defects]) if self.result.calibration_info.valid else None,
                max_area_px=complete_max([d.geometry.area_px for d in defects]),
                max_feret_px=complete_max([d.geometry.length_px for d in defects])))
        return rows

    def by_size_grade(self):
        return self._groups(lambda d:d.classification.size_grade, ('SMALL','MEDIUM','LARGE'))

    def by_band(self):
        return self._groups(lambda d:d.location.band_id, (b.band_id for b in self.result.roi_info.band_list),
                            lambda k:'Band '+k if k!='UNKNOWN' else '未归属 Band')

    def by_type(self):
        return self._groups(lambda d:d.classification.defect_type, label=lambda k:'未分类' if k=='UNKNOWN' else k)

    def by_roi(self):
        return self._groups(lambda d:d.location.roi_id, label=lambda k:'未归属 ROI' if k=='UNKNOWN' else k)
