# Phase10 提交前测试说明

新增82项（80普通合成+2真实PENDING golden），保留旧557项；计划最终全量639 / FAST602 / GOLDEN35 / RELEASE / smoke / pip check。提交前合成开发测试和13张UI观察已通过；最终是否通过以最终commit后的verification/JUnit/命令日志为准，不以计划数冒充执行。

80条逐项映射见requirement_coverage.md。所有真实submit在测试与观察时被patch为禁止；五结论、revision、其他审核者、恢复、异常链接、原子失败/校验损坏、筛选排序/局部RAW、身份保护/过期帧均为合成测试。真实两包仅创建空会话并证明83/49全PENDING、原to_dict摘要一致。

最终纪律：先完成代码/测试/文档并commit，再取干净HEAD，在同一HEAD依次运行全pytest、FAST、GOLDEN、RELEASE、smoke、pip check；不并行重型回归，不执行真实算法。守卫禁止外部RAW，局部RAW测试只读测试临时合成文件。

追加边界回归：正式文件在结果加载后、会话创建前变化时，直接内容摘要核对会阻止使用旧内存结果创建审核会话。旧431bc01验收在发现此边界后主动中止，日志保留；最终以修订后的干净HEAD全套串行验收为准。
