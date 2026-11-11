# Engine Protocol V1

Request: protocol_version=1.0, task_id, run_id (new UUID per request), image_path, captured config_snapshot, fresh work_directory. No algorithm parameter override UI. Exactly one engine_runner.exe --request <JSON> is launched per GUI job, under the pinned immutable Engine package. The runner may launch its same executable for each frozen AUTO attempt; all attempts are counted and logged.

Response: engine_receipt.json with status, request/run identity, engine identity, input_sha256, config_hash, output_result (relative), artifact_root (relative), result_sha256, result_id, attempt PIDs and algorithm_executions. Success requires a new valid schema1.0 InspectionResult and hash-valid typed artifacts. Failure preserves logs/traceback and cannot be formally saved.

Manifest requires engine_id/version, protocol1.0, schema1.0, fixed RAW profile, runner path/hash, algorithm_source_sha256, config_version, file hash manifest, engine_bundle_sha256. Bundle hash is SHA256 of canonical sorted file-path/hash map, excluding only the root engine_manifest.json to avoid a self-reference. All other files must match; unknown extra files are rejected. This is an integrity/compatibility contract for operator-installed local packages, not an online update service.

AlgorithmInfo.extensions.engine and engine_execution preserve per-result engine identity, algorithm source hash, bundle hash, protocol and run ID. Existing algorithm_version/config_hash/timestamps/runtime_environment remain. Historic result display reads its own metadata; it never executes the currently selected engine. New optional algorithm-specific data belongs in extensions; schema migration is out of scope.

Registry: engines/current.json -> versions/<engine_id>_<engine_version>. Install to a fresh staging directory, verify before/after copy, rename to a new immutable version, then atomically replace current.json. Never overwrite old versions. Selection and rollback validate the target fully before switching. Close the GUI before operator updates; in-flight jobs pin one package and reverify it after exit.

Runtime paths and imports are local to the Engine package; PATH is Windows/System32 plus the package, Python/venv/PYTHONPATH variables are removed. Reference source bytes are unchanged. Source_manifest contains every frozen source path/hash; source version matches b59eddcddc7739b94b5a58dff93fc3c2235aa63dbda049cd07ae16d5696706a5.

Historical approvals/negative shapes/identity/lineage are read-only resources required by frozen V1 only when its own RAW hash comparison recognizes an approved frame. They are not schema InspectionResults and are never returned as a detection result. RAW data folder and historical CSV resource prefixes are relocated at runtime; numeric values, masks, thresholds and decision functions are untouched. Unknown new RAW uses the frozen fresh-input branch. Full BH/J4/J5/K8/selection/mapping is recomputed by a fresh process for acceptance.

Windows extended-length paths are an I/O spelling adapter. Relative artifact validation, link/junction rejection and root containment remain enforced. No OS settings are changed.

QA evidence separates Python file-open audit events and loaded native module paths from OS-wide monitoring; it does not claim an ETW/ProcMon trace. Raw inputs, isolated output paths and Windows system resources are explicitly allowed. Any other Python file-open is rejected. No system Python or developer source/venv is a fallback.
