from dataclasses import dataclass, field
from .common import Record, nonnegative


@dataclass(kw_only=True)
class AlgorithmInfo(Record):
    software_version: str = "0.2.0"
    algorithm_version: str | None = None
    config_name: str | None = None
    config_version: str | None = None
    config_hash: str | None = None
    run_timestamp: str | None = None
    execution_time_seconds: float | None = None
    runtime_environment: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        nonnegative(self.execution_time_seconds, "execution_time_seconds")
