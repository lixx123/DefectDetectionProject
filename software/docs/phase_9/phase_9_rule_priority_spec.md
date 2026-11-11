# 规则顺序与优先级

优先级是复核紧急度，不是尺寸等级/严重度。HIGH：无效final link、lineage/安全证据冲突、缺失关键几何、明确promising证据、独立来源支持或大几何风险。MEDIUM：一般尺寸/边界/空间关联风险、有效分级边界、策略要求的光度缺失。LOW：有几何但去向/语义尚未解释的普通候选。

## 顺序显式定义

1. HARD_SAFETY
2. FINAL_DEFECT_PROTECTION
3. LINKED_CANDIDATE_EVIDENCE
4. OUTSIDE_WORK_EXCLUSION
5. HISTORICAL_OUTSIDE_AUDIT
6. HIGH_RISK_UNCERTAINTY
7. EXPLICIT_LOW_RISK_EXCLUSION
8. MISSING_GEOMETRY
9. HISTORICAL_ARCHIVE
10. PROVISIONAL_LOW_RISK_AUDIT
11. UNRESOLVED_UNCERTAINTY

具体Candidate分支：

1. 硬异常优先：无效非空finalID、重复Key、source/反向lineage矛盾、已存安全门异常、RETAINED无final、FILTERED缺reason、非法合并目标→MANUAL_REVIEW/HIGH。
2. 有效关联最终对象且无异常→AUDIT_ONLY；历史merged_into==有效finalID且没有同名候选→AUDIT_ONLY+DATA_LIMITATION。此14条历史限制不直接生成人工图像任务。
3. FILTERED+OUTSIDE_WORK且没有相反证据→AUTO_REJECT。
4. 历史归档且明确保存OUTSIDE_WORK语义→AUDIT_ONLY，不因旧框大而重扫或篡改。
5. 现有尺寸、promising、boundary、独立来源或与最终bbox相交→MANUAL_REVIEW，保留多原因。
6. 无风险的明确BACKGROUND_NOISE/LOW_EVIDENCE过滤→AUTO_REJECT；缺关键几何→MANUAL_REVIEW；普通历史归档→AUDIT_ONLY；已知暂存/未证实噪声/共享seed说明且无风险→AUDIT_ONLY；其余不确定→MANUAL_REVIEW/LOW。

最终Defect在Candidate评估后决策，以汇总其关联候选冲突。lineage不完整/声明数不符/反向异常/重复Key、关键几何缺失、已存分级冲突或UNCERTAIN/FALSE_POSITIVE→人工；有效阈值邻域和策略开启的光度缺失→人工；其他最终接受。没有任何最终Defect进入AUTO_REJECT/AUDIT_ONLY的分支。
排序稳定：任务按HIGH/MEDIUM/LOW、ReviewObjectKey排序；filter/sort在全量匹配集合完成后分页，输入无随机和时间依赖。多原因排序去重，不依赖集合遍历顺序。

