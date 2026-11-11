# Phase 3 Result QC

Result QC验证InspectionResult及必要输出的完整性，不能由Execution QA的PASS自动代替。

1. FINAL_DEFECTS表可读、Defect ID唯一，来源UID不可空。
2. 每个NPZ真实存在且可安全读取，mask shape与bbox及原图范围一致。
3. mask前景面积=CSV面积；独立最大Feret与CSV长度在明确容差内一致。
4. CSV来源=NPZ来源；source ledger/final membership/RAW recovery/J5 membership可追踪；所有最终Defect有反向候选来源。
5. 最终对象mask不重叠，重建整图与原二值PNG逐像素相同。
6. 从Defect[]重算统计，数量/面积与acceptance核对；新鲜source_count与原表行数核对。
7. 最终mask/标注图/测量引用必须存在，影像可解码；资源保存SHA256，外部资源复制前后复验。
8. 返回前通过Phase 2 validate_final的统计、执行、审计和QC独立一致性门禁。
9. 真实验收脚本显式执行JSON保存/加载相等检查，并逐帧做ROI↔FULL和FULL↔冻结基线差异。

资源引用相对本次result.json所在目录。原始引擎CSV/日志作为证据可保留原路径字段，不将其直接平铺为统一结果资源路径；GUI未来使用ArtifactReference，不需要读取原算法全局变量。

未知指标保留None；不能为通过QC填0，不能把尺寸等级当严重度，也不能把Feret当划痕中心线。UNKNOWN类型下划痕总长为None。

任一输出/统计/来源不一致会拒绝本次attempt，AUTO可触发直接FULL安全重试；FULL仍不通过则QC FAIL的失败草稿。没有正式Repository、报告、数据库或发布功能。
