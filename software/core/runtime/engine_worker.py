"""Subprocess-only bridge. Changes output location, never algorithm parameters."""
from pathlib import Path
import argparse
import json
import platform
import sys
import traceback
import types
import importlib.util
import importlib.machinery


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-root", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=["full", "roi-bh", "roi-j4"], required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project))
    sys.path.insert(0, str(args.reference_root))
    from core.adapters.qa_mapper import classify_failure
    # The reference scripts/ is a namespace package. A regular software scripts/
    # package would otherwise shadow it despite sys.path ordering. Pin the
    # reference package in this short-lived process, never in the application.
    package_dir = args.reference_root / "scripts"
    initializer = package_dir / "__init__.py"
    if initializer.is_file():
        spec = importlib.util.spec_from_file_location("scripts", initializer,
            submodule_search_locations=[str(package_dir)])
        package = importlib.util.module_from_spec(spec)
        sys.modules["scripts"] = package
        spec.loader.exec_module(package)
    else:
        package = types.ModuleType("scripts")
        package.__package__ = "scripts"
        package.__path__ = [str(package_dir)]
        package.__spec__ = importlib.machinery.ModuleSpec("scripts", loader=None, is_package=True)
        sys.modules["scripts"] = package

    def save(name, value):
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    stage = "IMPORT"
    try:
        # Historical global roots are resolved BEFORE redirecting only this run's output.
        from scripts import run_two_level_unified as engine
        from config import user_config as cfg
        import numpy as np
        import cv2
        stage = "BAND_LOCATOR"
        raw = np.memmap(args.input, mode="r", dtype=">u2", shape=(cfg.RAW_HEIGHT, cfg.RAW_WIDTH))
        try:
            geometry = engine.base.locate_transmission_bands(raw, engine.base.BandLocatorConfig())
        except Exception:
            stage = "BAND_LOCATOR_FAILED"
            raise
        stage = "ROI_PLAN"
        plan = engine.build_plan(raw.shape, geometry, force_full=args.mode == "full")
        if args.mode != "full" and plan["fallback_reasons"]:
            save("band_geometry.json", {k: v for k, v in geometry.items() if k != "profile"})
            save("detection_plan.json", plan)
            stage = "BAND_GEOMETRY_INVALID"
            raise RuntimeError("BAND_GEOMETRY_INVALID: " + ";".join(plan["fallback_reasons"]))
        del raw
        stage = "ENGINE_RUN"
        cfg.OUTPUT_ROOT = args.output.parent
        output = engine.run_raw(args.input, run_id=args.output.name, mode=args.mode)
        stage = "POST_EXECUTION_QA"
        # Execute the reference sentinel guard against EVERY actual J4 window.
        fused = np.load(output / "fused_blackhat.npy", mmap_mode="r", allow_pickle=False)
        checked = 0
        for tile in plan["tiles"]:
            state = json.loads((output / "upstream_J4/fresh/tile_status" / (tile["tile_id"] + ".json")).read_text(encoding="utf-8"))
            x0, y0, x1, y1 = state["work_xyxy"]
            engine.base.require_computed_response(fused[y0:y1, x0:x1], "Phase3 actual J4 consumed window")
            checked += 1
        ids = cv2.imdecode(np.frombuffer((output / "band_id_fullres.png").read_bytes(), np.uint8), 0)
        engine.base.require_computed_response(fused[ids > 0], "Phase3 actual K8B WORK pixels")
        save("bridge_qa.json", {"sentinel_status": "PASS", "context_rectangles_checked": checked,
            "K8B_work_checked": True, "original_guard": "require_computed_response",
            "runtime_environment": {"engine_python": sys.version, "platform": platform.platform(),
                                    "numpy": np.__version__, "opencv": cv2.__version__}})
        return 0
    except Exception as exc:
        trace = traceback.format_exc()
        reason = classify_failure(trace, stage=stage)
        save("bridge_error.json", {"stage": stage, "reason": reason.value,
                                  "error": repr(exc), "traceback": trace})
        print(trace, file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
