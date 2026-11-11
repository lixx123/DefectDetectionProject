# 统一比较策略

compare_inspection_results(reference,current,reference_dir,current_dir) 返回 RegressionComparison，支持 to_dict/save_json。compare_snapshots 用于独立小型冻结元数据。输出新增/消失、bbox、面积、Feret、grade、source membership、mask、ROI、audit、statistics、execution、calibration、QC 与元数据差异。

对象先唯一 EXACT_SOURCE_SET，无法唯一匹配才唯一 EXACT_GLOBAL_MASK（NPZ 二值像素、shape、全局 bbox 的签名）。不靠顺序 defect_id；不使用 bbox/area 近似放行。两个对象 ID 置换仅 INFO，但对应 source、mask、measurements 仍必须一致。引用 ID 归一为对应精确物理对象 token，避免 Candidate→Defect 指向同一对象时因顺序号变化误报。

CRITICAL：对象新增/消失、bbox/面积/Feret/grade/source/mask、工作区/Band/DN、audit reason/身份/归档状态、statistics、execution/AUTO、calibration、QC、schema/输入与算法/config 语义变化。None 不能变成 0。Feret 使用精确数值一致，不使用宽松容差。完整模型比较 API 在审计失败时额外报告具体候选差异（最多 100 条，明确总数与截断）。

INFO 白名单：result_id、task_id、run_timestamp、execution_time_seconds、attempt 起止时间/耗时、软件显示版本、非算法环境字段 platform/adapter_python、已知 remap provenance、保存时间和日志。engine_python/numpy/opencv 版本、config_hash、scale 和其他未知语义环境键不在白名单。路径只是资源定位，核心资源按内容 SHA；候选来源列表按集合处理。

CSV 中运行路径/顺序 ID 以及 annotated preview 字节属于 supporting_artifacts 诊断，不独立代表检测退化；其底层逐候选语义和所有物理 mask 仍严格比较。冻结 GOLDEN 额外逐一检查实际全部资源 SHA，因此不会借此放过历史证据被篡改。新 REAL 的 supporting evidence 差异可供审核，不能掩盖物理或审计差异。

WARNING：墙钟时间大于历史 2 倍；ROI planned/full 比例大于 0.9。planned>full 为 FAIL，计划结构任何变化另由 execution 黄金比较触发 CRITICAL。秒数不是硬失败条件。相同数值的 int/float JSON 表达按数值归一，避免 297 与 297.0 的冻结 codec 差异变成假退化。
