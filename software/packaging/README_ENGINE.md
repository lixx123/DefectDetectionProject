# Engine and GUI reproducible Windows build

1. Create an isolated Python3.14 build venv and `pip install -r packaging/requirements-engine-lock.txt`. Do not copy a venv into the release. GUI uses its existing requirements-lock/build requirements.
2. `powershell -ExecutionPolicy Bypass -File packaging/build_engine.ps1 -ReferenceRoot <frozen algorithm source> -BuildPython <isolated build python> -BuildName engine_release_final`
3. `powershell -ExecutionPolicy Bypass -File packaging/build_release.ps1 -EnginePackage <engine_release_final/dist/engine_runner> -OutputRoot <fresh output>`

Build only creates new owned directories; existing output names are refused. Source and numeric configuration are never rewritten. Engine source SHA and per-file hashes are recorded. The artifact entry points are independent PyInstaller onedir executables. The GUI package includes only the current real Engine, not test stubs. Source may be present for build; the copied release QA has no source or developer venv.

The Engine payload builder preserves historical approval/negative/identity/lineage resources demanded by the frozen reference algorithm; these are not precomputed InspectionResults. Every new detection recomputes the fresh pipeline. Runtime path relocation is isolated to the runner and storage I/O adapters; all frozen algorithm parameter/code hashes remain verified.
