# Phase 3 候选审计集中映射（schema 1.0）

用户于 2026-10-21 确认方案 2：不新增 wire enum；现有六组没有证实明确尺寸/几何硬筛除实例。此前 schema_gap 报告为历史检查点，本文件记录确认后的实施规则。

集中维护入口为 `core/adapters/audit_reason_mapper.py` 的 `reason_category`、`map_filter_reason`、`map_candidate_decision`。`audit_mapper.py` 负责合并台账和提供实际最终 membership，不再自行猜测筛除类型。

| 原始模式（按显式字段匹配） | FilterReason / 细分类 | CandidateDisposition |
|---|---|---|
| historical-only，没有最终目标 | None | REVIEW，保留未重算标志 |
| historical-only，有最终目标 | None | RETAINED，维持历史语义 |
| 实际最终 membership，单来源 | None | RETAINED |
| 实际最终 membership，多来源合并 | None；merged_into 为最终对象 | MERGED |
| 显式 human_rejected 或 HUMAN/USER + FALSE_POSITIVE/REJECTED 审核状态，无最终 membership | USER_REJECTED | FILTERED |
| MERGED / DUPLICATE / ASSOCIATED_INTO_OTHER_DEFECT，且目标可在实际 final ID 集合核实 | None；保存 merged_into | MERGED |
| 合并/重复但缺少可核实目标 | None | REVIEW，不能伪造 merged_into |
| REVIEW / PENDING / PROVISIONAL / NO_DELETE / NOT_PROVEN_NOISE / UNASSESSED / UNRELIABLE，无最终 membership | None | REVIEW |
| OUTSIDE_WORK / NONWORK / OUTSIDE_ROI，包括 J5_J5_OUTSIDE_WORK | OUTSIDE_WORK_REGION | FILTERED，除非属于以上待审/归档/最终保留状态 |
| RAW_GATE_REJECT / RAW_CONTRAST_FAIL / STABILITY_FAIL / SAFETY_REJECT | SAFETY_GATE_REJECTED | FILTERED |
| 明确 AREA_TOO_SMALL / SIZE_FILTER / MIN_AREA / GEOMETRY_REJECT | OTHER；extensions.reference_reason_category = SIZE_OR_GEOMETRY_FILTER | FILTERED；仅未来明确实例适用 |
| 明确 BACKGROUND / NOISE / LOCAL_NOISE / LOW_LOCAL_CONTRAST / NOISE_REJECT | BACKGROUND_NOISE | FILTERED；不匹配 NOT_PROVEN_NOISE / NO_DELETE / NOISE_REVIEW 的负面语境 |
| 明确 LOW_EVIDENCE / INSUFFICIENT_EVIDENCE / UNCERTAIN_BUT_REJECTED / WEAK_RESPONSE / EVIDENCE_NOT_SUFFICIENT | LOW_EVIDENCE | FILTERED；待审状态优先，不能将 REVIEW 变成拒绝 |
| 未知原因，但 execution/reason 明确 FILTERED / REJECTED / REMOVED | OTHER | FILTERED |
| 无最终目标且无明确过滤证据，包括 J5_WORK_SMALL | None；细分类 OTHER | REVIEW |

类别优先级：显式人工否定、合并/重复、非工作区、安全门、明确尺寸/几何、背景噪声、证据不足、OTHER。状态判断先保留 historical-only 语义，再使用实际最终 membership；之后处理人工状态、明确合并、待审/未删除、明确筛除及未知。两层分别表示“原算法原因类别”与“候选实际去向”，因此 REVIEW 记录可以保留 LOW_EVIDENCE 等原因细分类，但不被宣称已过滤。

`filter_message` 始终保留原始选定 `decision_reason`（缺失时依次使用 `reason_for_visibility`、`reason`），包括最终保留/合并候选。`extensions.reference_decision` 保留同值；`extensions.reference_fields` 无损保留 decision_reason、备用 reason、stage、primary_visibility_layer、classification、execution_disposition 以及审核/合并依据字段。没有依据不生成 USER_REJECTED。

字符串匹配使用大写规范化和下划线词界，不读取面积数字来猜测过滤。`MICRO_HIDE_SUGGESTION...NO_DELETE`、`MICRO_REVIEW...NOT_PROVEN_NOISE` 均按实际 membership 保留为 REVIEW / RETAINED / MERGED；没有把“面积小”当作背景噪声或硬尺寸拒绝。

fresh/historical/union 数量、historical_only_not_recomputed、候选身份、几何、current_stage、final_defect_id、最终对象来源集合和 RAW recovery 事件保持不变。仅新鲜多来源最终成员从 RETAINED 改为 MERGED，merged_into 指向已有实际对象，不修改 final membership。历史未重算成员保持既有 disposition 和 filter_reason。

生产 YAML 状态更新为 REFERENCE_ENGINE_CONNECTED。它只描述适配器连接状态，不表示独立打包或发布。重映射保留原始 algorithm_info/config_hash，因为该 hash 描述原计算使用的配置；没有把更新后的配置标签冒充原始检测配置。

`scripts/remap_phase3_results.py` 只调用已有 mapper，不调用 Detector 或启动引擎；必须使用新建输出目录，拒绝将输出写入 engine 证据目录。新快照保存原始结果 ID、原真实执行来源、审计修订标志及本次未重算标志。六组验证期间禁止启动 subprocess，另核对所有既有 engine 文件 SHA256 前后一致。
