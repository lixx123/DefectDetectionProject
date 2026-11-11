# Phase12_Engine 构建环境

Windows-11-10.0.26200-SP0

Python 3.14.7

GUI 依赖见 requirements-lock.txt；Engine 数值依赖固定到原算法实际运行环境，见 packaging/requirements-engine-lock.txt，特别是 numpy2.5.3。独立 engine_build_env 仅用于构建，不随包复制。两套产物各自嵌入运行时，无系统 Python 依赖。

PyInstaller6.22.3，hooks2026.9。Engine 隐藏导入来自冻结入口 AST 闭包，见 packaging/engine_hidden_imports.json；没有 collect_all。算法源码223文件原字节、必要参考资产335文件约24MB。

系统安全模块：运行环境可能由 Windows Defender 注入 ProgramData/Microsoft/Windows Defender/Platform/<version>/MpOav.dll。审计仅对此精确路径结构及文件名调用系统 Authenticode 校验，并要求 Valid + Microsoft Windows 签名，记录路径、签名与 SHA256。它属于操作系统安全组件，不是应用运行依赖；其他包外非 Windows 模块仍拒绝。首轮 QA 因未区分该组件导致完成后的审计失败，未计为验收通过，保留原始日志。

冻结 Golden 的配置 status 为 MODEL_ONLY_NOT_CONNECTED_TO_ENGINE，当前冻结生产配置为 REFERENCE_ENGINE_CONNECTED。两者唯一差异为连接状态标签，导致 config_hash 不同。真实证据验证器重新计算请求配置哈希，逐项比较除 status 外完整配置，并验证仅此历史状态迁移，再仅对比较副本归一化 hash；保存结果/回执中保留真实 hash。参数、尺度或未知状态改变均拒绝，原 Golden 不改。此修订仅影响验收比较器、测试与文档，不进入 GUI/Engine 运行代码。
