"""Explicit version migrations. Unknown versions are never relabelled as 1.0."""
from copy import deepcopy
from collections.abc import Callable

CURRENT_SCHEMA_VERSION = "1.0"


class SchemaVersionError(ValueError):
    pass


class MigrationRegistry:
    def __init__(self):
        self._steps: dict[str, tuple[str, Callable]] = {}

    def register(self, source: str, target: str, migration: Callable):
        if source == target or source in self._steps:
            raise ValueError("duplicate or self-referencing migration")
        self._steps[source] = (target, migration)

    def migrate(self, payload: dict, target: str = CURRENT_SCHEMA_VERSION) -> dict:
        data = deepcopy(payload)
        version = data.get("schema_version")
        visited = set()
        while version != target:
            if version in visited or version not in self._steps:
                raise SchemaVersionError(f"unsupported schema version: {version!r}; no migration to {target}")
            visited.add(version)
            next_version, fn = self._steps[version]
            data = fn(data)
            if not isinstance(data, dict) or data.get("schema_version") != next_version:
                raise SchemaVersionError("migration must return the declared target version")
            version = next_version
        return data


DEFAULT_MIGRATIONS = MigrationRegistry()
