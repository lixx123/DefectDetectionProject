# 提交前测试记录

Phase9新增78项，原479项全部保留，总557项收集；FAST预计522，GOLDEN33，reference probes2。Phase9前76项全通过；最终两个UI用例补充50k后台心跳和筛选清空过期详情，与Phase8联合125项轻量测试通过。
旧测试只更新test_fourth_tab_and_empty的总页签数量4→5；原第四Tab名称/只读空态/禁用按钮等断言均保留，其余旧测试未删改。冻结domain/core/application/configs/infrastructure/tests/golden零改动。
新测试覆盖四bucket/硬保护/显式排除/弱证据风险/已知历史语义/无效链接一致性任务与普通孤立任务区别/有效关联聚合/多原因与三级优先级/确定性及policy hash/零写回/缺失与零状态/目标超量不截断/50000无图像IO及worker心跳/真实两包/全部最终对象保护/第五Tab/过滤排序选择/跨页/各bucket查看/旧请求丢弃。
逐项73条要求映射见requirement_coverage.md；最终全部pytest与各门禁待最终commit后串行运行，提交前证据不替代最终回执。

