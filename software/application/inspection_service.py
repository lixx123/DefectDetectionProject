"""Application composition only; the GUI never constructs package paths."""
from pathlib import Path
from threading import Lock
from configs.loader import load_config
from domain.configuration import InspectionConfig
from domain.serialization import from_dict, to_dict


class InspectionService:
    def __init__(self, detector, repository, *, production_config_path=None):
        self.detector=detector; self.repository=repository; self._lock=Lock()
        self.production_config_path=Path(production_config_path) if production_config_path else Path(__file__).resolve().parents[1]/'configs/production_v1.yaml'

    def inspect_and_save(self, image_path, config=None):
        # Production callers without explicit config load the maintained YAML.
        config=load_config(self.production_config_path) if config is None else config
        captured=from_dict(InspectionConfig,to_dict(config))
        with self._lock:
            result=self.detector.inspect(image_path,captured)
            result.validate_final()
            return self.repository.save(result=result,source_run_dir=self.detector.last_run_dir,
                config_snapshot=captured,config_provenance={'kind':'APPLICATION_CAPTURED_BEFORE_INSPECTION'})
