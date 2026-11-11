# Phase 3 revision 测试报告

日期：2026-10-21。

- 全部 software tests：`190 passed in 63.31s (0:01:03)`。
- Phase 2 原 99 项与 Phase 3 原 145 项测试文件均未修改；原 145 项单独回归通过。
- 新增 45 项：原因分类/优先级、人工状态证据、方案 2 的尺寸扩展、未删除待审、真实 J5 UID、归档、membership/合并、六组新快照门禁、配置/AUTO 和工具边界。六组真实测试均实际运行，不跳过。
- 六组完整只读 remap 及逐对象/逐像素比较 PASS，Feret 零容差；所有受保护模型字段完全一致。
- JSON roundtrip 与资源 SHA256 PASS。
- Phase 1 smoke PASS，截图 phase1_smoke.png；pip check PASS；remap CLI --help PASS。
- 原算法与六组 engine 文件前后保护验证 PASS，详细见 revision_protection_verification.json。

重映射验证与测试读取现有结果；真实算法执行次数为 0。原参考 sentinel/导入小探针属于原有测试，不执行 Black-Hat/J4/J5/K8/RAW recovery。未进入 Phase 4。

日志：all_software_tests.log、phase1_smoke.log、pip_check.log、remap_cli_help.log；结构化命令与退出码见 revision_software_checks.json。
