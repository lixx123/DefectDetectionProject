"""Documented precedence and reason codes. No pixels, algorithms, or domain updates."""
RULE_PRIORITY=('HARD_SAFETY','FINAL_DEFECT_PROTECTION','LINKED_CANDIDATE_EVIDENCE',
               'OUTSIDE_WORK_EXCLUSION','HISTORICAL_OUTSIDE_AUDIT','HIGH_RISK_UNCERTAINTY',
               'EXPLICIT_LOW_RISK_EXCLUSION','MISSING_GEOMETRY','HISTORICAL_ARCHIVE',
               'PROVISIONAL_LOW_RISK_AUDIT','UNRESOLVED_UNCERTAINTY')

REASON_DESCRIPTIONS={
    'INVALID_FINAL_LINK':'已存 final_defect_id 非空，但当前结果不存在该最终疵病；保留原值，生成一致性任务。',
    'LINEAGE_INCONSISTENT':'来源链、声明数量或对象关联存在不一致，需要核对。',
    'MERGE_TARGET_AMBIGUOUS':'合并目标对应多个来源候选，不能任意选择。',
    'MERGE_TARGET_UNRESOLVED':'合并目标无法解析为唯一候选，且不属于已知有效最终ID历史表示。',
    'MISSING_FILTER_REASON':'FILTERED 未提供必需的排除原因。',
    'RETAINED_WITHOUT_FINAL_LINK':'RETAINED 候选没有最终关联，账本需要核对。',
    'MISSING_GEOMETRY':'缺少本规则所需几何字段，不以零替代。',
    'MISSING_PHOTOMETRY':'当前策略显式要求光度证据，但结果未提供。',
    'NEAR_SIZE_THRESHOLD':'测量值位于可能改变尺寸分级的有效阈值邻域；未改变原分级。',
    'SIZE_GRADE_EVIDENCE_CONFLICT':'已存尺寸分级与现有面积/Feret规则不一致。',
    'EXISTING_REVIEW_REQUIRES_ATTENTION':'既有UNCERTAIN或FALSE_POSITIVE与最终接受状态需要核对。',
    'FINAL_ALGORITHM_ACCEPTED':'算法最终接受且未发现当前策略要求复核的证据；不等于人工确认。',
    'LINKED_TO_ACCEPTED_DEFECT':'有效关联最终疵病，由最终对象承担主任务，候选作为证据。',
    'DATA_LIMITATION':'历史 merged_into 保存最终ID；独立 final_defect_id 有效，保留原值。',
    'OUTSIDE_WORK':'已有 FILTERED + OUTSIDE_WORK_REGION 排除依据，且无相反关联证据。',
    'BACKGROUND_NOISE':'已有 FILTERED + BACKGROUND_NOISE 且无当前高风险证据。',
    'LOW_EVIDENCE_LOW_RISK':'已有 LOW_EVIDENCE，已提供所需几何且未触发当前风险规则。',
    'HISTORICAL_AUDIT_ONLY':'历史归档保留，不直接等同人工工作队列。',
    'HISTORICAL_OUTSIDE_WORK_EVIDENCE':'已存工作区外、历史未重扫语义，仅审计保留，不改原disposition。',
    'PROVISIONAL_LOW_RISK_AUDIT_ONLY':'已知暂存/未证实噪声或共享seed语义，且未触发当前风险规则；不判噪声、不删除。',
    'WEAK_EVIDENCE_HIGH_RISK':'存在独立于原REVIEW标签的风险线索，需人工查看。',
    'CANDIDATE_SIZE_RISK':'现有面积或Feret达到策略复核阈值。',
    'LARGE_CANDIDATE_GEOMETRY':'现有面积或Feret达到策略高风险阈值。',
    'PROMISING_DARK_EVIDENCE':'已存明确的 promising dark 审计证据，准入层不重新分析图像。',
    'WORK_BOUNDARY_UNCERTAINTY':'已存工作区边界不确定说明。',
    'MULTI_SOURCE_COINCIDENCE':'bbox重合且提供明确独立来源支持；单纯重合不足以触发。',
    'SPATIAL_FINAL_ASSOCIATION':'候选bbox与最终对象bbox相交，仅作为风险线索，不伪造lineage。',
    'UNRESOLVED_FINAL_SELECTION':'FINAL_SELECTION 记录仍缺少明确最终去向或存在风险。',
    'UNRESOLVED_CANDIDATE':'当前字段不足以将该候选归为明确排除或已知审计保留。',
}


def grade(area,feret):
    if area>=250 or feret>=45:return 2
    if area>=40 or feret>=15:return 1
    return 0


def near_threshold(area,feret,config):
    if area is None or feret is None:return False
    return grade(max(0,area-config.area_grade_margin_px),max(0,feret-config.feret_grade_margin_px))!=grade(area+config.area_grade_margin_px,feret+config.feret_grade_margin_px)


def evidence_flags(candidate):
    """Only explicit structured reference fields count; unrelated free text is not scanned."""
    e=candidate.extensions
    fields=e.get('reference_fields',{})
    if not isinstance(fields,dict):fields={}
    texts=[e.get('reference_decision'),e.get('execution_disposition'),fields.get('decision_reason'),fields.get('reason_for_visibility')]
    return tuple(x for x in texts if isinstance(x,str))


def has_flag(candidate,fragment):return any(fragment in text for text in evidence_flags(candidate))


def candidate_risk(c,config):
    g=c.initial_geometry
    area=g.area_px if g else None;feret=g.length_px if g else None
    high=(area is not None and area>=config.candidate_high_area_px) or (feret is not None and feret>=config.candidate_high_feret_px)
    medium=(area is not None and area>=config.candidate_risk_area_px) or (feret is not None and feret>=config.candidate_risk_feret_px)
    promising=has_flag(c,'PROMISING_DARK_REVIEW')
    boundary=has_flag(c,'BOUNDARY_REVIEW')
    explicit_conflict=any(has_flag(c,x) for x in ('SOURCE_LINEAGE_INVALID','SENTINEL_CONSUMED','ROI_CONTEXT_INCOMPLETE'))
    return high,medium,promising,boundary,explicit_conflict
