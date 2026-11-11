# 候选表与选择

CandidateAuditTableModel为QAbstractTableModel，仅当前页行数；记录存于共享AuditViewModel。十列：序号、Candidate ID、Source、Stage、Disposition、Filter Reason、Merged Into、Final Defect ID、初始面积px²、初始Feretpx。None显示—。只读，无单元格Widget。
默认500条；200/500/1000可选。前后页与页码/页数/匹配数/总数可见；0记录显示0/0，筛选重回第一页并安全夹紧边界。
AND组合disposition/reason/source/stage/关联与否/id搜索/final_id。候选ID casefold contains，搜索200ms debounce。reason与其他筛选冲突时自然为空，不暗改选择。
索引查询先全局筛选和排序，再分页。ID/source/stage/disposition/reason/area/Feret/finalID等列均支持升降序，None独立排序，tupleKey和原序号确保稳定。表头箭头与实际排序同步。
CandidateSelectionController独立保存tupleKey；表行/页码不充当身份，翻页或排序后详情仍指向同一候选。合并候选唯一跳转会清除审计筛选并定位目标页。
当前页切换只重设模型，局部图不随每条行刷新；表筛选不隐藏任何disposition类别。
