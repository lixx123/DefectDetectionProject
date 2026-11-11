"""Independent admission policy, not a detector configuration or schema object."""
from dataclasses import dataclass, asdict, fields
from pathlib import Path
import hashlib
import json
import math
import yaml


@dataclass(frozen=True)
class ReviewAdmissionConfig:
    policy_id: str='review_admission_v1'
    policy_version: str='1.0'
    area_grade_margin_px: float=5.0
    feret_grade_margin_px: float=2.0
    candidate_risk_area_px: float=40.0
    candidate_risk_feret_px: float=15.0
    candidate_high_area_px: float=250.0
    candidate_high_feret_px: float=45.0
    review_when_missing_photometry: bool=False
    preferred_max_per_result: int=50

    def __post_init__(self):
        if not isinstance(self.policy_id,str) or not self.policy_id.strip() or not isinstance(self.policy_version,str) or not self.policy_version.strip():raise ValueError('policy identity required')
        for name in ('area_grade_margin_px','feret_grade_margin_px','candidate_risk_area_px','candidate_risk_feret_px','candidate_high_area_px','candidate_high_feret_px'):
            v=getattr(self,name)
            if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<0:raise ValueError('invalid '+name)
            object.__setattr__(self,name,float(v))
        for name in ('review_when_missing_photometry',):
            if type(getattr(self,name)) is not bool:raise ValueError('boolean required: '+name)
        if type(self.preferred_max_per_result) is not int or self.preferred_max_per_result<0:raise ValueError('invalid preferred max')
        if self.candidate_high_area_px<self.candidate_risk_area_px or self.candidate_high_feret_px<self.candidate_risk_feret_px:raise ValueError('high risk threshold must not be below medium')

    @property
    def policy_hash(self):
        payload=json.dumps(asdict(self),sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def load_policy(path=None):
    path=Path(path) if path is not None else Path(__file__).with_name('review_admission_v1.yaml')
    data=yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or set(data)-{f.name for f in fields(ReviewAdmissionConfig)}:raise ValueError('unknown admission policy fields')
    return ReviewAdmissionConfig(**data)
