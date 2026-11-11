"""Small shared value objects. Coordinates always refer to original pixels."""
from dataclasses import dataclass, field
import math
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


def nonnegative(value, name):
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                              or not math.isfinite(value) or value < 0):
        raise ValueError(f"{name} must be finite and nonnegative")


@dataclass(kw_only=True)
class Record:
    extensions: dict[str, Any] = field(default_factory=dict)
    # Unknown JSON fields remain at their original object level on re-save.
    _unknown_fields: dict[str, Any] = field(default_factory=dict, init=False, repr=False)


@dataclass(frozen=True, kw_only=True)
class FrozenRecord:
    extensions: dict[str, Any] = field(default_factory=dict)
    _unknown_fields: dict[str, Any] = field(default_factory=dict, init=False, repr=False)


@dataclass(frozen=True)
class Point(FrozenRecord):
    x: float
    y: float

    def __post_init__(self):
        nonnegative(self.x, "x")
        nonnegative(self.y, "y")


@dataclass(frozen=True)
class BoundingBox(FrozenRecord):
    x0: int
    y0: int
    x1: int
    y1: int

    def __post_init__(self):
        for value in (self.x0, self.y0, self.x1, self.y1):
            if type(value) is not int or value < 0:
                raise ValueError("bbox coordinates must be nonnegative integer pixels")
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("bbox must be nonempty, [x0,y0,x1,y1) exclusive")


@dataclass(kw_only=True)
class ArtifactReference(Record):
    path: str
    sha256: str | None = None
    media_type: str | None = None
    coordinate_system: str = "ORIGINAL_IMAGE_PIXELS"

    def __post_init__(self):
        path = str(self.path).replace("\\", "/")
        win = PureWindowsPath(path)
        if (not path or path == "." or PurePosixPath(path).is_absolute()
                or win.drive or ":" in path or ".." in path.split("/")):
            raise ValueError("artifact path must be relative to the result directory, without traversal")
        self.path = PurePosixPath(path).as_posix()
        if self.sha256 is not None and (len(self.sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.sha256.lower())):
            raise ValueError("sha256 must contain 64 hexadecimal digits")
