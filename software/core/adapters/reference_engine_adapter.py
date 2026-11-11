"""Reference engine process boundary, static RAW profile, and source provenance."""
from pathlib import Path
from dataclasses import dataclass
import ast
import json
import os
import subprocess
import sys
import time
from core.errors import InputValidationError, EngineExecutionError, InspectionCancelled
from core.runtime.resources import sha256, load_json, write_json


@dataclass(frozen=True)
class RawProfile:
    width: int
    height: int
    effective_bits: int
    byte_order: str
    container_bits: int = 16

    @property
    def shape(self):
        return self.height, self.width


class ReferenceEngineAdapter:
    def __init__(self, reference_root=None, python_executable=None, *, timeout_seconds=3600,
                 cancellation_event=None):
        self.project_root = Path(__file__).resolve().parents[2]
        self.reference_root = Path(reference_root) if reference_root else self.project_root.parent / "DefectDetectionProject"
        self.python_executable = Path(python_executable) if python_executable else self.reference_root / ".venv/Scripts/python.exe"
        self.timeout_seconds = timeout_seconds
        self.cancellation_event = cancellation_event

    def profile(self):
        config = self.reference_root / "config/user_config.py"
        tree = ast.parse(config.read_text(encoding="utf-8-sig"))
        values = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                key = node.targets[0].id
                if key in {"RAW_WIDTH", "RAW_HEIGHT", "EFFECTIVE_BITS", "RAW_ENDIAN", "RAW_DTYPE"}:
                    values[key] = ast.literal_eval(node.value)
        if values.get("RAW_DTYPE") != "uint16" or values.get("RAW_ENDIAN") != "big":
            raise InputValidationError("reference RAW profile is unsupported; do not guess decoding")
        return RawProfile(values["RAW_WIDTH"], values["RAW_HEIGHT"], values["EFFECTIVE_BITS"], values["RAW_ENDIAN"])

    def source_manifest(self):
        files = [self.reference_root / "main.py", self.reference_root / "requirements.txt"]
        for folder in ("config", "src", "scripts"):
            files.extend((self.reference_root / folder).rglob("*.py"))
        records = [{"path": p.relative_to(self.reference_root).as_posix(), "sha256": sha256(p)} for p in sorted(files)]
        import hashlib
        digest = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return digest, records

    def run(self, image_path, mode, run_dir, logger):
        if not self.python_executable.is_file():
            raise EngineExecutionError("reference virtual environment Python not found")
        if self.cancellation_event is not None and self.cancellation_event.is_set():
            raise InspectionCancelled("inspection cancelled before engine start")
        run_dir = Path(run_dir)
        output = run_dir / "engine" / mode.value
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise EngineExecutionError("refusing to reuse an engine output directory")
        command = [str(self.python_executable), str(self.project_root / "core/runtime/engine_worker.py"),
            "--reference-root", str(self.reference_root), "--input", str(image_path),
            "--output", str(output), "--mode", mode.value]
        log_path = run_dir / "logs" / (mode.value + "_engine.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        start = time.perf_counter()
        logger.info("%s start", mode.value)
        with log_path.open("x", encoding="utf-8") as log:
            child = subprocess.Popen(command, cwd=self.project_root, stdout=log, stderr=subprocess.STDOUT,
                env=dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1"),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                while child.poll() is None:
                    if self.cancellation_event is not None and self.cancellation_event.is_set():
                        raise InspectionCancelled("inspection cancelled while engine was running")
                    if time.perf_counter() - start > self.timeout_seconds:
                        raise EngineExecutionError("reference engine timeout")
                    time.sleep(0.2)
            except BaseException:
                child.kill()
                child.wait()
                raise
        logger.info("%s end exit=%s elapsed=%.3f", mode.value, child.returncode, time.perf_counter() - start)
        if child.returncode:
            error = load_json(output / "bridge_error.json") if (output / "bridge_error.json").is_file() else {
                "reason": "UNKNOWN_EXCEPTION", "stage": "PROCESS", "error": "nonzero engine exit"}
            return output, error
        return output, None
