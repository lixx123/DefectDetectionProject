"""Portable paths; reject links, Windows device paths, ADS and aliases."""
from pathlib import Path, PureWindowsPath
import re
from app.runtime_paths import native_path,logical_path
from infrastructure.repositories.errors import UnsafeArtifactPathError

DEVICES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}


def result_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise UnsafeArtifactPathError("unsafe result_id")
    if value.upper() in DEVICES: raise UnsafeArtifactPathError("reserved result_id")
    return value


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise UnsafeArtifactPathError(f"unsafe relative path: {value!r}")
    win = PureWindowsPath(value)
    parts = value.split("/")
    if value.startswith("/") or win.drive or any(p in ("", ".", "..") for p in parts):
        raise UnsafeArtifactPathError(f"unsafe relative path: {value!r}")
    if any(p.endswith((".", " ")) or p.split('.')[0].upper() in DEVICES or any(ord(c)<32 for c in p) for p in parts):
        raise UnsafeArtifactPathError(f"unsafe path component: {value!r}")
    return value


def is_link(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def safe_path(root, relative, *, must_exist=True):
    relative = relative_path(relative)
    root = Path(root)
    if is_link(native_path(root)): raise UnsafeArtifactPathError("package/source root is a link")
    path = root
    for part in relative.split('/'):
        path = path/part
        if is_link(native_path(path)): raise UnsafeArtifactPathError(f"linked path: {relative}")
    if not logical_path(native_path(path).resolve()).is_relative_to(logical_path(native_path(root).resolve())):
        raise UnsafeArtifactPathError(f"path escapes root: {relative}")
    path=native_path(path)
    if must_exist and (not path.exists() or not path.is_file()):
        raise FileNotFoundError(relative)
    return path
