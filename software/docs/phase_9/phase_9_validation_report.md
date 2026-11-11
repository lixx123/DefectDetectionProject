# 提交前真实准入与限制

## 26_1

Audit REVIEW=32324；最终Defect=36；候选=32370。

人工任务=83（Defect 2，Candidate 81），优先级{'HIGH': 13, 'MEDIUM': 70}；目标≤50：TARGET_NOT_MET，全部保留。压缩比=389.446:1，数量相对减少99.7432%。该指标把所有人工任务（包括Defect）与Audit REVIEW候选比较，不是准确率/召回率。

Bucket分布：{"AUTO_ACCEPT": {"DEFECT": 34, "CANDIDATE": 0}, "AUTO_REJECT": {"DEFECT": 0, "CANDIDATE": 4}, "MANUAL_REVIEW": {"DEFECT": 2, "CANDIDATE": 81}, "AUDIT_ONLY": {"DEFECT": 0, "CANDIDATE": 32285}}

具体触发原因（可重叠）：{"CANDIDATE_SIZE_RISK": 28, "LARGE_CANDIDATE_GEOMETRY": 9, "NEAR_SIZE_THRESHOLD": 2, "PROMISING_DARK_EVIDENCE": 4, "SPATIAL_FINAL_ASSOCIATION": 53, "WORK_BOUNDARY_UNCERTAINTY": 20}。最大具体规则=SPATIAL_FINAL_ASSOCIATION；通用UNRESOLVED_FINAL_SELECTION/WEAK_EVIDENCE_HIGH_RISK不作为独立贡献相加。

## 26_2

Audit REVIEW=8294；最终Defect=35；候选=8332。

人工任务=49（Defect 0，Candidate 49），优先级{'HIGH': 15, 'MEDIUM': 34}；目标≤50：达标。压缩比=169.265:1，数量相对减少99.4092%。该指标把所有人工任务（包括Defect）与Audit REVIEW候选比较，不是准确率/召回率。

Bucket分布：{"AUTO_ACCEPT": {"DEFECT": 35, "CANDIDATE": 0}, "AUTO_REJECT": {"DEFECT": 0, "CANDIDATE": 0}, "MANUAL_REVIEW": {"DEFECT": 0, "CANDIDATE": 49}, "AUDIT_ONLY": {"DEFECT": 0, "CANDIDATE": 8283}}

具体触发原因（可重叠）：{"CANDIDATE_SIZE_RISK": 27, "LARGE_CANDIDATE_GEOMETRY": 12, "PROMISING_DARK_EVIDENCE": 3, "SPATIAL_FINAL_ASSOCIATION": 40, "WORK_BOUNDARY_UNCERTAINTY": 6}。最大具体规则=SPATIAL_FINAL_ASSOCIATION；通用UNRESOLVED_FINAL_SELECTION/WEAK_EVIDENCE_HIGH_RISK不作为独立贡献相加。

## 必答结论与限制

26_1未达到≤50目标，不能宣称该目标通过；保留83个，不截断、不隐藏、不追加针对样本的阈值调参。26_2为49个，达标。当前策略共132个真实任务，所有71个最终Defect都在AUTO_ACCEPT/MANUAL_REVIEW中，含既有4个CONFIRMED对象。没有相反lineage/空间/promising等风险条件对象被AUTO_REJECT；26_1仅4个既有FILTERED+OUTSIDE_WORK有明确排除依据，26_2无AUTO_REJECT。工作区外记录的大面积不等同工作区内漏检风险。
14个历史MERGED finalID表示仍仅AUDIT_ONLY+DATA_LIMITATION，未变成人工图像任务。所有真实结果前后to_dict digest一致，准入不改变disposition或ReviewInfo。
几何bbox相交只是粗风险线索，可能使部分已被最终对象覆盖的微小候选保守进入队列；没有真实source-mask匹配证据时不自动合并或消掉这些任务，这是26_1超量的主要原因。未来减少队列需要更可靠的来源/空间证据和人工验收，不能在本轮为达50强行排除。
全部最终Defect未提供photometry，默认不据此一律升级；Candidate的部分初始Feret未提供，None不填0。已知微小未证实噪声记录仅审计保留，不被标成噪声、尺寸过滤或删除。缺乏完整人工GT，本轮不报告准确率、召回率、漏检率，也不能由压缩率证明无漏检。

十一张截图包含两组真实无RAW结果、超量60/零任务/非空无效链接一致性任务合成fixtures。工程视觉QA与最终用户人工审核不同。本报告为提交前结果；最终commit和门禁以ignored output/phase9_final及Codex outputs/Phase9权威回执为准。

