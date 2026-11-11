import csv
from pathlib import Path
from core.errors import EngineOutputError


def read_rows(path, *, required=True):
    path = Path(path)
    if not path.is_file():
        if required:
            raise EngineOutputError(f"missing table: {path.name}")
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return [{k: (v if v not in (None, "nan", "NaN") else "") for k, v in row.items()}
                for row in csv.DictReader(stream)]


def first(row, *keys, default=""):
    return next((row[k] for k in keys if row.get(k) not in (None, "")), default)


def truth(value):
    return str(value).lower() in ("true", "1")


def sources(value):
    return {v for v in str(value or "").split(";") if v}
