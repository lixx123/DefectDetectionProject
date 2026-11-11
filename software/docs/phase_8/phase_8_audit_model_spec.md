# AuditViewModel

持有CandidateAuditRecord不可变tuple引用及整数索引，不复制或改写domain。CandidateKey是(source,candidate_id) tuple；重复完整Key会告警且candidate(key)返回None，避免任意选择。相同id不同source合法。
统计覆盖全部audit_log.candidates：五种disposition、仅FILTERED的reason、动态source/stage、关联/未关联、source声明数量/实际数量/lineage_complete。None不是OTHER；FILTERED缺reason保留协议异常，stage None显示—。PENDING始终可见并警告。
声明数量不符和lineage_complete=false优先显示红色提示；完整issues保留于统计JSON。filter/search/sort/page都不改变全量统计。
AuditInfo.events通过QAbstractTableModel按实际dict展示；可选time/timestamp/stage/type/event_type/name/message/reason，其他字段完整JSON，无固定事件协议假设。
执行/事件为存量证据展示，不重新运行安全门或任何算法。
