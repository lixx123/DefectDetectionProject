# Phase12 scope and verification plan

Baseline: 470658221523741aa640c9248a36712aa6ecbdea (clean at start).

Explicit user scope: independent GUI release for RAW viewing, formal historical result loading, final defects/details/statistics/audit, manual review and verified RAW association. Real automatic detection still requires the external frozen algorithm environment; do not package that environment or execute its algorithms. algorithm_executions=0; Phase13_started=false.

Production compatibility is limited to app/runtime_paths.py and the controller root lookup. Frozen default root is exe parent; resources remain under _internal; source default remains source root. Packaging launcher creates runtime log. Review/logging/threads/evidence/algorithms are unchanged.

The existing impact gate has an exact file allowlist for reviewed packaging infrastructure and the path helper. Unknown packaging files and core/domain/application changes still demand real-engine evidence. This avoids falsely demanding forbidden algorithm execution for a packaging-only change without disabling impact analysis.

Onedir build uses stock dependency hooks, explicit YAML resources and narrow hidden imports. No collect_all. PySide6 imageformat/platform plugins verified in the built executable. Excludes tests, development tools and scientific dependencies used only by the external engine. Statistics are native Qt.

Compiled opt-in release acceptance uses actual packaged MainWindow/controller/workers/models with isolated repository copies and review data. It does not load source scripts, alter messages/images, execute detectors or submit records. Normal startup does not enter QA. Desktop shell double-click is independently verified. Screenshots and final clean-HEAD test reports are published externally after commit, avoiding self-referential build metadata.

checksums inside onedir cover static files; the ZIP itself is hashed in a sibling checksums.sha256 and delivery_manifest.json. A ZIP cannot contain its own final hash.

发布入口固定 Windows Qt 平台参数 darkmode=0，防止系统深色 palette 与冻结浅色 stylesheet 混用导致白底白字；未改 UI 样式或业务。官方参数：https://doc.qt.io/qt-6/qguiapplication.html#platform-specific-arguments 。
