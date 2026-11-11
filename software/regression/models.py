"""Regression report protocol, independent of detection/storage wire versions."""
from dataclasses import dataclass, field, asdict
from pathlib import Path
import json


@dataclass
class RegressionComparison:
    status: str = 'PASS'
    added_objects: list = field(default_factory=list)
    disappeared_objects: list = field(default_factory=list)
    bbox_changes: list = field(default_factory=list)
    area_changes: list = field(default_factory=list)
    Feret_changes: list = field(default_factory=list)
    grade_changes: list = field(default_factory=list)
    source_membership_changes: list = field(default_factory=list)
    mask_changes: list = field(default_factory=list)
    ROI_changes: list = field(default_factory=list)
    audit_changes: list = field(default_factory=list)
    statistics_changes: list = field(default_factory=list)
    execution_changes: list = field(default_factory=list)
    object_semantic_changes: list = field(default_factory=list)
    metadata_changes: list = field(default_factory=list)
    calibration_changes: list = field(default_factory=list)
    quality_control_changes: list = field(default_factory=list)
    critical_differences: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    info: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def to_dict(self): return asdict(self)

    def save_json(self,path):
        with Path(path).open('x',encoding='utf-8') as stream:
            json.dump(self.to_dict(),stream,ensure_ascii=False,indent=2,allow_nan=False)

    def finish(self):
        self.status='FAIL' if self.critical_differences or self.errors else 'PASS_WITH_WARNINGS' if self.warnings else 'PASS'
        return self
