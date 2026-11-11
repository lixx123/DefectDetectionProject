from pathlib import Path
import yaml
from domain.configuration import InspectionConfig
from domain.serialization import from_dict, to_dict


def load_config(path: str | Path) -> InspectionConfig:
    with Path(path).open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError("configuration YAML must be a mapping")
    return from_dict(InspectionConfig, data)


def save_config(config: InspectionConfig, path: str | Path):
    with Path(path).open("x", encoding="utf-8") as stream:
        yaml.safe_dump(to_dict(config), stream, allow_unicode=True, sort_keys=False)
