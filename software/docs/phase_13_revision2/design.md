# Phase13 Revision 2: Filter Defect Excel Ledger

Baseline f9e21cdc42ed1bd8a399ec7709d97d923775a698, clean at start after user-authorized withdrawal of the interrupted BBox display revision. That display revision is not included.

The UI save orchestration copies a temporary result, records operator-confirmed filter_metadata in existing extensions, publishes and reloads a verified formal package, then derives the XLSX. Original temporary data and old formal packages remain unchanged. Filter_ID never replaces Result_ID. Repeated Filter_ID is allowed; each Result_ID is projected exactly once.

Ledger code is a GUI projection adapter in ui/models/defect_ledger.py, with no detector, classification, review-policy, measurement or formal repository changes. Schema1.0 and engine reference1.0.0 are frozen. GUI remains1.0.0 engineering unsigned. Result AlgorithmInfo.software_version is retained independently of GUI release metadata.

All package reads are verified. No invalid package is silently dropped. Excel sync scans actual result directories, retains human research annotations independently, serializes threads/processes, fsyncs temporary files, and atomically replaces XLSX. Only a previous valid workbook is backed up. Failures after formal publication never remove the formal result. Sync errors have specific user-facing recovery messages and logs. A leftover .ledger.lock after a forced termination is not deleted automatically; only after confirming no writer is running may maintenance remove that lock file.

Physical units derive from the result declared valid calibration, not a hardcoded3.2. Configured scale is not claimed as metrological calibration; both scale source and metrological state are explicit. Feret is exported only for an existing MAX_FERET measurement method. Unknown values remain blank. Review_Status stays PENDING because independent human-review aggregation is not implemented. Manual Final_Judgement is a research annotation, not an automated review decision.

Source tests use synthetic pixels and controlled result fixtures. Explicit --ledger-acceptance QA uses copies of existing formal measurements with new QA Result_IDs; it never calls detection or human-review submission. Subprocess, detector and review submit guards assert zero. XLSX screenshots are real saved cells in a Qt read-only QA preview, not claimed as Excel/WPS acceptance. QA outputs are outside the clean delivered release.

Gate requirement: final tested commit, pytest + FAST/GOLDEN/RELEASE, source smoke, pip check, compiled GUI flow, frozen engine hash, original result and protected file digests, fresh GUI/ZIP hashes, empty release output directories. No Phase14, no change to prior conditional blind/second-PC/quality state, no code signing or final tag.
