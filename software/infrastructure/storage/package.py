"""Referenced resources only; no engine directory traversal for copying."""
from dataclasses import fields, is_dataclass
from pathlib import Path
import hashlib, json, os, shutil
from domain.common import ArtifactReference
from infrastructure.repositories.errors import PackageIntegrityError
from .paths import relative_path, safe_path


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def artifact_references(model):
    """Include typed references and portable {path, sha256} extension references."""
    refs = {}; aliases = {}
    def add(path, digest):
        path = relative_path(path)
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest.lower()):
            raise PackageIntegrityError(f"artifact requires SHA256: {path}")
        if path in refs and refs[path] != digest.lower():
            raise PackageIntegrityError(f"conflicting artifact hashes: {path}")
        if path.casefold() in aliases and aliases[path.casefold()] != path:
            raise PackageIntegrityError(f"case-aliased artifact paths: {path}")
        if path == 'result.json' or path == 'manifest.json' or path.startswith(('metadata/','logs/')):
            raise PackageIntegrityError(f"artifact collides with package metadata: {path}")
        refs[path] = digest.lower(); aliases[path.casefold()] = path
    def walk(value):
        if isinstance(value, ArtifactReference): add(value.path, value.sha256)
        if is_dataclass(value):
            for f in fields(value): walk(getattr(value,f.name))
        elif isinstance(value, dict):
            if 'path' in value and 'sha256' in value: add(value['path'],value['sha256'])
            for child in value.values(): walk(child)
        elif isinstance(value,(tuple,list)):
            for child in value: walk(child)
    walk(model)
    return refs


def copy_checked(source_root, destination_root, relative, expected_hash=None):
    source = safe_path(source_root, relative)
    target = safe_path(destination_root, relative, must_exist=False)
    source_digest = sha256(source)
    if expected_hash is not None and source_digest != expected_hash:
        raise PackageIntegrityError(f"source artifact hash mismatch: {relative}")
    target.parent.mkdir(parents=True,exist_ok=True)
    with source.open('rb') as src, target.open('xb') as dst:
        shutil.copyfileobj(src,dst,1024*1024); dst.flush(); os.fsync(dst.fileno())
    digest = sha256(target)
    if digest != source_digest or sha256(source) != source_digest:
        raise PackageIntegrityError(f"copied artifact hash mismatch: {relative}")
    return digest
