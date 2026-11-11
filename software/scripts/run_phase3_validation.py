"""Explicit acceptance runs; production AUTO itself does not run both modes."""
from pathlib import Path
import argparse
import json
from configs.loader import load_config
from core.detector import Detector
from domain.enums import PipelineMode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--modes", nargs="+", choices=["full", "roi-bh", "auto"], default=["full", "roi-bh", "auto"])
    parser.add_argument("--config", type=Path, default=Path("configs/production_v1.yaml"))
    parser.add_argument("--output-root", type=Path, default=Path("output/phase3_validation/repeated"))
    args = parser.parse_args()
    for mode in args.modes:
        config = load_config(args.config)
        config.pipeline_mode = PipelineMode(mode)
        config.advanced_debug = mode != "auto"
        detector = Detector(output_root=args.output_root)
        result = detector.inspect(args.input, config)
        result.save_json(detector.last_run_dir / "result.json")
        result.validate_final()
        print(json.dumps({"requested": mode, "final": result.execution_info.final_mode.value,
            "defects": result.statistics.total_defects, "area_px": result.statistics.total_defect_area_px,
            "result_directory": str(detector.last_run_dir)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
