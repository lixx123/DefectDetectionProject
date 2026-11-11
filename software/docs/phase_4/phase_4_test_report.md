# Phase 4 测试报告

日期：2026-10-21。

全部 software tests：`255 passed in 84.50s (0:01:24)`，无跳过。

原 190 项全部保留；新增 65 项（63 项专项 + 两组真实完整模型回读集成）。覆盖正常/FAILED 正式门禁、重复与并发 ID、同 RAW 多 ID、暂存完整校验及原子发布、注入复制/索引失败、既有暂存目录保护、全部引用去重、路径/盘符/设备名/junction 逃逸、缺失/目录/hash 错误资源、manifest 元数据与额外文件、日志缺失、实际配置与尺度漂移、历史查询/时间范围、索引丢失损坏/坏包隔离/重建、ZIP 清单/hash/CRC/不覆盖及应用服务生产配置。

两组真实验收只读既有 revision 输出，完整 InspectionResult 相等，result JSON 数值树相等；字节差异仅为既有 codec 的整数到 float 表达规范化，报告未将其误写为字节相同。全部资源 SHA256 验证通过。

Phase 1 smoke、pip check、独立模块导入 PASS。原算法保护 1317 项 SHA256 一致；冻结 domain 与原测试 Git diff 为空。Detector 仅增加实际 config_snapshot 写入，执行/QA/模式策略不变。

实际命令、退出码、耗时：phase_4_software_checks.json；日志：all_software_tests.log、phase1_smoke.log、pip_check.log、independent_module_imports.log；截图：phase1_smoke.png。真实仓库验收可显式执行 `python -m scripts.validate_phase4_repository`，它使用独立验收目录，禁止启动检测算法，重复执行只回读已有有效包，不覆盖历史结果。

import_package 明确延期，因而本轮无 zip-slip 解压实现或对应虚假通过声明；export 为完整实现。未提供永久删除，未进入 Phase 5。
