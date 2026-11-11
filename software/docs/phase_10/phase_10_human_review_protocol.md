# Phase 10 独立人工审核协议

human_review_v1 与 schema1.0 分离。实现位于 ui/models/human_review，作为运行期派生模型的同级、无Qt依赖子系统；不改变冻结检测Service、领域序列化或正式结果Repository。可单独导入和测试。

HumanReviewDecision有五类：CONFIRMED_DEFECT / FALSE_POSITIVE / DUPLICATE_OF_EXISTING_DEFECT / NEW_MISSED_DEFECT / UNCERTAIN。HumanReviewRecord是frozen dataclass，包含UUID、result_id、完整task/object key、decision、可选target、显式reviewer、带时区ISO8601时间、可空comment、策略id/version/hash、source_result_digest、冻结任务digest、revision和完整geometry_evidence。内存几何为不可变canonical JSON字符串，磁盘为JSON对象。

CandidateKey始终包含source+candidate_id；DefectKey为defect_id。初始bbox/center/面积/长宽/等效直径/方法/相对artifact ref/未知附加几何均无损保留。新漏检只追加独立证据，不生成正式Defect ID。算法结果、既有ReviewInfo和Golden不写回。

有效结果摘要等于对result.to_dict()的canonical UTF8 JSON（排序键、紧凑分隔符、不允许NaN）的SHA256。异常运行期lineage可能不满足冻结正式序列化器：独立只读source_payload保留原始字段（含未知字段）计算同形摘要，不修复无效ID、不解除正式校验、不得据此生成正式结果包；有效结果已测试与to_dict完全相等。

隐私：审核者由人明确填写，不读取系统账户/IP/序列号。审核协议递归拒绝机器绝对路径；仅持久化ID、相对引用及证据。V1审核者名称是本地声明身份，不是账户认证。CSV/JSON仅导出独立审核数据，不能代替正式报告。
