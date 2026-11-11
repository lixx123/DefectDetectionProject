# 提交前验证说明

本文件为提交前记录，不作为最终commit门禁PASS的替代。schema1.0、AUTO、Golden、正式Repository及Phase9policy保持不变；所有真实人工审核提交禁止。仅两组真实输入可以只读进行RAW关联和交叉错配验证；其他18组不扩展。

工程QA与人工验收分离。正式数据只创建PENDING空会话（隔离验证目录），不向用户output/reviews写测试记录。Synthetic提交只在单独临时审核根。正式存储API未改，RAW仅运行时挂接；原InspectionResult字典与任务集合前后核对。

按任务书依次完成修订、局部、提交前全量、文档、commit、干净检查，再在同一final_commit串行跑全部pytest/FAST/GOLDEN/RELEASE/smoke/pip。最终验证、真实汇总、RAW验证和截图交付镜像更新为commit后证据，跟踪源码/文档保持不动。未开始Phase11或正式修正结果/PDF/Excel报告。


## Evidence Fix Only

09 已从真实 26_1 正式结果和正确 RAW 重新渲染；旧图与06重复的问题已定位并修复。详见 phase_10_revision_evidence_fix.md。源码无功能改动，真实132任务仍全部 PENDING、0记录/0标签。最终门禁须在本次提交后的同一干净HEAD完整执行，以外部交付回执为准。
