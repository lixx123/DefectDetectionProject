# 人工复核准入页

第五Tab“人工复核准入”，保留原四页。顶部明确“当前仅生成复核建议队列，尚未执行人工审核”。同时显示Audit REVIEW候选数与真正人工ReviewTask数、Defect/Candidate任务分布、压缩比、建议目标是否达标、策略id/version/hash及警告。
四张小卡分别显示AUTO_ACCEPT/AUTO_REJECT/MANUAL_REVIEW/AUDIT_ONLY的Defect/Candidate对象数量。默认表为人工任务，其他bucket对象均可切换查看，不能隐藏仅审计或排除记录。

QAbstractTableModel虚拟500/页；全量AND过滤对象类型/优先级/原因/Band/Source，全局排序ID/优先级/面积/Feret/Band等。HIGH红、MEDIUM橙、LOW灰，旁注明优先级不是尺寸/严重度。None为—，Candidate未提供Band不从ID字符串伪造。
详情显示主对象、task_kind、原因、中文解释、evidence、related_candidates和局部图。Defect复用Phase7 DefectDetailViewModel，Candidate复用Phase8 CandidateDetailViewModel；不新增RAW parser。仅当前选中且本页活动时worker读取资源，epoch/revision拒绝旧返回。过滤排除当前选中对象会清空旧详情；排序保留对象身份并滚动到选中行。
Defect跳既有详情并透明清除遮挡显示筛选；Candidate调用审计focus_candidate，待后台索引完成后定位完整source/id和目标页。无RAW仍可看所有准入数据，用包内资源或明确标注中性底图。
不存在确认/驳回/误报/修改等级/意见/审核人时间等写回控件；无参数编辑器，无存库或正式报告导出。

