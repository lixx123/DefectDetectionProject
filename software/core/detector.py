"""GUI-free, real reference-engine inspection service."""
from pathlib import Path
from copy import deepcopy
import logging
import platform
import re
import sys
import time
from uuid import uuid4
import numpy as np
from domain import ImageInfo, AlgorithmInfo, InspectionResult
from domain.configuration import InspectionConfig
from domain.enums import PipelineMode, ExecutionStatus
from domain.serialization import from_dict, to_dict
from core.errors import InputValidationError, EngineExecutionError, InspectionCancelled
from core.adapters.reference_engine_adapter import ReferenceEngineAdapter
from core.adapters.qa_mapper import check
from core.runtime.execution_runner import timestamp
from core.runtime.resources import sha256, load_json, write_json
from core.pipeline import execute


class Detector:
    def __init__(self, reference_root=None, output_root=None, python_executable=None,
                 *, engine_adapter=None, timeout_seconds=3600, cancellation_event=None):
        self.project_root = Path(__file__).resolve().parents[1]
        self.output_root = Path(output_root) if output_root else self.project_root / "output/runtime"
        self.adapter = engine_adapter or ReferenceEngineAdapter(reference_root, python_executable,
            timeout_seconds=timeout_seconds, cancellation_event=cancellation_event)
        self.last_run_dir = None

    def inspect(self, image_path: str | Path, config: InspectionConfig) -> InspectionResult:
        # Capture a validated snapshot: later caller edits cannot change a result.
        config = from_dict(InspectionConfig, to_dict(config))
        if config.algorithm_parameters:
            raise InputValidationError("algorithm parameter overrides are not approved by this adapter")
        path = Path(image_path).resolve()
        profile = self.adapter.profile()
        if not path.is_file() or path.stat().st_size != profile.width * profile.height * 2:
            raise InputValidationError("RAW byte count does not match reference width/height/uint16 format")
        raw = np.memmap(path, mode="r", dtype=">u2", shape=profile.shape)
        for y in range(0, profile.height, 512):
            if raw[y:y+512].max() > (1 << profile.effective_bits) - 1:
                raise InputValidationError("RAW contains values above the configured effective bit depth")
        del raw
        input_hash = sha256(path)
        stem = re.sub(r"[^\w-]", "_", path.stem)[:32]
        name = timestamp().replace(":", "").replace("+", "_") + "_" + stem + "_" + uuid4().hex[:8]
        run_dir = self.output_root / name
        run_dir.mkdir(parents=True, exist_ok=False)
        self.last_run_dir = run_dir
        write_json(run_dir / "metadata/config_snapshot.json", to_dict(config))
        (run_dir / "logs").mkdir()
        logger = logging.getLogger("inspection." + run_dir.name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = logging.FileHandler(run_dir / "logs/inspection.log", mode="x", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        start = time.perf_counter()
        try:
            version_hash, manifest = self.adapter.source_manifest()
            write_json(run_dir / "algorithm_source_manifest.json", {"manifest_sha256": version_hash, "files": manifest})
            sample = re.match(r"(\d+)\s*\(", path.stem)
            info = ImageInfo(file_name=path.name, sha256=input_hash, width_px=profile.width,
                height_px=profile.height, container_bits=profile.container_bits, effective_bits=profile.effective_bits,
                byte_order=profile.byte_order, input_format="RAW", sample_id=sample.group(1) if sample else None)
            algorithm = AlgorithmInfo(software_version="0.3.0", algorithm_version="source-sha256:" + version_hash,
                config_name=config.config_name, config_version=config.config_version, config_hash=config.config_hash(),
                run_timestamp=timestamp(), runtime_environment={"adapter_python": sys.version, "platform": platform.platform()})
            legacy_dir = None
            if config.pipeline_mode == PipelineMode.LEGACY_REPLAY:
                baseline = self.project_root / "baseline"
                manifest = load_json(baseline / "baseline_manifest.json")
                found = next((i for i, row in enumerate(manifest["raw_inputs"], 1) if row["sha256"] == input_hash), None)
                if found is None:
                    raise InputValidationError("legacy replay requires an exact frozen RAW content hash")
                legacy_dir = baseline / "results/unified_26" / f"26_{found}"
                algorithm.algorithm_version = "legacy-manifest-sha256:" + sha256(baseline / "source_manifest.json")
            logger.info("input=%s requested_mode=%s run_directory=%s", path.name, config.pipeline_mode.value, run_dir)
            checks = [check("RAW_dimensions", True, stage="INPUT"), check("RAW_effective_bit_depth", True, stage="INPUT"),
                      check("RAW_SHA256", True, input_hash, stage="INPUT")]
            result = execute(self.adapter, path, config, run_dir, info, algorithm, checks, logger, legacy_dir=legacy_dir)
            if self.adapter.source_manifest()[0] != version_hash or sha256(path) != input_hash:
                raise EngineExecutionError("protected source or input RAW changed during inspection")
            result.algorithm_info.execution_time_seconds = time.perf_counter() - start
            bridge_path = run_dir / "engine" / result.execution_info.attempts[-1].mode.value / "bridge_qa.json"
            if bridge_path.is_file():
                result.algorithm_info.runtime_environment.update(load_json(bridge_path)["runtime_environment"])
            result.extensions["real_input_run"] = config.pipeline_mode != PipelineMode.LEGACY_REPLAY
            if result.execution_info.status == ExecutionStatus.SUCCEEDED:
                result.validate_final()
                logger.info("validate_final PASS elapsed=%.3f", result.algorithm_info.execution_time_seconds)
            else:
                logger.error("FAILED draft only; validate_final not permitted")
            # Return the in-memory result. Saving is explicit in validation/application code.
            return result
        except InspectionCancelled:
            write_json(run_dir / "cancelled.json", {"status": "CANCELLED", "elapsed_seconds": time.perf_counter()-start})
            logger.warning("inspection cancelled")
            raise
        except Exception:
            logger.exception("inspection raised; no formal result published")
            raise
        finally:
            logger.removeHandler(handler)
            handler.close()
