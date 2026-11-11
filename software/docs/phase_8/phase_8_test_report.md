# 提交前专项测试记录

Phase8专项：51 passed；其中49合成/轻量，2正式历史包Golden。现有Phase6/7 UI与当时Phase8轻量集成回归110 passed，旧测试原样保留。最终全部479项必须在最终commit后重跑，不能用本报告替代。
覆盖：tuple身份与同ID不同source、全量计数与动态分组、实际attempt/fallback/QA、FILTERED原因与None异常、MERGED唯一/歧义、invalid final link、双向跳转和隐藏筛选清除、所有组合筛选、debounce、全局排序/分页边界、50000响应与控件/IO限制、旧请求丢弃/快速切换、inactive无IO、synthetic RAW原像素、preview优先级/资源SHA、不伪造初始bbox、候选/最终框分离、任意events、零写回、两组正式包。
新增需求到测试和最终门禁的逐项映射见 requirement_coverage.md。未删除/弱化428个已有测试；不实际运行Detector。
最终pytest/FAST/GOLDEN/RELEASE/smoke/pip、路径扫描、外部RAW拒绝守卫、765原算法文件保护与冻结文件hash只在最终commit干净工作树上验收。

