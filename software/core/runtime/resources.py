"""Per-run portable resources. Never publishes a machine absolute path in the result."""
from pathlib import Path
import hashlib
import json
import shutil
from dataclasses import dataclass
from domain.common import ArtifactReference
from core.errors import EngineOutputError


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


@dataclass
class ResourceCollector:
    run_dir: Path

    def reference(self, path, *, group="evidence"):
        source = Path(path).resolve()
        if not source.is_file():
            raise EngineOutputError(f"missing required {group} resource: {source.name}")
        digest = sha256(source)
        try:
            relative = source.relative_to(self.run_dir.resolve())
        except ValueError:
            destination = self.run_dir / "artifacts" / group / (digest[:12] + "_" + source.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copy2(source, destination)
            if sha256(destination) != digest:
                raise EngineOutputError("copied resource SHA256 mismatch")
            relative = destination.relative_to(self.run_dir)
        return ArtifactReference(path=relative.as_posix(), sha256=digest)


def portable_reference(reference):
    # extensions accept JSON values, not ArtifactReference instances.
    return {"path": reference.path, "sha256": reference.sha256}
