"""Configuration protocol, independent of YAML and algorithm imports."""
from dataclasses import dataclass, field
from .common import Record
from .calibration import CalibrationInfo
from .enums import PipelineMode, IntermediateLevel


@dataclass(kw_only=True)
class AutoPolicy(Record):
    primary: PipelineMode = PipelineMode.ROI_BH
    fallback: PipelineMode = PipelineMode.FULL

    def __post_init__(self):
        if self.primary != PipelineMode.ROI_BH or self.fallback != PipelineMode.FULL:
            raise ValueError("production AUTO policy is ROI_BH -> FULL only")


@dataclass(kw_only=True)
class InspectionConfig(Record):
    config_name: str = "production_v1"
    config_version: str = "0.2.0"
    pipeline_mode: PipelineMode = PipelineMode.AUTO
    advanced_debug: bool = False
    auto_policy: AutoPolicy = field(default_factory=AutoPolicy)
    calibration: CalibrationInfo = field(default_factory=CalibrationInfo)
    intermediate_level: IntermediateLevel = IntermediateLevel.STANDARD
    algorithm_parameters: dict = field(default_factory=dict)
    algorithm_parameter_source: str = "UNCHANGED_REFERENCE_ENGINE"
    status: str = "MODEL_ONLY_NOT_CONNECTED_TO_ENGINE"

    def __post_init__(self):
        if not isinstance(self.pipeline_mode, PipelineMode):
            raise ValueError("pipeline_mode must be a PipelineMode")
        if self.pipeline_mode != PipelineMode.AUTO and not self.advanced_debug:
            raise ValueError("explicit engine/debug/replay modes require advanced_debug")
        self.auto_policy.__post_init__()

    def config_hash(self) -> str:
        import hashlib, json
        from .serialization import to_dict
        data = json.dumps(to_dict(self), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
