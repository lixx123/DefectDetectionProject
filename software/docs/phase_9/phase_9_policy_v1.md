# Review Admission Policy v1

policy_id=review_admission_v1，policy_version=1.0，policy_hash=63edae3c40966768f907360a377ad7847ebbf477121afb54c1595b69c80f2327。
Hash为规范化配置（含policy_id/version、所有参数）的SHA256，数字统一float、键排序、无时间/随机项；规则实现另由最终Git提交绑定，未来语义调整必须更新策略版本。改变参数只影响派生决策/队列及目标状态，不改变检测数据。

- Defect边界margin：面积±5px²，Feret±2px。沿用LARGE面积≥250或Feret≥45、MEDIUM面积≥40或Feret≥15。只有可能改变OR分级的有效边界才触发；例如面积1000时Feret接近15不会触发。
- Candidate复核尺寸线索：面积≥40或Feret≥15；高优先级尺寸线索：面积≥250或Feret≥45。不重算测量或更改SizeGrade。
- 缺失光度默认不单独触发：review_when_missing_photometry=False。正式71个Defect均未提供该字段，不能把历史字段未提供一律视为证据冲突。显式启用时会准入MISSING_PHOTOMETRY。
- Candidate.initial_geometry常为部分几何。bbox和area是该分支所需关键字段；未提供的Feret保持None，不填0、不反推。独立的尺寸规则只对已提供字段比较。缺Feret不证明风险低，也不作漏检率结论。
- preferred_max_per_result=50是工程建议，绝不是容量上限。超量全部保留，显示TARGET_NOT_MET。报告样本前20个HIGH/MEDIUM的截取仅用于QA样本文件，不影响tasks。
- 历史OUTSIDE_WORK归档保持AUDIT_ONLY；既有REVIEW不自动变成噪声/排除。已知微小暂存/未证实噪声/共享seed/弱暗斑说明，只有未命中风险时AUDIT_ONLY。
- 同bbox不同source只是重合线索。只有同时有明确extensions.independent_source_evidence=true才作为独立来源支持；不把同一算法链的相关表示误判为独立命中。
- 空间相交仅比较现有bbox，采用512像素格索引；仅是复核线索，不推断真实source membership、不建立新final_defect_id、不聚合成同一物理对象。
- 已有FILTERED+OUTSIDE_WORK且无相反lineage/空间/独立来源/边界证据可AUTO_REJECT；工作区外大面积本身不是“工作区内高风险”。BACKGROUND_NOISE/LOW_EVIDENCE只有未触发风险且几何满足该分支才AUTO_REJECT，绝不一律排除LOW_EVIDENCE。

## 原因码中文解释

- `BACKGROUND_NOISE`：已有 FILTERED + BACKGROUND_NOISE 且无当前高风险证据。
- `CANDIDATE_SIZE_RISK`：现有面积或Feret达到策略复核阈值。
- `DATA_LIMITATION`：历史 merged_into 保存最终ID；独立 final_defect_id 有效，保留原值。
- `EXISTING_REVIEW_REQUIRES_ATTENTION`：既有UNCERTAIN或FALSE_POSITIVE与最终接受状态需要核对。
- `FINAL_ALGORITHM_ACCEPTED`：算法最终接受且未发现当前策略要求复核的证据；不等于人工确认。
- `HISTORICAL_AUDIT_ONLY`：历史归档保留，不直接等同人工工作队列。
- `HISTORICAL_OUTSIDE_WORK_EVIDENCE`：已存工作区外、历史未重扫语义，仅审计保留，不改原disposition。
- `INVALID_FINAL_LINK`：已存 final_defect_id 非空，但当前结果不存在该最终疵病；保留原值，生成一致性任务。
- `LARGE_CANDIDATE_GEOMETRY`：现有面积或Feret达到策略高风险阈值。
- `LINEAGE_INCONSISTENT`：来源链、声明数量或对象关联存在不一致，需要核对。
- `LINKED_TO_ACCEPTED_DEFECT`：有效关联最终疵病，由最终对象承担主任务，候选作为证据。
- `LOW_EVIDENCE_LOW_RISK`：已有 LOW_EVIDENCE，已提供所需几何且未触发当前风险规则。
- `MERGE_TARGET_AMBIGUOUS`：合并目标对应多个来源候选，不能任意选择。
- `MERGE_TARGET_UNRESOLVED`：合并目标无法解析为唯一候选，且不属于已知有效最终ID历史表示。
- `MISSING_FILTER_REASON`：FILTERED 未提供必需的排除原因。
- `MISSING_GEOMETRY`：缺少本规则所需几何字段，不以零替代。
- `MISSING_PHOTOMETRY`：当前策略显式要求光度证据，但结果未提供。
- `MULTI_SOURCE_COINCIDENCE`：bbox重合且提供明确独立来源支持；单纯重合不足以触发。
- `NEAR_SIZE_THRESHOLD`：测量值位于可能改变尺寸分级的有效阈值邻域；未改变原分级。
- `OUTSIDE_WORK`：已有 FILTERED + OUTSIDE_WORK_REGION 排除依据，且无相反关联证据。
- `PROMISING_DARK_EVIDENCE`：已存明确的 promising dark 审计证据，准入层不重新分析图像。
- `PROVISIONAL_LOW_RISK_AUDIT_ONLY`：已知暂存/未证实噪声或共享seed语义，且未触发当前风险规则；不判噪声、不删除。
- `RETAINED_WITHOUT_FINAL_LINK`：RETAINED 候选没有最终关联，账本需要核对。
- `SIZE_GRADE_EVIDENCE_CONFLICT`：已存尺寸分级与现有面积/Feret规则不一致。
- `SPATIAL_FINAL_ASSOCIATION`：候选bbox与最终对象bbox相交，仅作为风险线索，不伪造lineage。
- `UNRESOLVED_CANDIDATE`：当前字段不足以将该候选归为明确排除或已知审计保留。
- `UNRESOLVED_FINAL_SELECTION`：FINAL_SELECTION 记录仍缺少明确最终去向或存在风险。
- `WEAK_EVIDENCE_HIGH_RISK`：存在独立于原REVIEW标签的风险线索，需人工查看。
- `WORK_BOUNDARY_UNCERTAINTY`：已存工作区边界不确定说明。

