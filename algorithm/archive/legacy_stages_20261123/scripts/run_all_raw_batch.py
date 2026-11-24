"""Run the supported full RAW pipeline for every RAW under the data root.

Incompatible RAW files are not forced through the detector; they receive an
explicit status record in the same batch directory.
"""
from pathlib import Path
from datetime import datetime
import json, re, sys, traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import user_config as C

EXPECTED_BYTES = C.RAW_HEIGHT * C.RAW_WIDTH * 2


def safe_name(path: Path) -> str:
    text = path.stem
    text = re.sub(r"[^0-9A-Za-z._-]+", "_", text).strip("._-")
    return text or "raw"


def main(run_id: str | None = None):
    data_root = Path(C.DATA_ROOT)
    batch_id = run_id or f"ALL_RAW_FULL_PIPELINE_{datetime.now():%Y%m%d_%H%M%S}"
    batch = C.OUTPUT_ROOT / batch_id
    batch.mkdir(parents=True, exist_ok=False)
    files = sorted(data_root.rglob("*.raw"), key=lambda p: str(p).lower())
    manifest = {
        "batch_id": batch_id,
        "data_root": str(data_root),
        "expected_bytes": EXPECTED_BYTES,
        "files": [],
    }
    (batch / "batch_manifest_initial.json").write_text(
        json.dumps({"batch_id": batch_id, "data_root": str(data_root),
                    "expected_bytes": EXPECTED_BYTES,
                    "raw_count": len(files),
                    "files": [str(p) for p in files]},
                   ensure_ascii=False, indent=2), encoding="utf-8"
    )
    import scripts.run_unified_raw_input as pipeline
    old_root = C.OUTPUT_ROOT
    C.OUTPUT_ROOT = batch
    pipeline.C.OUTPUT_ROOT = batch
    used_names = set()
    try:
        for index, raw in enumerate(files, 1):
            base = safe_name(raw)
            name = base
            suffix = 2
            while name in used_names:
                name = f"{base}_{suffix}"
                suffix += 1
            used_names.add(name)
            record = {"index": index, "path": str(raw), "bytes": raw.stat().st_size,
                      "run_id": name, "status": "NOT_STARTED"}
            if raw.stat().st_size != EXPECTED_BYTES:
                record.update({"status": "SKIPPED_INCOMPATIBLE_FORMAT",
                               "reason": f"size {raw.stat().st_size} != expected {EXPECTED_BYTES}"})
                target = batch / name
                target.mkdir()
                (target / "status.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                manifest["files"].append(record)
                print("BATCH_SKIP", json.dumps(record, ensure_ascii=False), flush=True)
                continue
            try:
                out = pipeline.run_raw(raw, name)
                record.update({"status": "COMPLETED", "output": str(out)})
            except Exception as exc:
                record.update({"status": "FAILED", "error": repr(exc),
                               "traceback": traceback.format_exc()})
                print("BATCH_FAIL", json.dumps(record, ensure_ascii=False), flush=True)
            else:
                print("BATCH_COMPLETE", json.dumps(record, ensure_ascii=False), flush=True)
            manifest["files"].append(record)
            (batch / "batch_manifest_progress.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    finally:
        C.OUTPUT_ROOT = old_root
        pipeline.C.OUTPUT_ROOT = old_root
    manifest["completed_at"] = datetime.now().isoformat(timespec="seconds")
    (batch / "batch_manifest_final.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("BATCH_COMPLETE_ALL", batch, flush=True)
    return batch


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
