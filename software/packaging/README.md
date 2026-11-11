# Phase12 Windows onedir build

在本工程 Windows 构建环境中安装固定打包依赖：`.venv\Scripts\python -m pip install -r packaging/requirements-build.txt`，运行 `powershell -ExecutionPolicy Bypass -File packaging\build_release.ps1`。运行依赖版本见 requirements-lock.txt，打包版本独立固定。

构建器只创建自己的全新 output/phase12_build 目录；目录已存在就拒绝覆盖。使用 -OutputRoot 指定另一个全新目录可再次构建，不删除用户文件。固定 spec、失败非0、打印最终路径与提交。

标准 PyInstaller hooks 收集 PySide6 QtCore/Gui/Widgets、platforms/qwindows 与 imageformats、numpy 和 cv2；显式添加策略 YAML 和 production YAML。统计图使用 QPainter，不依赖 matplotlib。排除外部算法专用科学库、开发测试与工具链；不使用 collect_all。

`smoke_release.ps1 -ReleaseDir <onedir>` 从临时非源码 cwd 启动真正的 exe，检查窗口可见截图、日志及正常退出。`--release-acceptance <plan.json>` 是显式隔离 QA 入口，编译在 exe 内，不执行动态外部 Python，不需要源码/tests/venv；仅加载计划中的正式包副本和两份批准 RAW，禁止检测与审核提交。正常启动不进入 QA。QA 数据必须在隔离复制目录，不能放入主发布包。

真实自动检测仍依赖外部冻结算法环境，已由用户明确排除本阶段独立部署范围。资源和运行路径适配只改变 frozen 的默认输出位置，不改变任何业务规则。

正式构建要求源码 Git clean；-AllowDirtyProbe 只用于不交付的预检诊断。Qt 使用 Windows 11 系统 ICU，spec 排除 PATH 中误收集的同名外部工具 DLL。

发布入口固定 Windows Qt 平台参数 darkmode=0，防止系统深色 palette 与冻结浅色 stylesheet 混用导致白底白字；未改 UI 样式或业务。官方参数：https://doc.qt.io/qt-6/qguiapplication.html#platform-specific-arguments 。
